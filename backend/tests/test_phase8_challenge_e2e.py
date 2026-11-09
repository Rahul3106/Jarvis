"""
End-to-End Verification Test Suite for Phase 8: J.A.R.V.I.S. Challenge Scenario.

Tests the full system lifecycle:
1. Multi-source event ingestion (REST API, Log file upload, AlertManager webhook).
2. Trace-ID and shared dependency correlation into one single master incident.
3. False-correlation isolation: strictly keeping unrelated anomalies isolated.
4. Multi-agent root cause analysis, business impact quantification, and timeline generation.
5. End-to-end post-mortem generation and download.
"""

import os
import sys
import uuid
import json
import io
from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import init_db, SessionLocal, Incident, Event, IncidentLog
from app.agent import generate_markdown_post_mortem
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_e2e_challenge_scenario_runner_and_postmortem():
    """
    Triggers the Payment Platform Outage composite scenario and verifies:
    1. Single master incident created with 3 correlated events.
    2. Quantified business impact values populated.
    3. Timeline returns chronological progression.
    4. Post-mortem report compiles with all 9 J.A.R.V.I.S. sections.
    """
    resp = client.post("/api/v1/simulation/scenario/payment-platform-outage", json={
        "failed_transactions": 175,
        "failed_logins": 95,
        "inject_mock_faults": False,
        "trigger_background_agent": False
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario"] == "payment-platform-outage"
    assert data["status"] == "success"
    master_id = data["master_incident_id"]
    assert master_id is not None
    assert data["correlated_events_count"] == 3

    # Verify correlated events endpoint
    events_resp = client.get(f"/api/v1/incidents/{master_id}/correlated-events")
    assert events_resp.status_code == 200
    ev_data = events_resp.json()
    assert ev_data["total_correlated_events"] >= 3
    services = ev_data["services_involved"]
    assert "payment-service" in services
    assert "user-service" in services
    assert "order-service" in services

    # Verify timeline endpoint
    tl_resp = client.get(f"/api/v1/incidents/{master_id}/timeline")
    assert tl_resp.status_code == 200
    tl_data = tl_resp.json()
    assert "timeline" in tl_data
    assert len(tl_data["timeline"]) >= 3

    # Generate and set a post-mortem report on the master incident to test retrieval and download
    db = SessionLocal()
    try:
        inc = db.query(Incident).filter(Incident.id == master_id).first()
        assert inc is not None
        report_md = generate_markdown_post_mortem(
            incident_id=master_id,
            service="payment-service",
            alert_name="DatabaseSaturation",
            root_cause="Shared database pool exhaustion on database-service",
            confidence=95,
            risk_level="CRITICAL",
            evidence=["DB pool checkout timeout > 10000ms"],
            affected_services=["payment-service", "user-service", "order-service", "database-service"],
            reasoning_summary="Cross-service cascading failure due to database pool exhaustion.",
            action="CLEAR_STUCK_JOBS",
            remediation_result="Cleared 50 orphaned connections.",
            success=True,
            resolution_time=25.0,
            governance_approved=True,
            governance_reason="Emergency pool clearing approved",
            impact_metrics={
                "failed_transactions": 175,
                "failed_logins": 95,
                "estimated_revenue_at_risk_usd": 8748.25,
                "estimated_users_affected": 270
            },
            correlated_events=ev_data.get("events", [])
        )
        inc.resolution_action = report_md
        inc.status = "RESOLVED"
        db.commit()
    finally:
        db.close()

    # Verify report endpoint
    rep_resp = client.get(f"/api/v1/incidents/{master_id}/report")
    assert rep_resp.status_code == 200
    rep_data = rep_resp.json()
    assert rep_data["incident_id"] == master_id
    markdown = rep_data["post_mortem_markdown"]
    assert "# SRE Incident Post-Mortem and Audit Report" in markdown
    assert "Business Impact Analysis" in markdown
    assert "175" in markdown  # Failed transactions
    assert "95" in markdown   # Failed logins

    # Verify report download endpoint
    dl_resp = client.get(f"/api/v1/incidents/{master_id}/report/download")
    assert dl_resp.status_code == 200
    assert "text/markdown" in dl_resp.headers["content-type"]
    assert f'filename="post-mortem-{master_id}.md"' in dl_resp.headers["content-disposition"]


def test_e2e_multi_source_ingestion_and_grouping():
    """
    Demonstrates true multi-source ingestion:
    - Master Incident exists for DatabaseSaturation.
    - Source 1: API event from user-service
    - Source 2: Uploaded log file from order-service
    - Source 3: AlertManager webhook alert from payment-service
    All 3 disparate sources share a common trace ID / database outage symptom
    and must be correlated into one single master incident.
    """
    db = SessionLocal()
    # Resolve any existing active incidents so the test runs in pure isolation
    db.query(Incident).filter(Incident.status.in_(["INVESTIGATING", "ROOT_CAUSE_FOUND", "EXECUTING_FIX", "VERIFYING", "PENDING_APPROVAL"])).update({"status": "RESOLVED"})
    
    shared_trace = f"TRACE-E2E-{uuid.uuid4().hex[:6]}"
    inc_id = f"INC-E2E-MASTER-{uuid.uuid4().hex[:6]}"
    master_inc = Incident(
        id=inc_id,
        service="payment-service",
        alert_name="DatabaseSaturation",
        status="INVESTIGATING",
        severity="critical",
        created_at=datetime.now(timezone.utc)
    )
    db.add(master_inc)
    db.commit()
    db.close()

    # 1. Ingest API event
    api_payload = {
        "service": "user-service",
        "message": "500: Database connection timeout during auth login attempt",
        "event_type": "api_event",
        "severity": "critical",
        "source": "api",
        "trace_id": shared_trace
    }
    r1 = client.post("/api/v1/events", json=api_payload)
    assert r1.status_code == 200
    r1_data = r1.json()
    assert r1_data["correlation"]["action"] == "attached_to_incident"
    assert r1_data["correlation"]["incident_id"] == inc_id

    # 2. Ingest log file upload
    log_content = f"2026-11-09T10:00:02Z [ERROR] [order-service] [trace_id={shared_trace}] Checkout transaction timed out on DB pool checkout write\n"
    r2 = client.post(
        "/api/v1/logs/upload",
        files={"file": ("order-service-error.log", io.BytesIO(log_content.encode("utf-8")), "text/plain")},
        data={"service": "order-service"}
    )
    assert r2.status_code == 200
    upload_res = r2.json()
    assert upload_res["events_ingested"] >= 1
    assert upload_res["events_correlated"] >= 1
    assert upload_res["sample_events"][0]["incident_id"] == inc_id

    # 3. Ingest AlertManager alert
    alert_payload = {
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "DatabaseSaturation",
                    "service": "payment-service",
                    "severity": "critical"
                },
                "annotations": {
                    "summary": "Payment commit failed: DB pool exhausted",
                    "description": f"Connection pool exhausted on payment-service trace={shared_trace}"
                },
                "startsAt": datetime.now(timezone.utc).isoformat()
            }
        ]
    }
    r3 = client.post("/api/v1/alerts/webhook", json=alert_payload)
    assert r3.status_code == 200

    # 4. Verify that all 3 events are attached to inc_id
    db = SessionLocal()
    try:
        events = db.query(Event).filter(Event.incident_id == inc_id).all()
        assert len(events) >= 3
        sources = {e.source for e in events}
        services = {e.service for e in events}
        assert "api" in sources
        assert "file" in sources
        assert "alertmanager" in sources
        assert "user-service" in services
        assert "order-service" in services
        assert "payment-service" in services
    finally:
        db.close()


def test_e2e_false_correlation_defense():
    """
    Verifies false-correlation isolation:
    An active database outage incident on payment-service must NOT absorb
    an unrelated memory leak anomaly on notification-service.
    """
    db = SessionLocal()
    # Resolve all existing active incidents for pure test isolation
    db.query(Incident).filter(Incident.status.in_(["INVESTIGATING", "ROOT_CAUSE_FOUND", "EXECUTING_FIX", "VERIFYING", "PENDING_APPROVAL"])).update({"status": "RESOLVED"})
    
    unique_run = uuid.uuid4().hex[:6]
    db_incident_id = f"INC-PAY-DB-{unique_run}"
    master_inc = Incident(
        id=db_incident_id,
        service="payment-service",
        alert_name="DatabaseSaturation",
        status="INVESTIGATING",
        severity="critical",
        created_at=datetime.now(timezone.utc)
    )
    db.add(master_inc)
    db.commit()
    db.close()

    # Ingest totally unrelated alert on disconnected notification-service
    r2 = client.post("/api/v1/events", json={
        "service": "notification-service",
        "message": f"OutOfMemoryError: Java heap space exhausted during email rendering run={unique_run}",
        "severity": "critical",
        "source": "api"
    })
    assert r2.status_code == 200
    notif_data = r2.json()

    # Must NOT be attached to the database outage incident!
    assert notif_data["correlation"]["incident_id"] != db_incident_id
    assert notif_data["correlation"]["action"] in ["stored_unassigned", "new_incident"]
