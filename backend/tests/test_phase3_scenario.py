import os
import sys
import json
import pytest
import importlib.util
from datetime import datetime
from fastapi.testclient import TestClient

# Ensure backend directory is in path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app
from app.database import SessionLocal, Incident, Event, IncidentLog

client = TestClient(app)

@pytest.fixture(autouse=True)
def cleanup_active_test_incidents():
    """Ensure any existing active test incidents are marked RESOLVED before running tests."""
    db = SessionLocal()
    try:
        active = db.query(Incident).filter(
            Incident.status.in_(["INVESTIGATING", "ROOT_CAUSE_FOUND", "EXECUTING_FIX", "VERIFYING", "PENDING_APPROVAL"])
        ).all()
        for inc in active:
            inc.status = "RESOLVED"
        db.commit()
    finally:
        db.close()
    yield


def test_list_simulation_scenarios():
    """Scenario list endpoint returns the payment-platform-outage scenario with complete metadata."""
    resp = client.get("/api/v1/simulation/scenarios")
    assert resp.status_code == 200
    scenarios = resp.json()
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 1

    scenario_ids = [s["id"] for s in scenarios]
    assert "payment-platform-outage" in scenario_ids

    payment_scenario = next(s for s in scenarios if s["id"] == "payment-platform-outage")
    assert payment_scenario["root_cause_service"] == "database-service"
    assert "payment-service" in payment_scenario["affected_services"]
    assert "user-service" in payment_scenario["affected_services"]
    assert "order-service" in payment_scenario["affected_services"]
    assert "database-service" in payment_scenario["affected_services"]
    assert "user-service" in payment_scenario["symptoms"]
    assert "order-service" in payment_scenario["symptoms"]
    assert "payment-service" in payment_scenario["symptoms"]


def test_trigger_payment_platform_outage_scenario():
    """Triggering the scenario produces one master incident with all 3 correlated events and business impact."""
    payload = {
        "trace_id": "tr-test-scenario-01",
        "inject_mock_faults": False,
        "trigger_background_agent": False,
        "failed_transactions": 150,
        "failed_logins": 95,
        "impact_summary": "Test: Shared database connection pool saturation"
    }

    resp = client.post("/api/v1/simulation/scenario/payment-platform-outage", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert data["scenario"] == "payment-platform-outage"
    master_incident_id = data["master_incident_id"]
    assert master_incident_id.startswith("INC-")
    assert data["trace_id"] == "tr-test-scenario-01"
    assert data["correlated_events_count"] == 3
    assert data["impact"]["failed_transactions"] == 150
    assert data["impact"]["failed_logins"] == 95

    # Check affected services contains all 4
    for svc in ["payment-service", "user-service", "order-service", "database-service"]:
        assert svc in data["affected_services"]

    # Verify master incident in database
    db = SessionLocal()
    try:
        inc = db.query(Incident).filter(Incident.id == master_incident_id).first()
        assert inc is not None
        assert inc.alert_name == "DatabaseSaturation"
        assert inc.severity == "CRITICAL"
        assert inc.failed_transactions == 150
        assert inc.failed_logins == 95

        # Verify all 3 events are attached to this master incident
        events = db.query(Event).filter(Event.incident_id == master_incident_id).all()
        assert len(events) == 3

        sources = {e.source for e in events}
        services = {e.service for e in events}
        assert sources == {"alertmanager", "api", "logs"}
        assert services == {"payment-service", "user-service", "order-service"}

        # Verify timeline logs were written
        logs = db.query(IncidentLog).filter(IncidentLog.incident_id == master_incident_id).all()
        messages = " ".join([l.message for l in logs])
        assert "Challenge Scenario" in messages
        assert "Correlated 3 multi-source events" in messages
    finally:
        db.close()


def test_master_incident_correlated_events_api():
    """GET /api/v1/incidents/{incident_id}/correlated-events returns all 3 events and statistics."""
    payload = {
        "trace_id": "tr-test-scenario-02",
        "inject_mock_faults": False,
        "trigger_background_agent": False
    }

    resp = client.post("/api/v1/simulation/scenario/payment-platform-outage", json=payload)
    assert resp.status_code == 200
    master_incident_id = resp.json()["master_incident_id"]

    # Call correlated events API
    corr_resp = client.get(f"/api/v1/incidents/{master_incident_id}/correlated-events")
    assert corr_resp.status_code == 200
    corr_data = corr_resp.json()

    assert corr_data["incident_id"] == master_incident_id
    assert corr_data["total_correlated_events"] == 3
    assert set(corr_data["services_involved"]) == {"payment-service", "user-service", "order-service"}
    assert set(corr_data["sources"]) == {"alertmanager", "api", "logs"}


def test_scenario_isolation_from_unrelated_anomaly():
    """An unrelated anomaly (e.g. notification-service OOM) is NOT correlated into the payment outage."""
    payload = {
        "trace_id": "tr-test-scenario-03",
        "inject_mock_faults": False,
        "trigger_background_agent": False
    }

    resp = client.post("/api/v1/simulation/scenario/payment-platform-outage", json=payload)
    assert resp.status_code == 200
    master_incident_id = resp.json()["master_incident_id"]

    # Ingest an unrelated OOM event for notification-service
    unrelated_event = {
        "source": "api",
        "service": "notification-service",
        "event_type": "OutOfMemoryError",
        "severity": "critical",
        "message": "java.lang.OutOfMemoryError: Java heap space saturated during email rendering"
    }

    ev_resp = client.post("/api/v1/events", json=unrelated_event)
    assert ev_resp.status_code == 200
    ev_data = ev_resp.json()

    # Must NOT be attached to the payment outage incident
    assert ev_data["event"]["incident_id"] is None
    assert ev_data["event"]["incident_id"] != master_incident_id
    assert ev_data["correlation"]["action"] == "stored_unassigned"
    assert ev_data["correlation"]["correlation_score"] == 0.0


def test_mock_service_app_shared_db_saturation():
    """Verify mock-services app correctly simulates role-specific symptoms under shared DB saturation."""
    mock_app_path = os.path.abspath(os.path.join(backend_dir, "..", "simulation", "mock-services", "app.py"))
    spec = importlib.util.spec_from_file_location("mock_service_app", mock_app_path)
    mock_app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mock_app_module)

    # Test user-service simulation
    mock_app_module.SERVICE_NAME = "user-service"
    mock_app_module.FAULT_SHARED_DB_SATURATION = True

    mock_client = TestClient(mock_app_module.app)
    health_resp = mock_client.get("/health")
    assert health_resp.status_code == 500
    assert "Login failures active" in health_resp.json()["detail"]

    logs_resp = mock_client.get("/logs")
    assert logs_resp.status_code == 200
    assert "User auth pool exhausted" in logs_resp.text

    # Test order-service simulation
    mock_app_module.SERVICE_NAME = "order-service"
    health_resp = mock_client.get("/health")
    assert health_resp.status_code == 500
    assert "Order DB pool exhausted" in health_resp.json()["detail"]

    logs_resp = mock_client.get("/logs")
    assert logs_resp.status_code == 200
    assert "504 Gateway Timeout" in logs_resp.text

    # Test payment-service simulation
    mock_app_module.SERVICE_NAME = "payment-service"
    health_resp = mock_client.get("/health")
    assert health_resp.status_code == 500
    assert "Payment transaction commit failed" in health_resp.json()["detail"]

    logs_resp = mock_client.get("/logs")
    assert logs_resp.status_code == 200
    assert "Payment ledger transaction rollback" in logs_resp.text

    # Clear faults
    clear_resp = mock_client.post("/fault/clear")
    assert clear_resp.status_code == 200
    assert mock_app_module.FAULT_SHARED_DB_SATURATION is False

    clean_health = mock_client.get("/health")
    assert clean_health.status_code == 200
