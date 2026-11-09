"""
Comprehensive Test Suite for Phase 2: Dedicated Event Correlation & Incident Grouping Engine
Tests:
1. Topology module: call graph, reverse graph, shared infrastructure dependencies, distances.
2. Correlation scoring:
   - Trace ID match override (Score = 1.0)
   - Shared dependency correlation (user-service + payment-service DB saturation -> Score > 0.70)
   - False correlation protection (notification-service OOM + user-service DB timeout -> Score < 0.40)
   - Time window decay (events > 35s apart -> Score = 0.0)
3. Endpoints:
   - GET /api/v1/topology
   - POST /api/v1/correlation/evaluate
   - Ingestion correlation: multi-service symptoms grouping into one incident
   - False-grouping check: unrelated anomaly kept separate
   - GET /api/v1/incidents/{id}/correlated-events
"""

import os
import sys
import json
import pytest
from datetime import datetime, timedelta

# Ensure backend directory is in python search path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from app.database import init_db, SessionLocal, Incident, Event, IncidentLog
from app.topology import (
    get_topology_graph,
    get_downstream_services,
    get_upstream_services,
    get_shared_dependencies,
    get_topological_distance,
    are_services_topologically_related
)
from app.correlation import (
    correlation_engine,
    extract_error_signatures,
    signatures_are_causally_compatible
)
from app.main import app

client = TestClient(app)

def setup_module():
    """Initialize database for tests."""
    init_db()

# ── 1. Topology Unit Tests ───────────────────────────────────────────────

def test_topology_graph_and_dependencies():
    topo = get_topology_graph()
    assert "api-gateway" in topo["services"]
    assert "database-service" in topo["services"]
    assert "user-service" in topo["call_graph"]["api-gateway"]
    assert "order-service" in topo["call_graph"]["api-gateway"]

    # Shared DB dependencies
    shared_user_payment = get_shared_dependencies("user-service", "payment-service")
    assert "database-service" in shared_user_payment

    shared_user_order = get_shared_dependencies("user-service", "order-service")
    assert "database-service" in shared_user_order

    # Topological distance checks
    assert get_topological_distance("user-service", "user-service") == 0
    assert get_topological_distance("user-service", "payment-service") == 1  # shared DB
    assert get_topological_distance("api-gateway", "user-service") == 1      # direct call
    assert get_topological_distance("api-gateway", "payment-service") == 2   # 2-hop

    # Connectedness
    assert are_services_topologically_related("user-service", "payment-service") is True
    assert are_services_topologically_related("api-gateway", "payment-service") is True

# ── 2. Correlation Engine Unit Tests ────────────────────────────────────

def test_trace_id_override_correlation():
    event_a = {
        "service": "api-gateway",
        "message": "Gateway timeout 504 on POST /checkout",
        "trace_id": "tr-shared-trace-999",
        "timestamp": datetime.utcnow()
    }
    event_b = {
        "service": "payment-service",
        "message": "Payment processing failed",
        "trace_id": "tr-shared-trace-999",
        "timestamp": datetime.utcnow()
    }
    score = correlation_engine.compute_event_correlation(event_a, event_b)
    assert score == 1.0, f"Expected 1.0 for trace ID match, got {score}"

def test_shared_dependency_correlation():
    """Tests that user-service login failure and payment-service transaction failure correlate via shared DB."""
    now = datetime.utcnow()
    event_user = {
        "service": "user-service",
        "message": "Database connection pool timeout during user login authentication",
        "timestamp": now
    }
    event_payment = {
        "service": "payment-service",
        "message": "Payment transaction commit failed: postgres database saturation",
        "timestamp": now + timedelta(seconds=4)
    }
    score = correlation_engine.compute_event_correlation(event_user, event_payment)
    assert score >= 0.70, f"Expected score >= 0.70 for shared DB failure, got {score}"

def test_false_correlation_protection():
    """
    CRITICAL J.A.R.V.I.S. Requirement:
    Two unrelated failures occurring in the same time window remain separate incidents.
    e.g., notification-service memory leak vs user-service database timeout.
    """
    now = datetime.utcnow()
    event_user_db = {
        "service": "user-service",
        "message": "Database connection pool exhausted during login",
        "timestamp": now
    }
    event_notif_oom = {
        "service": "notification-service",
        "message": "java.lang.OutOfMemoryError: Java heap space in worker thread",
        "timestamp": now + timedelta(seconds=1)
    }
    score = correlation_engine.compute_event_correlation(event_user_db, event_notif_oom)
    assert score < 0.40, f"Expected score < 0.40 for unrelated failures, got {score}"

def test_time_window_decay():
    """Events occurring beyond the time window must not correlate."""
    now = datetime.utcnow()
    event_old = {
        "service": "user-service",
        "message": "Database connection timeout",
        "timestamp": now - timedelta(seconds=60)
    }
    event_new = {
        "service": "payment-service",
        "message": "Database connection timeout",
        "timestamp": now
    }
    score = correlation_engine.compute_event_correlation(event_old, event_new)
    assert score == 0.0, f"Expected score 0.0 for events outside time window, got {score}"

# ── 3. API Endpoints & Multi-Service Grouping Tests ───────────────────────

def test_get_topology_endpoint():
    res = client.get("/api/v1/topology")
    assert res.status_code == 200
    data = res.json()
    assert "services" in data
    assert "call_graph" in data
    assert "infrastructure_dependencies" in data
    assert "database-service" in data["infrastructure_dependencies"]

def test_evaluate_correlation_endpoint():
    payload = {
        "event_a": {
            "service": "user-service",
            "message": "Database checkout timeout after 3000ms"
        },
        "event_b": {
            "service": "order-service",
            "message": "DatabaseSaturation: connection pool queue full"
        }
    }
    res = client.post("/api/v1/correlation/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["is_correlated"] is True
    assert data["score"] >= 0.60
    assert "database-service" in data["shared_dependencies"]

def test_multi_service_incident_grouping_and_false_grouping_isolation():
    """
    End-to-End Incident Grouping Verification:
    1. Create an active incident on user-service due to DatabaseSaturation.
    2. Ingest payment-service event with DatabaseSaturation -> must group into SAME incident.
    3. Ingest order-service event with DatabaseSaturation -> must group into SAME incident.
    4. Ingest notification-service event with OutOfMemoryError -> must NOT group (false grouping prevented).
    """
    db = SessionLocal()
    # Clean up all active incidents so only this new test incident is active
    db.query(Incident).filter(Incident.status.in_(["INVESTIGATING", "ROOT_CAUSE_FOUND", "EXECUTING_FIX", "VERIFYING", "PENDING_APPROVAL"])).update({"status": "RESOLVED"})
    db.commit()

    # 1. Setup active master incident
    inc_id = f"INC-CORR-TEST-{datetime.utcnow().strftime('%H%M%S')}"
    master_inc = Incident(
        id=inc_id,
        service="user-service",
        alert_name="DatabaseSaturation",
        status="INVESTIGATING",
        severity="critical",
        created_at=datetime.utcnow()
    )
    db.add(master_inc)
    db.commit()
    db.close()

    # 2. Ingest payment-service DB event
    res_pay = client.post("/api/v1/events", json={
        "service": "payment-service",
        "message": "Payment failed: DatabaseSaturation connection pool exhausted",
        "severity": "critical"
    })
    assert res_pay.status_code == 200
    pay_data = res_pay.json()
    assert pay_data["correlation"]["action"] == "attached_to_incident"
    assert pay_data["correlation"]["incident_id"] == inc_id

    # 3. Ingest order-service DB event
    res_ord = client.post("/api/v1/events", json={
        "service": "order-service",
        "message": "Order checkout timed out on database postgres write",
        "severity": "critical"
    })
    assert res_ord.status_code == 200
    ord_data = res_ord.json()
    assert ord_data["correlation"]["action"] == "attached_to_incident"
    assert ord_data["correlation"]["incident_id"] == inc_id

    # 4. Ingest unrelated notification-service OOM event -> MUST NOT group into inc_id
    res_notif = client.post("/api/v1/events", json={
        "service": "notification-service",
        "message": "OutOfMemoryError in notification email queue worker",
        "severity": "critical"
    })
    assert res_notif.status_code == 200
    notif_data = res_notif.json()
    # Action should be stored_unassigned or NOT attached to inc_id
    assert notif_data["correlation"]["incident_id"] != inc_id

    # 5. Verify incident's correlated-events endpoint
    corr_res = client.get(f"/api/v1/incidents/{inc_id}/correlated-events")
    assert corr_res.status_code == 200
    corr_data = corr_res.json()
    assert corr_data["total_correlated_events"] >= 2
    assert "user-service" in corr_data["services_involved"] or "payment-service" in corr_data["services_involved"]
    assert "order-service" in corr_data["services_involved"]

if __name__ == "__main__":
    pytest.main(["-v", __file__])

