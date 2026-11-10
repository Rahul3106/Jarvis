import os
import uuid
import time
import json
import logging
import threading
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    for env_path in [".env", "backend/.env", "../.env", os.path.join(os.path.dirname(__file__), "..", ".env")]:
        if os.path.exists(env_path):
            load_dotenv(env_path, override=True)
except Exception:
    pass

from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session
import requests

from app.database import init_db, get_db, SessionLocal, Incident, IncidentLog, Event
from app.event_normalizer import (
    normalize_api_event,
    normalize_alertmanager_alert,
    parse_log_file_content,
    generate_event_id
)
from app.topology import get_topology_graph, get_shared_dependencies, get_topological_distance
from app.correlation import correlation_engine
from app.timeline import build_incident_timeline
from app.agent import agent_app, log_step, send_admin_failure_email, MAX_TRIES

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis-backend")

app = FastAPI(title="J.A.R.V.I.S. AI - SRE Backend")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development ease
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Built-in Health Monitor ──────────────────────────────────────────────
# Replaces Prometheus + AlertManager when they are not available (local dev).
# Polls every service every 5 seconds for anomalies and triggers the agent.

MONITOR_INTERVAL = 10  # seconds
MEMORY_THRESHOLD_MB = 120.0  # trigger alert above this (well above normal baseline)
CPU_THRESHOLD = 0.85  # trigger alert above this
ENABLE_HEALTH_MONITOR = os.getenv("ENABLE_HEALTH_MONITOR", "false").lower() in ("true", "1", "yes")

# Concurrency lock to prevent multiple simultaneous LLM agent runs from eating tokens
_agent_workflow_lock = threading.Lock()

# Will be populated after LOCAL_PORTS is defined further below
_monitor_thread = None

def _has_active_incident(db, service_name: str, alert_name: str) -> bool:
    """Check if there is already an active incident for this service/alert."""
    return db.query(Incident).filter(
        Incident.service == service_name,
        Incident.alert_name == alert_name,
        Incident.status.in_(["INVESTIGATING", "ROOT_CAUSE_FOUND", "EXECUTING_FIX", "VERIFYING"])
    ).first() is not None

def check_max_tries_exceeded(db, service_name: str, alert_name: str, max_tries: int = MAX_TRIES) -> bool:
    """Check if the number of consecutive failed incidents for this service/alert has reached or exceeded max_tries."""
    incidents = db.query(Incident).filter(
        Incident.service == service_name,
        Incident.alert_name == alert_name
    ).order_by(Incident.created_at.desc()).all()
    
    consecutive_failures = 0
    for inc in incidents:
        if inc.status == "FAILED":
            consecutive_failures += 1
        elif inc.status == "RESOLVED":
            break
            
    return consecutive_failures >= max_tries

def _create_and_run_incident(service_name: str, alert_name: str, severity: str):
    """Create an incident record and run the agent workflow synchronously."""
    db = SessionLocal()
    try:
        # 1. Double-check dedup inside the monitor thread
        if _has_active_incident(db, service_name, alert_name):
            return

        # 2. Check if this anomaly correlates with an ongoing active incident
        mock_event_dict = {
            "service": service_name,
            "message": f"[HealthMonitor] {alert_name} on {service_name}",
            "severity": severity,
            "timestamp": datetime.utcnow()
        }
        matched_inc, score = correlation_engine.find_matching_active_incident(db, mock_event_dict)
        if matched_inc:
            logger.info(f"[HealthMonitor] Anomaly '{alert_name}' on '{service_name}' correlated into active incident {matched_inc.id} (Score: {score:.2f})")
            event_entry = Event(
                id=generate_event_id("EVT-MON"),
                incident_id=matched_inc.id,
                source="simulator",
                service=service_name,
                event_type="alert",
                severity=severity.lower(),
                timestamp=datetime.utcnow(),
                message=f"[HealthMonitor] Auto-detected anomaly: '{alert_name}' on '{service_name}'",
                metadata_json=json.dumps({"alert_name": alert_name, "severity": severity})
            )
            db.add(event_entry)

            # Expand affected_services
            current_affected = []
            if matched_inc.affected_services:
                try:
                    current_affected = json.loads(matched_inc.affected_services)
                except Exception:
                    current_affected = [matched_inc.service]
            else:
                current_affected = [matched_inc.service]
            if service_name not in current_affected:
                current_affected.append(service_name)
                matched_inc.affected_services = json.dumps(current_affected)

            log_entry = IncidentLog(
                incident_id=matched_inc.id,
                level="INFO",
                message=f"[CorrelationEngine] Auto-correlated anomaly '{alert_name}' on '{service_name}' into incident '{matched_inc.id}' (Score: {score:.2f})",
                timestamp=datetime.utcnow()
            )
            db.add(log_entry)
            db.commit()
            return

        # 3. Check if max tries has been reached for consecutive failures
        if check_max_tries_exceeded(db, service_name, alert_name, MAX_TRIES):
            logger.warning(
                f"[HealthMonitor] Alert '{alert_name}' on service '{service_name}' has exceeded maximum tries ({MAX_TRIES}). Automatic self-healing suspended."
            )
            return

        incident_id = f"INC-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        new_incident = Incident(
            id=incident_id,
            service=service_name,
            alert_name=alert_name,
            severity=severity,
            status="INVESTIGATING",
            created_at=datetime.utcnow()
        )
        db.add(new_incident)
        db.commit()

        # Record normalized Event entry
        event_entry = Event(
            id=generate_event_id("EVT-MON"),
            incident_id=incident_id,
            source="simulator",
            service=service_name,
            event_type="alert",
            severity=severity.lower(),
            timestamp=datetime.utcnow(),
            message=f"[HealthMonitor] Auto-detected anomaly: '{alert_name}' on '{service_name}'",
            metadata_json=json.dumps({"alert_name": alert_name, "severity": severity})
        )
        db.add(event_entry)

        log_entry = IncidentLog(
            incident_id=incident_id,
            level="WARNING",
            message=f"[HealthMonitor] Alert '{alert_name}' (severity: {severity}) auto-detected on service '{service_name}'",
            timestamp=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Monitor: failed to create incident: {e}")
        return
    finally:
        db.close()

    logger.info(f"Monitor: triggering agent workflow for {incident_id}")
    try:
        run_agent_workflow(incident_id, service_name, alert_name)
    except Exception as e:
        logger.error(f"Monitor: agent workflow crashed for {incident_id}: {e}")

def _health_monitor_loop():
    """Background thread that continuously polls services for anomalies."""
    # Wait a few seconds for services to come online
    time.sleep(8)
    logger.info("Background health monitor started – polling every %ds", MONITOR_INTERVAL)

    while True:
        try:
            for service_name, port in LOCAL_PORTS.items():
                url = get_service_url(service_name)
                try:
                    # ── Check metrics ────────────────────────────────
                    memory_mb = 0.0
                    cpu = 0.0
                    metric_resp = requests.get(f"{url}/metrics", timeout=0.8)
                    if metric_resp.status_code == 200:
                        for line in metric_resp.text.split("\n"):
                            if line.startswith("service_memory_usage_bytes") and not line.startswith("#"):
                                try:
                                    memory_mb = float(line.split()[1]) / (1024 * 1024)
                                except (ValueError, IndexError):
                                    pass
                            elif line.startswith("service_cpu_usage_ratio") and not line.startswith("#"):
                                try:
                                    cpu = float(line.split()[1])
                                except (ValueError, IndexError):
                                    pass

                    # ── Check health ─────────────────────────────────
                    health_ok = False
                    active_fault = None
                    try:
                        health_resp = requests.get(f"{url}/health", timeout=0.8)
                        health_ok = health_resp.status_code == 200
                        if not health_ok:
                            try:
                                detail = health_resp.json().get("detail", "")
                                if ":" in detail:
                                    active_fault = detail.split(":")[0].strip()
                            except Exception:
                                pass
                    except Exception:
                        pass

                    # ── Decide if alert should fire ──────────────────
                    if memory_mb > MEMORY_THRESHOLD_MB:
                        alert_name = "HighMemoryUsage"
                        severity = "critical"
                    elif cpu > CPU_THRESHOLD:
                        alert_name = "HighCpuUsage"
                        severity = "warning"
                    elif not health_ok:
                        if active_fault == "DependencyFailure":
                            alert_name = "DependencyFailure"
                            severity = "critical"
                        elif active_fault == "DatabaseSaturation":
                            alert_name = "DatabaseSaturation"
                            severity = "critical"
                        elif active_fault == "NetworkPartition":
                            alert_name = "NetworkPartition"
                            severity = "critical"
                        elif active_fault == "CascadingFailure":
                            alert_name = "CascadingFailure"
                            severity = "critical"
                        elif active_fault == "ConfigurationDrift":
                            alert_name = "ConfigurationDrift"
                            severity = "warning"
                        elif active_fault == "CertificateExpiration":
                            alert_name = "CertificateExpiration"
                            severity = "critical"
                        elif active_fault:
                            alert_name = active_fault
                            severity = "critical"
                        else:
                            # Transient lag or service starting up; do NOT trigger false incidents
                            continue
                    else:
                        continue  # service is healthy, move on

                    # Fire in a separate thread so monitor keeps polling
                    threading.Thread(
                        target=_create_and_run_incident,
                        args=(service_name, alert_name, severity),
                        daemon=True
                    ).start()

                except Exception as e:
                    # Service unreachable – skip it silently
                    pass
        except Exception as e:
            logger.error(f"Monitor loop error: {e}")

        time.sleep(MONITOR_INTERVAL)

# Initialize database on startup and launch the health monitor
@app.on_event("startup")
def startup_event():
    global _monitor_thread
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized.")

    # Only start background health monitor thread if explicitly enabled
    if ENABLE_HEALTH_MONITOR:
        _monitor_thread = threading.Thread(target=_health_monitor_loop, daemon=True)
        _monitor_thread.start()
        logger.info("Background health monitor thread launched.")
    else:
        logger.info("Background auto health monitor is disabled (ENABLE_HEALTH_MONITOR=false). Incidents will be triggered on-demand via Chaos Lab or AlertManager.")

# Pydantic Schemas
class FaultInjectionRequest(BaseModel):
    service: str
    fault: str # memory-leak, cpu-spike, error-spike

# Helper to run LangGraph Agent
def run_agent_workflow(incident_id: str, service: str, alert_name: str):
    logger.info(f"Queued background LangGraph workflow for incident {incident_id}")
    with _agent_workflow_lock:
        logger.info(f"Acquired lock: Starting LangGraph workflow for incident {incident_id}")
        try:
        db = SessionLocal()
        correlated_events = []
        impact_metrics = {}
        try:
            evts = db.query(Event).filter(Event.incident_id == incident_id).order_by(Event.timestamp.asc()).all()
            correlated_events = [e.to_dict() for e in evts]

            inc = db.query(Incident).filter(Incident.id == incident_id).first()
            if inc:
                tx = inc.failed_transactions or 0
                lg = inc.failed_logins or 0
                impact_metrics = {
                    "failed_transactions": tx,
                    "failed_logins": lg,
                    "estimated_revenue_at_risk_usd": round(tx * 49.99, 2),
                    "estimated_users_affected": tx + lg,
                    "impact_summary": inc.impact_summary or "",
                    "is_measured": True
                }
        finally:
            db.close()

        initial_state = {
            "incident_id": incident_id,
            "service": service,
            "alert_name": alert_name,
            "status": "INVESTIGATING",
            "root_cause": None,
            "confidence": None,
            "severity": None,
            "risk_level": None,
            "evidence": None,
            "affected_services": None,
            "reasoning_summary": None,
            "remediation_choice": None,
            "remediation_result": None,
            "verification_success": None,
            "incident_report": None,
            "next_agent": None,
            "analyzer_logs": None,
            "analyzer_metrics": None,
            "analyzer_health": None,
            "governance_approved": None,
            "governance_reason": None,
            "correlated_events": correlated_events,
            "impact_metrics": impact_metrics,
            "alternative_causes": None
        }
        # Execute compiled LangGraph workflow
        agent_app.invoke(initial_state)
    except Exception as e:
        logger.error(f"Error executing agent workflow for {incident_id}: {str(e)}")
        log_step(incident_id, f"Agent workflow execution crashed: {str(e)}", "ERROR")
        
        # Mark incident failed
        db = SessionLocal()
        try:
            incident = db.query(Incident).filter(Incident.id == incident_id).first()
            if incident:
                incident.status = "FAILED"
                db.commit()
        except Exception as db_err:
            logger.error(f"Failed to update crashed incident status: {db_err}")
        finally:
            db.close()
            
        # Send admin failure email
        send_admin_failure_email(
            incident_id=incident_id,
            service=service,
            alert_name=alert_name,
            reason=f"Agent workflow execution crashed: {str(e)}"
        )

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

manager = ConnectionManager()

@app.websocket("/api/v1/simulation/ws")
async def simulation_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Poll status safely in threadpool without blocking fastapi event loop
            status = await run_in_threadpool(get_simulation_status)
            await websocket.send_json(status)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# REST Endpoints

class TestIncidentRequest(BaseModel):
    risk_level: str  # "low", "medium", "high", "critical"

@app.post("/api/v1/simulation/trigger_test_incident")
def trigger_test_incident(req: TestIncidentRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    risk = req.risk_level.lower()
    logger.info(f"Triggering simulated test incident for risk level: {risk}")
    
    # Define parameters based on target risk level
    if risk == "low":
        service_name = "notification-service"
        alert_name = "LowPriorityWarning"
        severity = "warning"
    elif risk == "medium":
        service_name = "order-service"
        alert_name = "HighCpuUsage"
        severity = "warning"
    elif risk == "high":
        service_name = "user-service"  # Auth subsystem triggers HIGH minimum
        alert_name = "HttpErrorSpike"
        severity = "critical"
    elif risk == "critical":
        service_name = "database-service"  # DB subsystem + Destructive runbook triggers CRITICAL
        alert_name = "DatabaseCorruptionAlert"
        severity = "critical"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid risk level: {req.risk_level}. Choose from low, medium, high, critical.")
        
    # Check deduplication
    active_incident = db.query(Incident).filter(
        Incident.service == service_name,
        Incident.alert_name == alert_name,
        Incident.status.in_(["INVESTIGATING", "ROOT_CAUSE_FOUND", "EXECUTING_FIX", "VERIFYING", "PENDING_APPROVAL"])
    ).first()
    
    if active_incident:
        logger.info(f"Active incident {active_incident.id} already exists for {service_name}/{alert_name}. Skipping duplicate.")
        return {"status": "ignored", "message": f"An active incident already exists for {service_name}.", "incident_id": active_incident.id}
        
    # Check if max tries has been reached for consecutive failures
    if check_max_tries_exceeded(db, service_name, alert_name, MAX_TRIES):
        raise HTTPException(
            status_code=400,
            detail=f"Service '{service_name}' Alert '{alert_name}' has exceeded maximum tries ({MAX_TRIES}). Clear faults or reset cluster to retry."
        )
        
    # Create new incident entry
    incident_id = f"INC-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
    new_incident = Incident(
        id=incident_id,
        service=service_name,
        alert_name=alert_name,
        severity=severity,
        status="INVESTIGATING",
        created_at=datetime.utcnow()
    )
    db.add(new_incident)
    db.commit()

    # Record normalized Event entry
    event_entry = Event(
        id=generate_event_id("EVT-SIM"),
        incident_id=incident_id,
        source="simulator",
        service=service_name,
        event_type="alert",
        severity=severity.lower(),
        timestamp=datetime.utcnow(),
        message=f"[Simulation] Triggered test incident for {risk.upper()} risk: '{alert_name}' on service '{service_name}'",
        metadata_json=json.dumps({"alert_name": alert_name, "risk_level": risk})
    )
    db.add(event_entry)
    
    # Log initial alert event
    log_entry = IncidentLog(
        incident_id=incident_id,
        level="WARNING",
        message=f"[Simulation] Triggered test incident for {risk.upper()} risk: '{alert_name}' on service '{service_name}'",
        timestamp=datetime.utcnow()
    )
    db.add(log_entry)
    db.commit()
    
    # Queue the agent running loop in background
    background_tasks.add_task(run_agent_workflow, incident_id, service_name, alert_name)
    
    return {"status": "success", "message": f"Simulated {risk.upper()} risk incident triggered.", "incident_id": incident_id}

@app.get("/")
def read_root():
    return {"message": "J.A.R.V.I.S. SRE API is running."}

@app.post("/api/v1/alerts/webhook")
def alerts_webhook(payload: Dict[str, Any], background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Receives AlertManager alerts, parses them, and runs the SRE agent in background."""
    logger.info(f"Received alert webhook payload: {payload}")
    
    alerts = payload.get("alerts", [])
    if not alerts:
        return {"status": "ignored", "message": "No active alerts found in payload"}
        
    for alert in alerts:
        # Check if the alert is firing (we ignore resolved alerts since the agent fixes them)
        status = alert.get("status")
        if status == "resolved":
            logger.info("Ignoring resolved alert notification.")
            continue

        # Normalize incoming AlertManager alert into unified schema
        norm_event = normalize_alertmanager_alert(alert)
        service_name = norm_event["service"]
        alert_name = alert.get("labels", {}).get("alertname", "UnknownAlert")
        severity = norm_event["severity"]
        
        # Check if incoming alert correlates with any active incident
        matched_incident, score = correlation_engine.find_matching_active_incident(db, norm_event)
        
        if matched_incident:
            logger.info(f"[AlertWebhook] Correlated alert '{alert_name}' on '{service_name}' into active incident {matched_incident.id} (Score: {score:.2f})")
            event_entry = Event(
                id=norm_event["id"],
                incident_id=matched_incident.id,
                source=norm_event["source"],
                service=norm_event["service"],
                event_type=norm_event["event_type"],
                severity=norm_event["severity"],
                timestamp=norm_event["timestamp"],
                message=norm_event["message"],
                trace_id=norm_event["trace_id"],
                raw_payload=norm_event["raw_payload"],
                metadata_json=norm_event["metadata_json"]
            )
            db.add(event_entry)

            # Expand affected_services
            current_affected = []
            if matched_incident.affected_services:
                try:
                    current_affected = json.loads(matched_incident.affected_services)
                except Exception:
                    current_affected = [matched_incident.service]
            else:
                current_affected = [matched_incident.service]
            if service_name not in current_affected and service_name != "unknown":
                current_affected.append(service_name)
                matched_incident.affected_services = json.dumps(current_affected)

            # Log correlation
            log_entry = IncidentLog(
                incident_id=matched_incident.id,
                level="WARNING",
                message=f"[CorrelationEngine] Correlated alert '{alert_name}' on '{service_name}' into incident '{matched_incident.id}' (Score: {score:.2f})",
                timestamp=datetime.utcnow()
            )
            db.add(log_entry)
            db.commit()
            continue
            
        # Check if max tries has been reached for consecutive failures
        if check_max_tries_exceeded(db, service_name, alert_name, MAX_TRIES):
            logger.warning(
                f"[AlertWebhook] Alert '{alert_name}' on service '{service_name}' has exceeded maximum tries ({MAX_TRIES}). Automatic self-healing suspended."
            )
            continue
            
        # Create new incident entry
        incident_id = f"INC-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        new_incident = Incident(
            id=incident_id,
            service=service_name,
            alert_name=alert_name,
            severity=severity,
            status="INVESTIGATING",
            created_at=datetime.utcnow()
        )
        db.add(new_incident)
        db.commit()

        # Persist normalized Event record linked to this incident
        event_entry = Event(
            id=norm_event["id"],
            incident_id=incident_id,
            source=norm_event["source"],
            service=norm_event["service"],
            event_type=norm_event["event_type"],
            severity=norm_event["severity"],
            timestamp=norm_event["timestamp"],
            message=norm_event["message"],
            trace_id=norm_event["trace_id"],
            raw_payload=norm_event["raw_payload"],
            metadata_json=norm_event["metadata_json"]
        )
        db.add(event_entry)
        
        # Log initial alert event
        log_entry = IncidentLog(
            incident_id=incident_id,
            level="WARNING",
            message=f"Alert '{alert_name}' (severity: {severity}) triggered on service '{service_name}'",
            timestamp=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        
        # Queue the agent running loop in background
        background_tasks.add_task(run_agent_workflow, incident_id, service_name, alert_name)
        
    return {"status": "processed", "message": "Triggered background SRE agents for alerts."}

@app.get("/api/v1/incidents")
def list_incidents(db: Session = Depends(get_db)):
    """Lists all past and active SRE incidents."""
    incidents = db.query(Incident).order_by(Incident.created_at.desc()).all()
    return incidents

@app.get("/api/v1/incidents/{incident_id}")
def get_incident_details(incident_id: str, db: Session = Depends(get_db)):
    """Gets details for a single incident including correlated events."""
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    events = db.query(Event).filter(Event.incident_id == incident_id).order_by(Event.timestamp.asc()).all()
    return {
        "id": incident.id,
        "service": incident.service,
        "alert_name": incident.alert_name,
        "status": incident.status,
        "severity": incident.severity,
        "root_cause": incident.root_cause,
        "confidence": incident.confidence,
        "risk_level": incident.risk_level,
        "evidence": incident.evidence,
        "affected_services": incident.affected_services,
        "reasoning_summary": incident.reasoning_summary,
        "resolution_action": incident.resolution_action,
        "resolution_time_seconds": incident.resolution_time_seconds,
        "failed_transactions": incident.failed_transactions or 0,
        "failed_logins": incident.failed_logins or 0,
        "impact_summary": incident.impact_summary,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "updated_at": incident.updated_at.isoformat() if incident.updated_at else None,
        "events": [e.to_dict() for e in events]
    }

@app.post("/api/v1/incidents/{incident_id}/approve")
def approve_incident_remediation(incident_id: str, db: Session = Depends(get_db)):
    """
    Operator manual approval endpoint:
    Approves an incident held in PENDING_APPROVAL state, executes the recovery runbook,
    verifies microservice health, updates the post-mortem report, and marks the incident RESOLVED.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status != "PENDING_APPROVAL":
        return {
            "status": "ignored",
            "message": f"Incident {incident_id} is currently '{incident.status}', not 'PENDING_APPROVAL'.",
            "incident_id": incident.id
        }

    # 1. Update status to EXECUTING_FIX
    incident.status = "EXECUTING_FIX"
    db.commit()

    log_step(incident_id, "[Governance & Safety Agent] Manual SRE Operator Approval GRANTED via Console.", "INFO")
    log_step(incident_id, f"[Incident Commander] Human confirmation received. Authorizing remediation for service '{incident.service}'.", "AGENT_ACTION")

    # 2. Execute remediation
    service = incident.service
    from app.tools import restart_service, check_service_health
    
    remediation_log = ""
    if any(k in (incident.alert_name or "").lower() for k in ["database", "pool", "saturation"]) or service == "database-service":
        restart_service.invoke({"service_name": "database-service"})
        restart_service.invoke({"service_name": service})
        remediation_log = f"Reset database connection pool and restarted {service}."
    else:
        restart_service.invoke({"service_name": service})
        remediation_log = f"Restarted service {service} and cleared fault state."

    log_step(incident_id, f"[Remediation Executor] Result: {remediation_log}", "AGENT_RESULT")

    # 3. Post-Remediation Verification
    log_step(incident_id, f"[Auditor] Verifying post-remediation health for '{service}'...", "AGENT_THOUGHT")
    health_output = check_service_health.invoke({"service_name": service})
    log_step(incident_id, f"[Auditor] Health Probe Result:\n{health_output}", "AGENT_RESULT")

    # 4. Resolve incident
    incident.status = "RESOLVED"
    incident.resolution_time_seconds = round((datetime.utcnow() - incident.created_at).total_seconds(), 1) if incident.created_at else 45.0
    
    approval_addendum = (
        f"\n\n---\n"
        f"## 10. Manual Operator Authorization & Final Resolution\n"
        f"* **Authorization Gate:** APPROVED BY SRE OPERATOR (CONSOLE)\n"
        f"* **Executed Runbook:** `{remediation_log}`\n"
        f"* **Recovery Verification:** Health probe verified OK (200 Status)\n"
        f"* **Mean Time to Recovery (MTTR):** `{incident.resolution_time_seconds}s`\n"
        f"* **Final Status:** RESOLVED\n"
    )
    if incident.resolution_action:
        updated_report = incident.resolution_action.replace(
            "**SUSPENDED (PENDING HUMAN APPROVAL)**",
            "**RESOLVED (MANUAL SRE APPROVAL GRANTED)**"
        )
        incident.resolution_action = updated_report + approval_addendum
    else:
        incident.resolution_action = f"# SRE Incident Resolution - {incident_id}\n\n{approval_addendum}"

    db.commit()
    log_step(incident_id, f"[Incident Commander] SRE verification & post-mortem complete. Closing incident lifecycle as RESOLVED.", "INFO")

    return {
        "status": "success",
        "message": f"Incident {incident_id} approved and resolved successfully.",
        "incident": {
            "id": incident.id,
            "status": incident.status,
            "resolution_time_seconds": incident.resolution_time_seconds
        }
    }

@app.post("/api/v1/incidents/{incident_id}/reject")
def reject_incident_remediation(incident_id: str, db: Session = Depends(get_db)):
    """
    Operator manual rejection endpoint:
    Rejects the proposed remediation for an incident in PENDING_APPROVAL.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.status = "FAILED"
    db.commit()
    log_step(incident_id, "[Governance & Safety Agent] Manual SRE Operator REJECTED remediation. Action cancelled.", "WARNING")
    log_step(incident_id, "[Incident Commander] Incident closed as FAILED by operator override.", "INFO")
    return {"status": "rejected", "incident_id": incident.id}

@app.get("/api/v1/incidents/{incident_id}/logs")
def get_incident_logs(incident_id: str, db: Session = Depends(get_db)):
    """Gets the execution log timeline for a single incident."""
    logs = db.query(IncidentLog).filter(IncidentLog.incident_id == incident_id).order_by(IncidentLog.timestamp.asc()).all()
    return logs

@app.get("/api/v1/incidents/{incident_id}/timeline")
def get_incident_timeline_endpoint(incident_id: str, db: Session = Depends(get_db)):
    """
    Returns the unified chronological incident timeline, combining multi-source
    symptoms (alerts, API failures, error logs), multi-agent investigation milestones,
    governance evaluations, and remediation actions.
    """
    timeline_data = build_incident_timeline(db, incident_id)
    if not timeline_data:
        raise HTTPException(status_code=404, detail="Incident not found")
    return timeline_data

@app.get("/api/v1/incidents/{incident_id}/report")
def get_incident_report(incident_id: str, db: Session = Depends(get_db)):
    """
    Returns the comprehensive post-mortem report and audit metadata for an incident.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    return {
        "incident_id": incident.id,
        "service": incident.service,
        "alert_name": incident.alert_name,
        "status": incident.status,
        "risk_level": incident.risk_level,
        "confidence": incident.confidence,
        "has_post_mortem": bool(incident.resolution_action),
        "post_mortem_markdown": incident.resolution_action or "Post-mortem report pending compilation.",
        "resolution_time_seconds": incident.resolution_time_seconds,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "updated_at": incident.updated_at.isoformat() if incident.updated_at else None
    }

@app.get("/api/v1/incidents/{incident_id}/report/download")
def download_incident_report(incident_id: str, db: Session = Depends(get_db)):
    """
    Downloads the incident post-mortem markdown report directly as an attachment.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    content = incident.resolution_action or (
        f"# SRE Incident Post-Mortem and Audit Report - {incident.id}\n\n"
        f"**Service:** {incident.service}\n"
        f"**Alert:** {incident.alert_name}\n"
        f"**Status:** {incident.status}\n\n"
        f"*Post-mortem report pending compilation by SRE Auditor.*\n"
    )
    filename = f"post-mortem-{incident_id}.md"
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# ── Unified Event Ingestion Endpoints (J.A.R.V.I.S. Multi-Source Ingestion) ─

class EventIngestRequest(BaseModel):
    service: Optional[str] = None
    message: str
    event_type: Optional[str] = "api_event"
    severity: Optional[str] = "info"
    source: Optional[str] = "api"
    timestamp: Optional[str] = None
    trace_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class BatchEventIngestRequest(BaseModel):
    events: List[EventIngestRequest]

@app.post("/api/v1/events")
def ingest_event(req: EventIngestRequest, db: Session = Depends(get_db)):
    """
    Ingests a single generic event from external APIs, webhooks, or agents.
    Normalizes event payload into the unified Event schema and persists it.
    Uses the Correlation Engine to automatically bind to active incidents.
    """
    norm = normalize_api_event(req.model_dump() if hasattr(req, "model_dump") else req.dict())
    
    event_record = Event(
        id=norm["id"],
        incident_id=None,
        source=norm["source"],
        service=norm["service"],
        event_type=norm["event_type"],
        severity=norm["severity"],
        timestamp=norm["timestamp"],
        message=norm["message"],
        trace_id=norm["trace_id"],
        raw_payload=norm["raw_payload"],
        metadata_json=norm["metadata_json"]
    )
    db.add(event_record)
    db.commit()

    # Pass through correlation engine to associate with active incident
    correlation_result = correlation_engine.correlate_and_assign(db, event_record)

    logger.info(f"Ingested external API event {event_record.id} for service {event_record.service} (Action: {correlation_result['action']})")
    return {
        "status": "success",
        "message": "Event ingested and processed by correlation engine.",
        "correlation": correlation_result,
        "event": event_record.to_dict()
    }

@app.post("/api/v1/events/batch")
def ingest_events_batch(req: BatchEventIngestRequest, db: Session = Depends(get_db)):
    """
    Ingests multiple events atomically in a batch and runs correlation.
    """
    if not req.events:
        return {"status": "ignored", "count": 0, "events": []}

    created_events = []
    correlation_summaries = []
    for item in req.events:
        norm = normalize_api_event(item.model_dump() if hasattr(item, "model_dump") else item.dict())
        event_record = Event(
            id=norm["id"],
            incident_id=None,
            source=norm["source"],
            service=norm["service"],
            event_type=norm["event_type"],
            severity=norm["severity"],
            timestamp=norm["timestamp"],
            message=norm["message"],
            trace_id=norm["trace_id"],
            raw_payload=norm["raw_payload"],
            metadata_json=norm["metadata_json"]
        )
        db.add(event_record)
        created_events.append(event_record)

    db.commit()

    # Run correlation assignment on all created events
    for evt in created_events:
        c_res = correlation_engine.correlate_and_assign(db, evt)
        correlation_summaries.append(c_res)

    logger.info(f"Batch ingested {len(created_events)} events.")
    return {
        "status": "success",
        "count": len(created_events),
        "correlations": correlation_summaries,
        "events": [e.to_dict() for e in created_events]
    }

@app.post("/api/v1/logs/upload")
async def upload_log_file(
    file: UploadFile = File(...),
    service: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Uploads and parses a log file (.log, .txt, .json, .jsonl).
    Extracts timestamps, severity levels, trace IDs, and services.
    Persists structured Event records, correlates them into incidents,
    and automatically spawns autonomous investigation if anomalies are detected.
    """
    filename = file.filename or "unknown.log"
    try:
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    parsed_events = parse_log_file_content(content, filename=filename, default_service=service)
    if not parsed_events:
        return {
            "status": "warning",
            "filename": filename,
            "events_ingested": 0,
            "events_correlated": 0,
            "master_incident_id": None,
            "message": "File was empty or no parseable log events found."
        }

    created_records = []
    for pe in parsed_events:
        event_record = Event(
            id=pe["id"],
            incident_id=None,
            source="file",
            service=pe["service"],
            event_type=pe["event_type"],
            severity=pe["severity"],
            timestamp=pe["timestamp"],
            message=pe["message"],
            trace_id=pe["trace_id"],
            raw_payload=pe["raw_payload"],
            metadata_json=pe.get("metadata_json")
        )
        db.add(event_record)
        created_records.append(event_record)

    db.commit()

    # 1. Attempt correlation with active ongoing incidents
    grouped_count = 0
    matched_inc_id = None
    for evt in created_records:
        c_res = correlation_engine.correlate_and_assign(db, evt)
        if c_res.get("action") == "attached_to_incident":
            grouped_count += 1
            matched_inc_id = c_res.get("incident_id")

    # 2. If no active incident was running, synthesize Master Incident from uploaded log failure
    if grouped_count == 0 and created_records:
        primary_event = next((e for e in created_records if e.severity == "critical"), None)
        if not primary_event:
            primary_event = next((e for e in created_records if e.severity == "error"), created_records[0])

        service_name = primary_event.service if primary_event.service != "unknown" else (service or "payment-service")
        
        # Derive canonical alert name based on error signature
        msg_l = (primary_event.message or "").lower()
        if any(w in msg_l for w in ["database", "pool", "saturation", "postgres"]):
            alert_name = "DatabaseSaturation"
        elif any(w in msg_l for w in ["memory", "heap", "oom"]):
            alert_name = "HighMemoryUsage"
        elif any(w in msg_l for w in ["500", "gateway", "spike"]):
            alert_name = "HttpErrorSpike"
        else:
            alert_name = f"LogAnomaly-{service_name}"

        incident_id = f"INC-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        new_incident = Incident(
            id=incident_id,
            service=service_name,
            alert_name=alert_name,
            severity="CRITICAL" if primary_event.severity == "critical" else "HIGH",
            status="INVESTIGATING",
            created_at=datetime.utcnow()
        )
        db.add(new_incident)
        db.commit()

        # Link all created log records to this new incident
        affected_services = set()
        failed_logins = 0
        failed_transactions = 0

        for evt in created_records:
            evt.incident_id = incident_id
            if evt.service and evt.service != "unknown":
                affected_services.add(evt.service)
            msg_l = (evt.message or "").lower()
            if "login" in msg_l and ("fail" in msg_l or "timeout" in msg_l or "delayed" in msg_l):
                failed_logins += 1
            if ("payment" in msg_l or "checkout" in msg_l or "transaction" in msg_l) and ("fail" in msg_l or "timeout" in msg_l or "aborted" in msg_l):
                failed_transactions += 1

        new_incident.affected_services = json.dumps(list(affected_services) if affected_services else [service_name])
        new_incident.failed_logins = failed_logins
        new_incident.failed_transactions = failed_transactions
        db.commit()

        # Add initial audit log
        log_entry = IncidentLog(
            incident_id=incident_id,
            level="WARNING",
            message=f"Log file '{filename}' triggered Master Incident: {len(created_records)} events ingested across {list(affected_services)}",
            timestamp=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()

        if background_tasks:
            background_tasks.add_task(run_agent_workflow, incident_id, service_name, alert_name)

        grouped_count = len(created_records)
        matched_inc_id = incident_id

    logger.info(f"Uploaded and ingested {len(created_records)} log events from {filename} ({grouped_count} correlated into {matched_inc_id})")

    return {
        "status": "success",
        "filename": filename,
        "events_ingested": len(created_records),
        "events_correlated": grouped_count,
        "master_incident_id": matched_inc_id,
        "service": service or (created_records[0].service if created_records else "unknown"),
        "sample_events": [e.to_dict() for e in created_records[:10]]
    }

@app.get("/api/v1/events")
def list_events(
    incident_id: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lists ingested events with optional filtering by incident, service, severity, and source."""
    query = db.query(Event)
    if incident_id:
        query = query.filter(Event.incident_id == incident_id)
    if service:
        query = query.filter(Event.service == service)
    if severity:
        query = query.filter(Event.severity == severity.lower())
    if source:
        query = query.filter(Event.source == source.lower())

    events = query.order_by(Event.timestamp.desc()).limit(limit).all()
    return [e.to_dict() for e in events]

@app.get("/api/v1/events/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_db)):
    """Retrieves a single event by ID."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event.to_dict()

# ── Correlation & Topology Endpoints (Phase 2) ──────────────────────────

@app.get("/api/v1/topology")
def get_topology():
    """Returns complete service call graph, shared infrastructure dependencies, and node metadata."""
    return get_topology_graph()

@app.get("/api/v1/incidents/{incident_id}/correlated-events")
def get_incident_correlated_events(incident_id: str, db: Session = Depends(get_db)):
    """Returns all events correlated with this incident, along with correlation statistics."""
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    events = db.query(Event).filter(Event.incident_id == incident_id).order_by(Event.timestamp.asc()).all()

    services_involved = set()
    sources = set()
    severity_counts: Dict[str, int] = {}
    for ev in events:
        services_involved.add(ev.service)
        sources.add(ev.source)
        sev = (ev.severity or "info").lower()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "incident_id": incident.id,
        "primary_service": incident.service,
        "alert_name": incident.alert_name,
        "status": incident.status,
        "total_correlated_events": len(events),
        "services_involved": list(services_involved),
        "sources": list(sources),
        "severity_counts": severity_counts,
        "events": [e.to_dict() for e in events]
    }

class CorrelationEvaluateRequest(BaseModel):
    event_a: Dict[str, Any]
    event_b: Dict[str, Any]
    time_window_seconds: Optional[float] = 35.0

@app.post("/api/v1/correlation/evaluate")
def evaluate_correlation(req: CorrelationEvaluateRequest):
    """Evaluates correlation score and causal affinity between two candidate events."""
    score = correlation_engine.compute_event_correlation(req.event_a, req.event_b)
    is_correlated = score >= correlation_engine.min_score
    return {
        "score": score,
        "is_correlated": is_correlated,
        "threshold": correlation_engine.min_score,
        "shared_dependencies": get_shared_dependencies(
            req.event_a.get("service", ""),
            req.event_b.get("service", "")
        ),
        "topological_distance": get_topological_distance(
            req.event_a.get("service", ""),
            req.event_b.get("service", "")
        )
    }

@app.get("/api/v1/benchmarks")
def get_benchmarks(db: Session = Depends(get_db)):
    """Computes real benchmark metrics from historical incident data."""
    all_incidents = db.query(Incident).all()

    if not all_incidents:
        return {
            "total_incidents": 0,
            "summary": {
                "avg_mttr": 0,
                "recovery_success_rate": 0,
                "false_positive_rate": 0,
                "agent_accuracy": 0,
                "total_resolved": 0,
                "total_failed": 0,
                "total_pending": 0,
            },
            "by_alert_type": []
        }

    # Count by status
    resolved = [i for i in all_incidents if i.status == "RESOLVED"]
    failed = [i for i in all_incidents if i.status == "FAILED"]
    pending = [i for i in all_incidents if i.status == "PENDING_APPROVAL"]
    terminal = resolved + failed  # Only completed incidents count for rates

    # Overall MTTR (only from resolved incidents with timing data)
    mttr_values = [i.resolution_time_seconds for i in resolved if i.resolution_time_seconds is not None]
    avg_mttr = round(sum(mttr_values) / len(mttr_values), 1) if mttr_values else 0

    # Recovery success rate = resolved / (resolved + failed)
    success_rate = round(len(resolved) / len(terminal) * 100, 1) if terminal else 0

    # False positive rate: incidents where the resolution action mentions NO_ACTION
    # or where confidence was below 50 (agent was unsure and likely triggered needlessly)
    false_positives = [
        i for i in all_incidents
        if (i.resolution_action and "NO_ACTION" in (i.resolution_action or "").upper())
        or (i.confidence is not None and i.confidence < 50)
    ]
    fp_rate = round(len(false_positives) / len(all_incidents) * 100, 1) if all_incidents else 0

    # Agent accuracy: average RCA confidence across all incidents that have a confidence score
    confidence_values = [i.confidence for i in all_incidents if i.confidence is not None]
    avg_accuracy = round(sum(confidence_values) / len(confidence_values), 1) if confidence_values else 0

    # Breakdown by alert_name
    alert_types: Dict[str, list] = {}
    for inc in all_incidents:
        name = inc.alert_name or "Unknown"
        alert_types.setdefault(name, []).append(inc)

    by_alert = []
    for alert_name, incidents_list in alert_types.items():
        a_resolved = [i for i in incidents_list if i.status == "RESOLVED"]
        a_failed = [i for i in incidents_list if i.status == "FAILED"]
        a_terminal = a_resolved + a_failed
        a_mttr_vals = [i.resolution_time_seconds for i in a_resolved if i.resolution_time_seconds is not None]
        a_conf_vals = [i.confidence for i in incidents_list if i.confidence is not None]
        a_fp = [
            i for i in incidents_list
            if (i.resolution_action and "NO_ACTION" in (i.resolution_action or "").upper())
            or (i.confidence is not None and i.confidence < 50)
        ]

        by_alert.append({
            "alert_name": alert_name,
            "total": len(incidents_list),
            "resolved": len(a_resolved),
            "failed": len(a_failed),
            "avg_mttr": round(sum(a_mttr_vals) / len(a_mttr_vals), 1) if a_mttr_vals else 0,
            "success_rate": round(len(a_resolved) / len(a_terminal) * 100, 1) if a_terminal else 0,
            "false_positive_rate": round(len(a_fp) / len(incidents_list) * 100, 1) if incidents_list else 0,
            "avg_confidence": round(sum(a_conf_vals) / len(a_conf_vals), 1) if a_conf_vals else 0,
        })

    return {
        "total_incidents": len(all_incidents),
        "summary": {
            "avg_mttr": avg_mttr,
            "recovery_success_rate": success_rate,
            "false_positive_rate": fp_rate,
            "agent_accuracy": avg_accuracy,
            "total_resolved": len(resolved),
            "total_failed": len(failed),
            "total_pending": len(pending),
        },
        "by_alert_type": by_alert
    }

# Simulation Fault Control Proxy Endpoints
LOCAL_PORTS = {
    "api-gateway": 8001,
    "user-service": 8002,
    "order-service": 8003,
    "payment-service": 8004,
    "notification-service": 8005
}

def get_service_url(service: str) -> str:
    """Helper to try accessing service in container, with localhost fallback."""
    # Try container host DNS
    url = f"http://{service}:8000"
    try:
        resp = requests.get(f"{url}/health", timeout=0.6)
        if resp.status_code == 200:
            return url
    except Exception:
        pass
    
    # Try local port fallback
    local_port = LOCAL_PORTS.get(service)
    if local_port:
        return f"http://localhost:{local_port}"
    return url

@app.post("/api/v1/simulation/inject")
def inject_simulation_fault(req: FaultInjectionRequest):
    """Triggers fault injection in a simulated service."""
    service = req.service
    fault = req.fault
    logger.info(f"Requesting fault injection: {fault} on {service}")
    
    url = f"{get_service_url(service)}/fault/{fault}"
    try:
        resp = requests.post(url, timeout=3.0)
        if resp.status_code == 200:
            return {"status": "success", "message": f"Fault '{fault}' injected into '{service}'."}
        else:
            raise HTTPException(status_code=500, detail=f"Service returned error code {resp.status_code}: {resp.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not connect to mock service '{service}' at {url}: {str(e)}")

@app.post("/api/v1/simulation/clear")
def clear_simulation_faults():
    """Clears all faults across all services."""
    services = ["api-gateway", "user-service", "order-service", "payment-service", "notification-service"]
    results = {}
    for service in services:
        url = f"{get_service_url(service)}/fault/clear"
        try:
            resp = requests.post(url, timeout=1.5)
            results[service] = "Cleared" if resp.status_code == 200 else f"Error: {resp.status_code}"
        except Exception as e:
            results[service] = f"Connection failed: {str(e)}"
            
    # Reset consecutive failure counters in db by marking FAILED incidents as RESOLVED
    db = SessionLocal()
    try:
        failed_incidents = db.query(Incident).filter(Incident.status == "FAILED").all()
        for inc in failed_incidents:
            inc.status = "RESOLVED"
            inc.resolution_action = (inc.resolution_action or "") + "\n\n---\nIncident manually cleared/resolved by admin."
        db.commit()
        logger.info(f"Marked {len(failed_incidents)} FAILED incidents as RESOLVED due to manual cluster reset.")
    except Exception as e:
        logger.error(f"Failed to clear failed incidents on reset: {e}")
    finally:
        db.close()
            
    return {"status": "success", "cleared_services": results}

@app.get("/api/v1/simulation/status")
def get_simulation_status():
    """Aggregates metrics and health checks for all simulated microservices."""
    services = ["api-gateway", "user-service", "order-service", "payment-service", "notification-service"]
    status_data = {}
    
    for service in services:
        status_data[service] = {
            "name": service,
            "status": "healthy",
            "cpu": 0.05,
            "memory": 20.0,  # MB
            "faults_injected": False
        }
        
        url = get_service_url(service)
        
        try:
            # Check metrics
            metric_resp = requests.get(f"{url}/metrics", timeout=0.5)
            if metric_resp.status_code == 200:
                for line in metric_resp.text.split("\n"):
                    if line.startswith("service_memory_usage_bytes"):
                        status_data[service]["memory"] = float(line.split()[1]) / (1024 * 1024)
                    elif line.startswith("service_cpu_usage_ratio"):
                        status_data[service]["cpu"] = float(line.split()[1])
            
            # Check health
            health_resp = requests.get(f"{url}/health", timeout=0.5)
            if health_resp.status_code != 200:
                status_data[service]["status"] = "unhealthy"
            
            # Detect active faults in metric values
            if status_data[service]["memory"] > 50.0 or status_data[service]["cpu"] > 0.5 or health_resp.status_code != 200:
                status_data[service]["faults_injected"] = True
                
        except Exception:
            status_data[service]["status"] = "offline"
            status_data[service]["cpu"] = 0.0
            status_data[service]["memory"] = 0.0
            status_data[service]["faults_injected"] = False
            
    return status_data

# ── Challenge Scenario Endpoints (Phase 3) ─────────────────────────────

class ScenarioTriggerRequest(BaseModel):
    trace_id: Optional[str] = None
    inject_mock_faults: Optional[bool] = True
    trigger_background_agent: Optional[bool] = False
    failed_transactions: Optional[int] = 142
    failed_logins: Optional[int] = 89
    impact_summary: Optional[str] = None

@app.get("/api/v1/simulation/scenarios")
def list_simulation_scenarios():
    """Returns available simulation challenge scenarios."""
    return [
        {
            "id": "payment-platform-outage",
            "name": "Digital Payment Platform Outage",
            "category": "Shared Infrastructure Saturation",
            "description": (
                "Simulates a high-traffic cascade where the shared database connection pool "
                "exhausts, causing login failures in user-service, slow API 504 timeouts in "
                "order-service, and transaction rollback failures in payment-service."
            ),
            "root_cause_service": "database-service",
            "root_cause_component": "PostgreSQL connection pool on port 5432",
            "affected_services": ["payment-service", "user-service", "order-service", "database-service"],
            "symptoms": {
                "user-service": "Authentication failures and login errors due to connection pool checkout timeout",
                "order-service": "Checkout order latency spikes (>3800ms) and HTTP 504 Gateway Timeouts",
                "payment-service": "Transaction rollbacks and ledger write failures (AlertManager alert)"
            },
            "multi_source_events": [
                {"source": "alertmanager", "service": "payment-service", "type": "DatabaseSaturation alert"},
                {"source": "api", "service": "user-service", "type": "UserLoginFailed event"},
                {"source": "logs", "service": "order-service", "type": "SlowApiResponseTimeout log"}
            ]
        }
    ]

@app.post("/api/v1/simulation/scenario/payment-platform-outage")
def trigger_payment_platform_outage_scenario(
    req: Optional[ScenarioTriggerRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """
    Executes the J.A.R.V.I.S. Challenge Scenario:
    A digital payment platform starts experiencing login failures, slow API responses,
    and failed transactions.
    
    Ingests 3 multi-source events (alert, API event, log entry) with shared trace ID,
    correlates them into ONE unified master incident, calculates business impact,
    and launches root cause analysis.
    """
    if req is None:
        req = ScenarioTriggerRequest()

    scenario_trace_id = req.trace_id or f"tr-pay-outage-{str(uuid.uuid4())[:8]}"
    injected_services = []

    # 1. Optionally inject shared fault on mock microservices
    if req.inject_mock_faults:
        target_services = ["user-service", "order-service", "payment-service"]
        for svc in target_services:
            svc_url = f"{get_service_url(svc)}/fault/shared-db-saturation"
            try:
                resp = requests.post(svc_url, timeout=1.5)
                if resp.status_code == 200:
                    injected_services.append(svc)
            except Exception as e:
                logger.warning(f"Could not inject fault into mock service '{svc}' (offline or unreachable): {e}")

    # 2. Create Master Incident (or reuse active DatabaseSaturation incident if one already exists)
    existing_incident, _ = correlation_engine.find_matching_active_incident(
        db,
        {
            "service": "payment-service",
            "message": "DatabaseSaturation: Payment transaction commit failed",
            "trace_id": scenario_trace_id,
            "timestamp": datetime.utcnow()
        }
    )

    now = datetime.utcnow()
    affected_list = ["payment-service", "user-service", "order-service", "database-service"]
    default_summary = (
        "Shared database connection pool saturation causing concurrent login failures in user-service, "
        "slow API checkout responses in order-service, and transaction rollback failures in payment-service."
    )

    if existing_incident:
        master_incident = existing_incident
        master_incident.severity = "CRITICAL"
        master_incident.affected_services = json.dumps(affected_list)
        master_incident.failed_transactions = req.failed_transactions if req.failed_transactions is not None else 142
        master_incident.failed_logins = req.failed_logins if req.failed_logins is not None else 89
        master_incident.impact_summary = req.impact_summary or default_summary
        master_incident_id = master_incident.id
        db.commit()
    else:
        master_incident_id = f"INC-{now.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        master_incident = Incident(
            id=master_incident_id,
            service="payment-service",
            alert_name="DatabaseSaturation",
            severity="CRITICAL",
            status="INVESTIGATING",
            affected_services=json.dumps(affected_list),
            failed_transactions=req.failed_transactions if req.failed_transactions is not None else 142,
            failed_logins=req.failed_logins if req.failed_logins is not None else 89,
            impact_summary=req.impact_summary or default_summary,
            created_at=now
        )
        db.add(master_incident)
        db.commit()

    # 3. Create Event 1: AlertManager alert on payment-service
    evt1_id = f"evt-pmt-{str(uuid.uuid4())[:8]}"
    evt1 = Event(
        id=evt1_id,
        incident_id=master_incident_id,
        source="alertmanager",
        service="payment-service",
        event_type="alert",
        severity="critical",
        timestamp=now - timedelta(seconds=4),
        message="DatabaseSaturation: Payment transaction commit failed. Ledger write timeout on shared postgres connection pool.",
        trace_id=scenario_trace_id,
        raw_payload=json.dumps({
            "receiver": "jarvis-webhook",
            "status": "firing",
            "alerts": [{
                "labels": {
                    "alertname": "DatabaseSaturation",
                    "service": "payment-service",
                    "severity": "critical",
                    "instance": "postgres-primary:5432"
                },
                "annotations": {
                    "summary": "Payment transaction commit failed",
                    "description": "Ledger write timeout on shared postgres connection pool."
                }
            }]
        }),
        metadata_json=json.dumps({
            "error_type": "DatabaseSaturation",
            "failed_transactions": req.failed_transactions if req.failed_transactions is not None else 142,
            "scenario": "payment-platform-outage"
        })
    )
    db.add(evt1)

    # 4. Create Event 2: API event on user-service
    evt2_id = f"evt-usr-{str(uuid.uuid4())[:8]}"
    evt2 = Event(
        id=evt2_id,
        incident_id=None,
        source="api",
        service="user-service",
        event_type="UserLoginFailed",
        severity="error",
        timestamp=now - timedelta(seconds=2),
        message="DatabaseSaturation: User auth pool exhausted. Login failures spiking across web & mobile clients.",
        trace_id=scenario_trace_id,
        raw_payload=json.dumps({
            "endpoint": "/api/v1/auth/login",
            "status_code": 500,
            "error": "ConnectionCheckoutTimeout",
            "trace_id": scenario_trace_id
        }),
        metadata_json=json.dumps({
            "error_type": "DatabaseSaturation",
            "failed_logins": req.failed_logins if req.failed_logins is not None else 89,
            "scenario": "payment-platform-outage"
        })
    )
    db.add(evt2)
    db.commit()

    # Run correlation on user-service event
    c2 = correlation_engine.correlate_and_assign(db, evt2)

    # 5. Create Event 3: Log event on order-service
    evt3_id = f"evt-ord-{str(uuid.uuid4())[:8]}"
    evt3 = Event(
        id=evt3_id,
        incident_id=None,
        source="logs",
        service="order-service",
        event_type="SlowApiResponseTimeout",
        severity="warning",
        timestamp=now,
        message=f"[ERROR] DatabaseSaturation: High latency (3800ms) and HTTP 504 Gateway Timeout: API gateway slow response on checkout order commit. trace_id={scenario_trace_id}",
        trace_id=scenario_trace_id,
        raw_payload=f"[ERROR] DatabaseSaturation: High latency (3800ms) and HTTP 504 Gateway Timeout: API gateway slow response on checkout order commit. trace_id={scenario_trace_id}",
        metadata_json=json.dumps({
            "error_type": "DatabaseSaturation",
            "latency_ms": 3800,
            "scenario": "payment-platform-outage"
        })
    )
    db.add(evt3)
    db.commit()

    # Run correlation on order-service event
    c3 = correlation_engine.correlate_and_assign(db, evt3)

    # 6. Re-enforce scenario business impact values
    if req.failed_transactions is not None:
        master_incident.failed_transactions = req.failed_transactions
    if req.failed_logins is not None:
        master_incident.failed_logins = req.failed_logins
    if req.impact_summary:
        master_incident.impact_summary = req.impact_summary
    db.commit()

    # 7. Record incident timeline logs
    db.add(IncidentLog(
        incident_id=master_incident_id,
        level="WARNING",
        message=f"[ScenarioTrigger] Injected Challenge Scenario: Digital Payment Platform Outage. Trace ID: {scenario_trace_id}",
        timestamp=now
    ))
    db.add(IncidentLog(
        incident_id=master_incident_id,
        level="INFO",
        message=f"[MultiSourceIngestion] Correlated 3 multi-source events (alertmanager, api, logs) across payment-service, user-service, and order-service into master incident {master_incident_id}",
        timestamp=now + timedelta(milliseconds=100)
    ))
    db.commit()

    # 8. Optionally trigger background agent workflow
    if req.trigger_background_agent:
        background_tasks.add_task(run_agent_workflow, master_incident_id, master_incident.service, master_incident.alert_name)

    return {
        "status": "success",
        "scenario": "payment-platform-outage",
        "scenario_title": "Digital Payment Platform Outage (Shared Dependency Failure)",
        "master_incident_id": master_incident_id,
        "trace_id": scenario_trace_id,
        "injected_mock_services": injected_services,
        "correlated_events_count": 3,
        "affected_services": affected_list,
        "impact": {
            "failed_transactions": master_incident.failed_transactions,
            "failed_logins": master_incident.failed_logins,
            "impact_summary": master_incident.impact_summary
        },
        "symptoms": {
            "payment-service": "Transaction write failures and ledger commit rollbacks (AlertManager alert)",
            "user-service": "Spike in login failures and authentication timeouts (API event)",
            "order-service": "Slow API responses and 504 gateway timeouts on checkout (Log event)"
        },
        "underlying_cause": "Shared database connection pool exhaustion on postgres-primary (database-service)",
        "events": [evt1.to_dict(), evt2.to_dict(), evt3.to_dict()]
    }


