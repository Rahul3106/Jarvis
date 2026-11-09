import os
import sys
import json
import uuid
import pytest
from datetime import datetime

# Ensure backend directory is in path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import SessionLocal, Incident, Event, IncidentLog
from app.sre_system_prompt import build_investigation_prompt, build_audit_report_prompt
from app.agent import (
    _heuristic_diagnosis,
    diagnostics_agent_node,
    governance_safety_agent_node,
    auditor_node,
    AgentState
)

@pytest.fixture(autouse=True)
def cleanup_test_incidents():
    """Ensure any existing test incidents and events are cleaned up."""
    db = SessionLocal()
    try:
        db.query(Event).filter(
            (Event.id.like("evt-p4%")) | (Event.incident_id.like("INC-TEST-PH4%"))
        ).delete(synchronize_session=False)

        active = db.query(Incident).filter(
            Incident.id.like("INC-TEST-PH4%")
        ).all()
        for inc in active:
            db.delete(inc)
        db.commit()
    finally:
        db.close()
    yield


def test_heuristic_diagnosis_multi_service_payment_outage():
    """Multi-service correlated events trigger shared database outage diagnosis with alternative causes."""
    correlated_events = [
        {
            "service": "payment-service",
            "source": "alertmanager",
            "message": "DatabaseSaturation: Payment transaction commit failed. Ledger write timeout on shared postgres.",
            "timestamp": "2026-11-09T10:00:00"
        },
        {
            "service": "user-service",
            "source": "api",
            "message": "DatabaseSaturation: User auth pool exhausted. Login failures spiking across web & mobile.",
            "timestamp": "2026-11-09T10:00:02"
        },
        {
            "service": "order-service",
            "source": "logs",
            "message": "DatabaseSaturation: Slow API latency and 504 Gateway Timeout on checkout order commit.",
            "timestamp": "2026-11-09T10:00:04"
        }
    ]
    impact_metrics = {
        "failed_transactions": 142,
        "failed_logins": 89,
        "impact_summary": "Shared database connection pool saturation"
    }

    diagnosis = _heuristic_diagnosis(
        alert_name="DatabaseSaturation",
        service="payment-service",
        correlated_events=correlated_events,
        impact_metrics=impact_metrics
    )

    assert "database-service" in diagnosis["root_cause"].lower() or "database connection pool" in diagnosis["root_cause"].lower()
    assert diagnosis["confidence"] == 95
    assert diagnosis["severity"] == "critical"
    assert diagnosis["risk_level"] == "CRITICAL"
    assert diagnosis["recommended_runbook"] == "CLEAR_STUCK_JOBS"

    # All 4 services must be in affected_services
    for svc in ["database-service", "order-service", "payment-service", "user-service"]:
        assert svc in diagnosis["affected_services"]

    # Alternative causes must be evaluated
    assert "alternative_causes" in diagnosis
    assert len(diagnosis["alternative_causes"]) >= 2
    alt_causes = [ac["cause"] for ac in diagnosis["alternative_causes"]]
    assert any("network" in c.lower() for c in alt_causes)
    for ac in diagnosis["alternative_causes"]:
        assert "confidence" in ac
        assert "reason_rejected" in ac


def test_heuristic_diagnosis_single_service_has_alternative_causes():
    """Single service diagnosis also provides alternative candidate hypotheses."""
    diagnosis = _heuristic_diagnosis("HighMemoryUsage", "notification-service")
    assert "memory" in diagnosis["root_cause"].lower()
    assert diagnosis["affected_services"] == ["notification-service"]
    assert "alternative_causes" in diagnosis
    assert len(diagnosis["alternative_causes"]) >= 1


def test_build_investigation_prompt_formatting():
    """Prompt composer includes the correlated events cluster and business impact metrics."""
    correlated_events = [
        {
            "timestamp": "2026-11-09 10:00:00",
            "service": "payment-service",
            "source": "alertmanager",
            "severity": "critical",
            "message": "Payment write timeout"
        },
        {
            "timestamp": "2026-11-09 10:00:02",
            "service": "user-service",
            "source": "api",
            "severity": "error",
            "message": "Login timeout"
        }
    ]
    impact_metrics = {
        "failed_transactions": 142,
        "failed_logins": 89,
        "estimated_revenue_at_risk_usd": 7098.58,
        "estimated_users_affected": 231,
        "impact_summary": "Active cascade across payment and user auth."
    }

    prompt = build_investigation_prompt(
        alert_name="DatabaseSaturation",
        service="payment-service",
        metrics="cpu=0.15, mem=30MB",
        health="Status: 500 Unhealthy",
        logs="[ERROR] Connection checkout timeout",
        correlated_events=correlated_events,
        impact_metrics=impact_metrics
    )

    assert "CORRELATED MULTI-SOURCE EVENTS CLUSTER (2 events)" in prompt
    assert "payment-service" in prompt
    assert "user-service" in prompt
    assert "MEASURED BUSINESS & USER IMPACT" in prompt
    assert "Failed Transactions: 142" in prompt
    assert "Failed Logins: 89" in prompt
    assert "$7,098.58" in prompt


def test_diagnostics_node_enrichment_and_impact():
    """Diagnostics agent node enriches state with alternative causes and quantified impact metrics."""
    inc_id = "INC-TEST-PH4-01"
    db = SessionLocal()
    try:
        inc = Incident(
            id=inc_id,
            service="payment-service",
            alert_name="DatabaseSaturation",
            severity="CRITICAL",
            status="INVESTIGATING",
            failed_transactions=142,
            failed_logins=89,
            impact_summary="Initial alert triggered",
            created_at=datetime.utcnow()
        )
        db.add(inc)

        evt1 = Event(
            id=f"evt-p4-01-{uuid.uuid4().hex[:6]}",
            incident_id=inc_id,
            source="alertmanager",
            service="payment-service",
            event_type="alert",
            severity="critical",
            timestamp=datetime.utcnow(),
            message="DatabaseSaturation: Payment transaction rollback"
        )
        evt2 = Event(
            id=f"evt-p4-02-{uuid.uuid4().hex[:6]}",
            incident_id=inc_id,
            source="api",
            service="user-service",
            event_type="UserLoginFailed",
            severity="error",
            timestamp=datetime.utcnow(),
            message="DatabaseSaturation: Auth pool exhausted"
        )
        db.add(evt1)
        db.add(evt2)
        db.commit()
    finally:
        db.close()

    initial_state: AgentState = {
        "incident_id": inc_id,
        "service": "payment-service",
        "alert_name": "DatabaseSaturation",
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
        "analyzer_logs": "Database pool timeout logs",
        "analyzer_metrics": "cpu=0.20",
        "analyzer_health": "500 Internal Server Error",
        "governance_approved": None,
        "governance_reason": None,
        "correlated_events": None,
        "impact_metrics": None,
        "alternative_causes": None
    }

    output_state = diagnostics_agent_node(initial_state)

    assert output_state["root_cause"] is not None
    assert output_state["confidence"] >= 85
    assert output_state["risk_level"] == "CRITICAL"
    assert "user-service" in output_state["affected_services"]
    assert "database-service" in output_state["affected_services"]
    assert output_state["alternative_causes"] is not None
    assert len(output_state["alternative_causes"]) >= 1

    # Verify impact metrics
    impact = output_state["impact_metrics"]
    assert impact["failed_transactions"] == 142
    assert impact["failed_logins"] == 89
    assert impact["estimated_revenue_at_risk_usd"] == round(142 * 49.99, 2)
    assert impact["estimated_users_affected"] == 142 + 89
    assert impact["is_measured"] is True


def test_governance_safety_node_high_business_impact_gate():
    """Governance Agent flags CRITICAL risk and suspends auto-execution when business impact is high."""
    state: AgentState = {
        "incident_id": "INC-TEST-PH4-02",
        "service": "payment-service",
        "alert_name": "DatabaseSaturation",
        "status": "ROOT_CAUSE_FOUND",
        "root_cause": "Shared database connection pool exhaustion",
        "confidence": 95,
        "severity": "critical",
        "risk_level": "CRITICAL",
        "evidence": ["Connection pool timeout"],
        "affected_services": ["payment-service", "user-service", "order-service", "database-service"],
        "reasoning_summary": "Shared database saturation",
        "remediation_choice": "CLEAR_STUCK_JOBS",
        "remediation_result": None,
        "verification_success": None,
        "incident_report": None,
        "next_agent": None,
        "analyzer_logs": None,
        "analyzer_metrics": None,
        "analyzer_health": None,
        "governance_approved": None,
        "governance_reason": None,
        "correlated_events": [],
        "impact_metrics": {
            "failed_transactions": 142,
            "failed_logins": 89,
            "is_measured": True
        },
        "alternative_causes": []
    }

    gov_output = governance_safety_agent_node(state)
    assert gov_output["risk_level"] == "CRITICAL"
    assert gov_output["governance_approved"] is False
    assert "High business impact" in gov_output["governance_reason"] or "More than 3 services" in gov_output["governance_reason"]


def test_auditor_post_mortem_contains_impact_and_timeline():
    """Auditor node formats executive summary, business impact, multi-service timeline, and alternative causes."""
    inc_id = "INC-TEST-PH4-03"
    db = SessionLocal()
    try:
        inc = Incident(
            id=inc_id,
            service="payment-service",
            alert_name="DatabaseSaturation",
            status="INVESTIGATING",
            created_at=datetime.utcnow()
        )
        db.add(inc)
        db.commit()
    finally:
        db.close()

    state: AgentState = {
        "incident_id": inc_id,
        "service": "payment-service",
        "alert_name": "DatabaseSaturation",
        "status": "ROOT_CAUSE_FOUND",
        "root_cause": "Shared database pool exhaustion on database-service",
        "confidence": 95,
        "severity": "critical",
        "risk_level": "CRITICAL",
        "evidence": ["Connection pool checkout timed out"],
        "affected_services": ["payment-service", "user-service", "order-service", "database-service"],
        "reasoning_summary": "Cascading failures due to shared DB pool",
        "remediation_choice": "CLEAR_STUCK_JOBS",
        "remediation_result": "Cleared 45 orphaned connections",
        "verification_success": None,
        "incident_report": None,
        "next_agent": None,
        "analyzer_logs": None,
        "analyzer_metrics": None,
        "analyzer_health": None,
        "governance_approved": False,
        "governance_reason": "High business impact: 142 transactions failed",
        "correlated_events": [
            {
                "timestamp": "2026-11-09T10:00:00",
                "service": "payment-service",
                "source": "alertmanager",
                "severity": "critical",
                "message": "Payment write timeout"
            },
            {
                "timestamp": "2026-11-09T10:00:02",
                "service": "user-service",
                "source": "api",
                "severity": "error",
                "message": "Login timeout"
            }
        ],
        "impact_metrics": {
            "failed_transactions": 142,
            "failed_logins": 89,
            "estimated_revenue_at_risk_usd": 7098.58,
            "estimated_users_affected": 231,
            "impact_summary": "Shared database saturation",
            "is_measured": True
        },
        "alternative_causes": [
            {
                "cause": "Network partition between API Gateway and microservices",
                "confidence": 15,
                "reason_rejected": "Services healthy internally"
            }
        ]
    }

    auditor_output = auditor_node(state)
    report = auditor_output["incident_report"]

    assert "# SRE Incident Post-Mortem and Audit Report" in report
    assert "PENDING HUMAN APPROVAL" in report
    assert "Root Cause" in report

