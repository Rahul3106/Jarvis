import os
import sys
import uuid
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

# Ensure backend directory is in path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app
from app.database import SessionLocal, Incident, Event, IncidentLog
from app.timeline import build_incident_timeline, TimelinePhase, TimelineEntryType

client = TestClient(app)

@pytest.fixture(autouse=True)
def cleanup_test_timeline_data():
    """Clean up test incidents before and after running tests."""
    db = SessionLocal()
    try:
        db.query(Event).filter(
            (Event.id.like("evt-tl%")) | (Event.incident_id.like("INC-TEST-TL%"))
        ).delete(synchronize_session=False)

        active = db.query(Incident).filter(
            Incident.id.like("INC-TEST-TL%")
        ).all()
        for inc in active:
            db.delete(inc)
        db.commit()
    finally:
        db.close()
    yield


def test_timeline_generation_multi_service_incident():
    """Timeline aggregator merges symptoms, lifecycle events, and agent logs in chronological order."""
    inc_id = f"INC-TEST-TL-{uuid.uuid4().hex[:6]}"
    now = datetime.utcnow()
    t0 = now - timedelta(seconds=20)
    t1 = now - timedelta(seconds=15)
    t2 = now - timedelta(seconds=10)
    t3 = now - timedelta(seconds=5)
    t4 = now

    db = SessionLocal()
    try:
        # 1. Incident
        inc = Incident(
            id=inc_id,
            service="payment-service",
            alert_name="DatabaseSaturation",
            severity="CRITICAL",
            status="RESOLVED",
            resolution_time_seconds=20.0,
            failed_transactions=142,
            failed_logins=89,
            impact_summary="Test: Shared DB Saturation cascade",
            created_at=t0
        )
        db.add(inc)

        # 2. Symptoms in chronological sequence across services
        evt1 = Event(
            id=f"evt-tl-01-{uuid.uuid4().hex[:6]}",
            incident_id=inc_id,
            source="alertmanager",
            service="payment-service",
            event_type="alert",
            severity="critical",
            timestamp=t0,
            message="DatabaseSaturation: Payment transaction rollback on shared postgres connection"
        )
        evt2 = Event(
            id=f"evt-tl-02-{uuid.uuid4().hex[:6]}",
            incident_id=inc_id,
            source="api",
            service="user-service",
            event_type="UserLoginFailed",
            severity="error",
            timestamp=t1,
            message="DatabaseSaturation: Auth pool exhausted. 89 login failures."
        )
        evt3 = Event(
            id=f"evt-tl-03-{uuid.uuid4().hex[:6]}",
            incident_id=inc_id,
            source="logs",
            service="order-service",
            event_type="SlowApiResponseTimeout",
            severity="warning",
            timestamp=t2,
            message="DatabaseSaturation: Slow API response and 504 checkout timeout"
        )
        db.add(evt1)
        db.add(evt2)
        db.add(evt3)

        # 3. Agent Execution Logs
        db.add(IncidentLog(
            incident_id=inc_id,
            level="INFO",
            message="[Diagnostics Agent] Root cause: Shared database connection pool exhaustion",
            timestamp=t3
        ))
        db.add(IncidentLog(
            incident_id=inc_id,
            level="INFO",
            message="[Remediation Executor] Action: CLEAR_STUCK_JOBS executed successfully",
            timestamp=t4
        ))
        db.commit()

        # Build timeline
        timeline_result = build_incident_timeline(db, inc_id)
        assert timeline_result is not None
        assert timeline_result["incident_id"] == inc_id
        assert timeline_result["symptom_event_count"] == 3
        assert timeline_result["agent_log_count"] == 2
        assert timeline_result["impact"]["failed_transactions"] == 142
        assert timeline_result["impact"]["failed_logins"] == 89

        # Spread sequence must record progression across services
        assert timeline_result["spread_sequence"] == ["payment-service", "user-service", "order-service"]

        entries = timeline_result["timeline"]
        assert len(entries) >= 6

        # Verify strict chronological sorting
        for i in range(len(entries) - 1):
            assert entries[i]["timestamp"] <= entries[i + 1]["timestamp"]

        # Verify entry phases exist
        phases = {e["phase"] for e in entries}
        assert TimelinePhase.DETECTION in phases
        assert TimelinePhase.DIAGNOSIS in phases
        assert TimelinePhase.REMEDIATION in phases
        assert TimelinePhase.LIFECYCLE in phases
    finally:
        db.close()


def test_timeline_api_endpoint():
    """GET /api/v1/incidents/{incident_id}/timeline returns full chronological data for challenge scenario."""
    # 1. Trigger Scenario
    scenario_payload = {
        "trace_id": "tr-timeline-api-01",
        "inject_mock_faults": False,
        "trigger_background_agent": False
    }
    sc_resp = client.post("/api/v1/simulation/scenario/payment-platform-outage", json=scenario_payload)
    assert sc_resp.status_code == 200
    master_incident_id = sc_resp.json()["master_incident_id"]

    # 2. Call Timeline API
    tl_resp = client.get(f"/api/v1/incidents/{master_incident_id}/timeline")
    assert tl_resp.status_code == 200
    tl_data = tl_resp.json()

    assert tl_data["incident_id"] == master_incident_id
    assert tl_data["symptom_event_count"] == 3
    assert tl_data["total_timeline_entries"] >= 4
    assert "payment-service" in tl_data["services_involved"]
    assert "user-service" in tl_data["services_involved"]
    assert "order-service" in tl_data["services_involved"]

    # Check entries have required fields
    for entry in tl_data["timeline"]:
        assert "id" in entry
        assert "timestamp" in entry
        assert "phase" in entry
        assert "entry_type" in entry
        assert "service" in entry
        assert "title" in entry
        assert "description" in entry


def test_timeline_not_found():
    """GET /api/v1/incidents/{incident_id}/timeline returns 404 for non-existent incident."""
    resp = client.get("/api/v1/incidents/INC-NONEXISTENT-9999/timeline")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Incident not found"

