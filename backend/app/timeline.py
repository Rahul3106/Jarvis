"""
J.A.R.V.I.S. AI — Unified Chronological Incident Timeline Aggregator (Phase 5)

This module builds a comprehensive, chronological timeline of an incident's lifecycle:
1. Multi-source symptom arrivals (alerts, API failures, error log lines with original timestamps).
2. Cross-service event correlation and incident creation.
3. SRE Multi-Agent reasoning steps (Analyzer, Diagnostics, RCA, Alternatives).
4. Governance safety review and risk classification gate.
5. Remediation action execution (e.g., CLEAR_STUCK_JOBS, RESTART, SCALE).
6. Auditor verification health checks and convergence probes.
7. Service recovery and post-mortem resolution milestones.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import Incident, Event, IncidentLog


class TimelinePhase:
    DETECTION = "DETECTION"
    CORRELATION = "CORRELATION"
    TELEMETRY = "TELEMETRY"
    DIAGNOSIS = "DIAGNOSIS"
    GOVERNANCE = "GOVERNANCE"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"
    RECOVERY = "RECOVERY"
    LIFECYCLE = "LIFECYCLE"


class TimelineEntryType:
    SYMPTOM_EVENT = "symptom_event"
    AGENT_THOUGHT = "agent_thought"
    AGENT_ACTION = "agent_action"
    AGENT_RESULT = "agent_result"
    MILESTONE = "milestone"
    LIFECYCLE = "lifecycle"


def _categorize_log_phase(message: str, level: str) -> str:
    """Categorizes an incident log message into an SRE lifecycle phase."""
    msg_l = message.lower()

    if any(k in msg_l for k in ["triggered", "scenario", "detected", "initial alert", "alert '"]):
        return TimelinePhase.DETECTION
    if any(k in msg_l for k in ["correlated", "correlation", "grouping", "multisource"]):
        return TimelinePhase.CORRELATION
    if any(k in msg_l for k in ["metrics/log analyzer", "telemetry", "scrape", "logs retrieved"]):
        return TimelinePhase.TELEMETRY
    if any(k in msg_l for k in ["diagnostics agent", "root cause", "rca", "diagnosis", "confidence"]):
        return TimelinePhase.DIAGNOSIS
    if any(k in msg_l for k in ["governance", "safety", "risk classification", "approval", "suspended"]):
        return TimelinePhase.GOVERNANCE
    if any(k in msg_l for k in ["remediation executor", "remediation", "action:", "rollback", "scale", "restart", "clear_stuck_jobs"]):
        return TimelinePhase.REMEDIATION
    if any(k in msg_l for k in ["auditor", "verification", "convergence", "health status", "probe"]):
        return TimelinePhase.VERIFICATION
    if any(k in msg_l for k in ["resolved", "recovered", "closing incident", "post-mortem"]):
        return TimelinePhase.RECOVERY

    if level in ["AGENT_THOUGHT", "AGENT_ACTION", "AGENT_RESULT"]:
        return TimelinePhase.DIAGNOSIS
    return TimelinePhase.LIFECYCLE


def _entry_type_from_level(level: str) -> str:
    if level == "AGENT_THOUGHT":
        return TimelineEntryType.AGENT_THOUGHT
    elif level == "AGENT_ACTION":
        return TimelineEntryType.AGENT_ACTION
    elif level == "AGENT_RESULT":
        return TimelineEntryType.AGENT_RESULT
    elif level in ["WARNING", "ERROR"]:
        return TimelineEntryType.MILESTONE
    return TimelineEntryType.LIFECYCLE


def build_incident_timeline(db: Session, incident_id: str) -> Optional[Dict[str, Any]]:
    """
    Builds a unified chronological timeline for an incident by merging:
    - Ingested Event records (symptoms, alerts, log lines)
    - IncidentLog execution records (multi-agent thoughts, actions, milestones)
    - Incident status transitions
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return None

    timeline_entries: List[Dict[str, Any]] = []
    services_seen: List[str] = []

    # 1. Ingest Correlated Symptom Events
    events = db.query(Event).filter(Event.incident_id == incident_id).all()
    for ev in events:
        svc = ev.service or "unknown"
        if svc not in services_seen and svc != "unknown":
            services_seen.append(svc)

        ts = ev.timestamp or incident.created_at
        ts_str = (ts.isoformat() + "Z") if hasattr(ts, "isoformat") and not str(ts.isoformat()).endswith("Z") else str(ts)
        timeline_entries.append({
            "id": f"tl-evt-{ev.id}",
            "timestamp": ts_str,
            "_sort_key": ts,
            "phase": TimelinePhase.DETECTION,
            "entry_type": TimelineEntryType.SYMPTOM_EVENT,
            "source": ev.source or "event",
            "service": svc,
            "severity": (ev.severity or "info").lower(),
            "title": f"Symptom: {ev.event_type or 'Event'} on {svc}",
            "description": ev.message or "",
            "metadata": {
                "event_id": ev.id,
                "trace_id": ev.trace_id,
                "raw_payload": ev.raw_payload,
                "metadata_json": ev.metadata_json
            }
        })

    # 2. Add Incident Creation Lifecycle Milestone
    c_ts = incident.created_at or datetime.utcnow()
    c_ts_str = (c_ts.isoformat() + "Z") if hasattr(c_ts, "isoformat") and not str(c_ts.isoformat()).endswith("Z") else str(c_ts)
    timeline_entries.append({
        "id": f"tl-inc-created-{incident.id}",
        "timestamp": c_ts_str,
        "_sort_key": c_ts,
        "phase": TimelinePhase.LIFECYCLE,
        "entry_type": TimelineEntryType.LIFECYCLE,
        "source": "system",
        "service": incident.service,
        "severity": (incident.severity or "critical").lower(),
        "title": f"Incident Created: {incident.id}",
        "description": f"Master incident created for alert '{incident.alert_name}' on '{incident.service}'. Severity: {incident.severity}.",
        "metadata": {
            "incident_id": incident.id,
            "alert_name": incident.alert_name,
            "status": incident.status
        }
    })

    # 3. Add Agent Execution Logs
    logs = db.query(IncidentLog).filter(IncidentLog.incident_id == incident_id).all()
    for l in logs:
        l_ts = l.timestamp or incident.created_at
        phase = _categorize_log_phase(l.message, l.level)
        entry_type = _entry_type_from_level(l.level)

        # Detect service mention in log
        log_svc = incident.service
        for s in ["payment-service", "user-service", "order-service", "notification-service", "api-gateway", "database-service"]:
            if s in l.message.lower():
                log_svc = s
                break

        l_ts_str = (l_ts.isoformat() + "Z") if hasattr(l_ts, "isoformat") and not str(l_ts.isoformat()).endswith("Z") else str(l_ts)
        timeline_entries.append({
            "id": f"tl-log-{l.id}",
            "timestamp": l_ts_str,
            "_sort_key": l_ts,
            "phase": phase,
            "entry_type": entry_type,
            "source": "agent",
            "service": log_svc,
            "severity": "error" if l.level == "ERROR" else ("warning" if l.level == "WARNING" else "info"),
            "title": f"[{phase}] {l.level.replace('_', ' ').title()}",
            "description": l.message,
            "metadata": {
                "log_id": l.id,
                "level": l.level
            }
        })

    # Sort all entries chronologically by timestamp
    timeline_entries.sort(key=lambda x: x["_sort_key"] if isinstance(x["_sort_key"], datetime) else datetime.min)

    # Clean internal sort key before serializing
    for item in timeline_entries:
        item.pop("_sort_key", None)

    # Compute timeline summary metrics
    first_ts = timeline_entries[0]["timestamp"] if timeline_entries else None
    last_ts = timeline_entries[-1]["timestamp"] if timeline_entries else None
    duration_s = incident.resolution_time_seconds or 0.0
    if first_ts and last_ts:
        try:
            t0 = datetime.fromisoformat(first_ts)
            t1 = datetime.fromisoformat(last_ts)
            calculated_duration = (t1 - t0).total_seconds()
            if calculated_duration > 0 and duration_s == 0.0:
                duration_s = round(calculated_duration, 1)
        except Exception:
            pass

    return {
        "incident_id": incident.id,
        "service": incident.service,
        "alert_name": incident.alert_name,
        "status": incident.status,
        "severity": incident.severity,
        "total_timeline_entries": len(timeline_entries),
        "symptom_event_count": len(events),
        "agent_log_count": len(logs),
        "started_at": first_ts,
        "ended_at": last_ts,
        "duration_seconds": duration_s,
        "services_involved": list(set(services_seen + [incident.service])),
        "spread_sequence": services_seen,
        "impact": {
            "failed_transactions": incident.failed_transactions or 0,
            "failed_logins": incident.failed_logins or 0,
            "impact_summary": incident.impact_summary or ""
        },
        "timeline": timeline_entries
    }

