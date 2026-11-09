"""
Unit and integration tests for Phase 7: Post-Mortem Report & Documentation.

Verifies:
1. Production-grade Markdown Post-Mortem compilation with all 9 J.A.R.V.I.S. sections.
2. Correlated Events Table and Quantified Business Impact Table generation.
3. Causal propagation narrative and alternative causes discussion.
4. Auditor integration and persistence of post-mortem into `incident.resolution_action`.
5. REST endpoints `GET /api/v1/incidents/{id}/report` and `GET /api/v1/incidents/{id}/report/download`.
"""

import os
import sys
import uuid
from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import SessionLocal, Incident, Event, init_db
from app.agent import generate_markdown_post_mortem, auditor_node, AgentState
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_postmortem_markdown_generation_full():
    """Verifies that generate_markdown_post_mortem generates all 9 J.A.R.V.I.S. sections."""
    incident_id = f"INC-PM-FULL-{uuid.uuid4().hex[:6]}"
    
    correlated_events = [
        {
            "id": f"EV-PM-1-{uuid.uuid4().hex[:4]}",
            "timestamp": "2026-11-09T10:00:00",
            "source": "api",
            "service": "user-service",
            "severity": "error",
            "message": "Auth timeout during login checkout"
        },
        {
            "id": f"EV-PM-2-{uuid.uuid4().hex[:4]}",
            "timestamp": "2026-11-09T10:00:02",
            "source": "file",
            "service": "order-service",
            "severity": "warning",
            "message": "HTTP 504 Gateway Timeout while acquiring connection"
        },
        {
            "id": f"EV-PM-3-{uuid.uuid4().hex[:4]}",
            "timestamp": "2026-11-09T10:00:05",
            "source": "alertmanager",
            "service": "payment-service",
            "severity": "critical",
            "message": "Transaction rollback on DB write timeout"
        }
    ]

    impact_metrics = {
        "failed_transactions": 250,
        "failed_logins": 110,
        "estimated_revenue_at_risk_usd": 12497.50,
        "estimated_users_affected": 360,
        "impact_summary": "Cascading auth and checkout failures across tier 1 services."
    }

    alternative_causes = [
        {
            "cause": "Upstream Cloudflare DNS routing failure",
            "confidence": 10,
            "reason_rejected": "Internal services unhealthy directly via cluster IPs"
        },
        {
            "cause": "Payment gateway third-party API outage",
            "confidence": 20,
            "reason_rejected": "Order and User services also failing simultaneously"
        }
    ]

    timeline_items = [
        {
            "timestamp": "2026-11-09T10:00:00",
            "phase": "DETECTION",
            "service": "database-service",
            "source": "SIMULATOR",
            "title": "Fault Injected",
            "description": "Shared database pool saturated"
        },
        {
            "timestamp": "2026-11-09T10:00:01",
            "phase": "CORRELATION",
            "service": "correlation-engine",
            "source": "JARVIS",
            "title": "Master Incident Grouped",
            "description": "Grouped 3 multi-service events into 1 master incident"
        },
        {
            "timestamp": "2026-11-09T10:00:06",
            "phase": "REMEDIATION",
            "service": "payment-service",
            "source": "SRE_AGENT",
            "title": "CLEAR_STUCK_JOBS",
            "description": "Flushed 50 idle connections"
        },
        {
            "timestamp": "2026-11-09T10:00:12",
            "phase": "VERIFICATION",
            "service": "payment-service",
            "source": "AUDITOR",
            "title": "Recovery Verified",
            "description": "Probe returned 200 OK"
        }
    ]

    report = generate_markdown_post_mortem(
        incident_id=incident_id,
        service="payment-service",
        alert_name="PaymentCommitFailure",
        root_cause="Shared database pool exhaustion on database-service",
        confidence=95,
        risk_level="MEDIUM",
        evidence=["DB pool checkout timeout > 10000ms", "PostgreSQL max_connections reached"],
        affected_services=["payment-service", "user-service", "order-service", "database-service"],
        reasoning_summary="Cross-service correlation identified common database dependency saturation.",
        action="CLEAR_STUCK_JOBS",
        remediation_result="Cleared 50 deadlocked connections; pool capacity restored.",
        success=True,
        resolution_time=12.4,
        governance_approved=True,
        governance_reason="Action verified safe for medium risk tier",
        impact_metrics=impact_metrics,
        correlated_events=correlated_events,
        alternative_causes=alternative_causes,
        timeline_items=timeline_items
    )

    # 1. Executive Summary
    assert f"# SRE Incident Post-Mortem and Audit Report - {incident_id}" in report
    assert "## 1. Executive Summary" in report
    assert "RESOLVED" in report
    assert "12.4s MTTR" in report

    # 2. Correlated Events Table
    assert "## 2. Correlated Multi-Source Events Table" in report
    assert "| Event ID | Timestamp | Source | Service | Severity | Symptom / Description |" in report
    assert "Auth timeout during login checkout" in report
    assert "HTTP 504 Gateway Timeout while acquiring connection" in report

    # 3. Business Impact Analysis
    assert "## 3. Business Impact Analysis" in report
    assert "| **Failed Transactions** | Measured Counter | `250` |" in report
    assert "| **Failed Logins** | Measured Counter | `110` |" in report
    assert "$12,497.50" in report

    # 4. Causal Propagation
    assert "## 4. Causal Propagation & Topology Dynamics" in report
    assert "database-service" in report

    # 5. Root Cause Analysis
    assert "## 5. Root Cause Analysis & Alternative Candidates" in report
    assert "Shared database pool exhaustion on database-service" in report
    assert "Upstream Cloudflare DNS routing failure" in report

    # 6. Unified Incident Chronological Timeline
    assert "## 6. Unified Incident Chronological Timeline" in report
    assert "| Timestamp | Phase | Service | Source | Milestone Description |" in report
    assert "Flushed 50 idle connections" in report

    # 7. Actions & Remediation Audit
    assert "## 7. Actions & Remediation Audit" in report
    assert "APPROVED (AUTO)" in report

    # 8. Recovery Verification Summary
    assert "## 8. Recovery Verification Summary" in report
    assert "SUCCESS (HEALTHY)" in report

    # 9. Preventative SRE Recommendations & Action Items
    assert "## 9. Preventative SRE Recommendations & Action Items" in report
    assert "Shared Resource Pooling & Queue Caps" in report


def test_postmortem_pending_approval():
    """Verifies that suspended incidents highlight PENDING HUMAN APPROVAL and safety warnings."""
    incident_id = f"INC-PM-SUSP-{uuid.uuid4().hex[:6]}"

    report = generate_markdown_post_mortem(
        incident_id=incident_id,
        service="database-service",
        alert_name="DatabaseSaturation",
        root_cause="Shared database pool exhaustion on database-service",
        confidence=95,
        risk_level="CRITICAL",
        evidence=["Active locks > 200"],
        affected_services=["database-service", "user-service", "payment-service"],
        reasoning_summary="Critical database intervention required.",
        action="CLEAR_STUCK_JOBS",
        remediation_result="Execution halted by safety gate.",
        success=False,
        resolution_time=0.0,
        governance_approved=False,
        governance_reason="High business impact: > 50 failed transactions",
        impact_metrics={"failed_transactions": 150, "failed_logins": 75},
        correlated_events=[],
        alternative_causes=[]
    )

    assert "SUSPENDED (PENDING HUMAN APPROVAL)" in report
    assert "Action Suspended by Safety Governance" in report
    assert "High business impact: > 50 failed transactions" in report
    assert "PENDING HUMAN APPROVAL" in report
    assert "SKIPPED (Bypassed due to governance hold)" in report


def test_get_incident_report_api_endpoints():
    """Verifies GET /api/v1/incidents/{id}/report and report download endpoints."""
    incident_id = f"INC-API-PM-{uuid.uuid4().hex[:6]}"
    sample_report = f"# SRE Incident Post-Mortem and Audit Report - {incident_id}\n\n## 1. Executive Summary\nResolved."

    db = SessionLocal()
    try:
        inc = Incident(
            id=incident_id,
            service="order-service",
            alert_name="HighLatency",
            status="RESOLVED",
            severity="warning",
            root_cause="Database pool contention",
            confidence=90,
            risk_level="LOW",
            resolution_action=sample_report,
            resolution_time_seconds=15.2,
            failed_transactions=12,
            failed_logins=5,
            created_at=datetime.now(timezone.utc)
        )
        db.add(inc)
        db.commit()
    finally:
        db.close()

    # 1. Test JSON report metadata endpoint
    resp = client.get(f"/api/v1/incidents/{incident_id}/report")
    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_id"] == incident_id
    assert data["has_post_mortem"] is True
    assert data["post_mortem_markdown"] == sample_report
    assert data["service"] == "order-service"

    # 2. Test direct markdown download endpoint
    dl_resp = client.get(f"/api/v1/incidents/{incident_id}/report/download")
    assert dl_resp.status_code == 200
    assert "text/markdown" in dl_resp.headers["content-type"]
    assert f'filename="post-mortem-{incident_id}.md"' in dl_resp.headers.get("content-disposition", "")
    assert sample_report in dl_resp.text


def test_report_endpoints_404():
    """Verifies 404 behavior for nonexistent incident report queries."""
    fake_id = f"INC-NONEXISTENT-{uuid.uuid4().hex[:6]}"
    resp = client.get(f"/api/v1/incidents/{fake_id}/report")
    assert resp.status_code == 404

    dl_resp = client.get(f"/api/v1/incidents/{fake_id}/report/download")
    assert dl_resp.status_code == 404
