"""
Comprehensive Test Suite for Phase 1: Unified Event Schema, Storage & Multi-Source Ingestion
Tests:
1. Normalizer unit tests (AlertManager, API events, Plaintext logs, JSON logs)
2. Database Event model and relationship with Incident
3. FastAPI Endpoints:
   - POST /api/v1/events (single event ingestion)
   - POST /api/v1/events/batch (batch ingestion)
   - POST /api/v1/logs/upload (plaintext log upload)
   - POST /api/v1/logs/upload (JSON log upload)
   - GET /api/v1/events (filtering by service, severity, source)
   - GET /api/v1/events/{id}
   - POST /api/v1/alerts/webhook (AlertManager ingestion & event persistence)
   - GET /api/v1/incidents/{id} (incident details with correlated events)
"""

import os
import sys
import io
import json
import pytest

# Ensure backend directory is in python search path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from app.database import init_db, SessionLocal, Incident, Event, IncidentLog
from app.event_normalizer import (
    normalize_api_event,
    normalize_alertmanager_alert,
    normalize_log_line,
    parse_log_file_content,
    generate_event_id
)
from app.main import app

client = TestClient(app)

def setup_module():
    """Initialize database for tests."""
    init_db()

def test_event_normalizer_unit():
    # 1. API event normalization
    api_payload = {
        "service": "payment-service",
        "message": "Payment transaction timed out waiting for gateway",
        "severity": "ERROR",
        "trace_id": "tr-abc-123",
        "metadata": {"http_code": 504, "amount": 99.99}
    }
    norm_api = normalize_api_event(api_payload)
    assert norm_api["service"] == "payment-service"
    assert norm_api["severity"] == "error"
    assert norm_api["trace_id"] == "tr-abc-123"
    assert norm_api["source"] == "api"
    assert "EVT-" in norm_api["id"]

    # 2. AlertManager alert normalization
    alert_payload = {
        "status": "firing",
        "labels": {
            "alertname": "HighMemoryUsage",
            "service": "order-service",
            "severity": "critical",
            "instance": "order-service:8000"
        },
        "annotations": {
            "summary": "order-service RAM exceeds 80MB threshold"
        },
        "startsAt": "2026-11-09T10:00:00Z"
    }
    norm_alert = normalize_alertmanager_alert(alert_payload)
    assert norm_alert["service"] == "order-service"
    assert norm_alert["severity"] == "critical"
    assert norm_alert["source"] == "alertmanager"
    assert norm_alert["event_type"] == "alert"

    # 3. Plaintext log line parsing with trace ID and timestamp
    log_line = "[ERROR] 2026-11-09 10:15:30 - user-service authentication failed for user_id=402 trace_id=tr-usr-999"
    norm_log = normalize_log_line(log_line)
    assert norm_log is not None
    assert norm_log["service"] == "user-service"
    assert norm_log["severity"] == "error"
    assert norm_log["trace_id"] == "tr-usr-999"

    # 4. JSON log file parsing
    json_logs = json.dumps([
        {"service": "payment-service", "level": "WARN", "message": "Connection pool slow", "trace_id": "tr-pool-1"},
        {"service": "payment-service", "level": "ERROR", "message": "Transaction failed", "trace_id": "tr-pool-2"}
    ])
    parsed_json_events = parse_log_file_content(json_logs, "payment.json")
    assert len(parsed_json_events) == 2
    assert parsed_json_events[0]["severity"] == "warning"
    assert parsed_json_events[1]["severity"] == "error"

def test_api_ingest_single_event():
    payload = {
        "service": "user-service",
        "message": "User login rate limited on IP 192.168.1.1",
        "severity": "warning",
        "event_type": "security_alert",
        "trace_id": "tr-login-001",
        "metadata": {"attempts": 10}
    }
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    event = data["event"]
    assert event["service"] == "user-service"
    assert event["severity"] == "warning"
    assert event["trace_id"] == "tr-login-001"
    assert event["id"] is not None

def test_api_ingest_batch_events():
    batch = {
        "events": [
            {
                "service": "order-service",
                "message": "Checkout started for cart #1001",
                "severity": "info",
                "trace_id": "tr-batch-1"
            },
            {
                "service": "order-service",
                "message": "Checkout database write failure",
                "severity": "error",
                "trace_id": "tr-batch-1"
            }
        ]
    }
    response = client.post("/api/v1/events/batch", json=batch)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["count"] == 2
    assert len(data["events"]) == 2

def test_log_file_upload_plaintext():
    sample_log = (
        "[INFO] 2026-11-09 11:00:01 - payment-service started transaction #5501 trace_id=tr-pay-5501\n"
        "[WARNING] 2026-11-09 11:00:03 - payment-service connection pool delay 1500ms trace_id=tr-pay-5501\n"
        "[ERROR] 2026-11-09 11:00:05 - payment-service database timeout during commit trace_id=tr-pay-5501\n"
    )
    files = {"file": ("payment-service.log", io.BytesIO(sample_log.encode("utf-8")), "text/plain")}
    response = client.post("/api/v1/logs/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["events_ingested"] == 3
    assert data["service"] == "payment-service"

def test_log_file_upload_json():
    json_data = json.dumps([
        {"service": "api-gateway", "severity": "info", "message": "GET /api/v1/orders 200 OK", "trace_id": "tr-gw-1"},
        {"service": "api-gateway", "severity": "error", "message": "GET /api/v1/users 502 Bad Gateway", "trace_id": "tr-gw-2"}
    ])
    files = {"file": ("gateway_traffic.json", io.BytesIO(json_data.encode("utf-8")), "application/json")}
    response = client.post("/api/v1/logs/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["events_ingested"] == 2

def test_list_and_filter_events():
    # Query events for payment-service
    res = client.get("/api/v1/events?service=payment-service")
    assert res.status_code == 200
    events = res.json()
    assert isinstance(events, list)
    assert len(events) >= 1
    assert all(e["service"] == "payment-service" for e in events)

    # Query events with severity error
    res_err = client.get("/api/v1/events?severity=error")
    assert res_err.status_code == 200
    err_events = res_err.json()
    assert all(e["severity"] == "error" for e in err_events)

def test_get_single_event():
    # Ingest event then retrieve by ID
    ingest_res = client.post("/api/v1/events", json={
        "service": "notification-service",
        "message": "Push notification sent to user #401",
        "severity": "info"
    })
    event_id = ingest_res.json()["event"]["id"]

    get_res = client.get(f"/api/v1/events/{event_id}")
    assert get_res.status_code == 200
    event_data = get_res.json()
    assert event_data["id"] == event_id
    assert event_data["service"] == "notification-service"

def test_alertmanager_webhook_integration_and_incident_events(monkeypatch):
    monkeypatch.setattr("app.main.run_agent_workflow", lambda *args, **kwargs: None)
    webhook_payload = {
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HttpErrorSpike",
                    "instance": "order-service:8000",
                    "service": "order-service",
                    "severity": "critical"
                },
                "annotations": {
                    "summary": "Rapid increase in HTTP 500 responses on order-service"
                },
                "startsAt": "2026-11-09T11:30:00Z"
            }
        ]
    }
    webhook_res = client.post("/api/v1/alerts/webhook", json=webhook_payload)
    assert webhook_res.status_code == 200

    # Query incidents to find the created incident
    inc_res = client.get("/api/v1/incidents")
    assert inc_res.status_code == 200
    incidents = inc_res.json()
    order_inc = next((i for i in incidents if i["service"] == "order-service"), None)
    assert order_inc is not None

    # Verify incident details includes events list
    detail_res = client.get(f"/api/v1/incidents/{order_inc['id']}")
    assert detail_res.status_code == 200
    inc_detail = detail_res.json()
    assert "events" in inc_detail
    assert len(inc_detail["events"]) >= 1
    assert inc_detail["events"][0]["service"] == "order-service"

if __name__ == "__main__":
    pytest.main(["-v", __file__])

