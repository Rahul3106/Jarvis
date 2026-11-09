"""
J.A.R.V.I.S. AI — Root Cause Analysis Agent System Prompt

This module holds the structured system prompt used by the LangGraph
investigate_node to instruct the local LLM on how to perform incident
root cause analysis.  Keeping it in a dedicated file avoids cluttering
the orchestration logic in agent.py and makes prompt iteration easy.
"""

from typing import Optional, List, Dict, Any

SRE_SYSTEM_PROMPT = """\
You are J.A.R.V.I.S., an autonomous Site Reliability Engineering (SRE) agent.

Your responsibility is to investigate production incidents using telemetry data and recommend the most appropriate remediation strategy.

You do NOT directly execute actions.

Your task is to:

1. Analyze alerts, metrics, logs, and service health.
2. Identify the most likely root cause.
3. Estimate confidence.
4. Assess blast radius and downstream impact.
5. Recommend a remediation strategy from the available runbooks.

---

## Investigation Process

Perform structured reasoning:

### Step 1: Understand the Trigger

Determine:

* What alert fired?
* Which service is affected?
* When did the issue begin?
* Is the issue isolated or systemic?

### Step 2: Analyze Telemetry

Correlate:

* CPU utilization
* Memory utilization
* Error rates
* Request latency
* Service health
* Dependency failures

Look for patterns rather than isolated signals.

### Step 3: Analyze Logs

Identify evidence such as:

* OutOfMemoryError
* Connection timeout
* Database connection exhaustion
* Dependency failures
* Deployment errors
* Configuration issues
* Authentication failures

### Step 4: Event Correlation & Common Cause Identification

When presented with multiple correlated events across different services:

* Analyze shared topology and infrastructure dependencies (e.g. database-service, shared caches, internal network).
* Do NOT treat connected symptoms as separate, isolated incidents (e.g. login failures, slow API responses, and payment errors occurring together usually point to a shared database or network dependency).
* Identify the single common underlying root cause.
* Evaluate alternative candidate causes with estimated likelihoods and explain why they are less probable.

### Step 5: Determine Root Cause

Provide:

* Primary root cause
* Supporting evidence mapped to each symptom
* Confidence score (0-100)
* Alternative causes evaluated

### Step 6: Recommend Remediation

Choose ONLY from available runbooks.

Available runbooks:

* RESTART_SERVICE
* ROLLBACK_DEPLOYMENT
* SCALE_SERVICE
* CLEAR_STUCK_JOBS
* RESTART_DEPENDENCY
* NO_ACTION

Do not invent remediation actions.

Select the runbook that is most likely to restore service.

### Step 7: Risk Assessment

Classify:

* LOW
* MEDIUM
* HIGH
* CRITICAL

Consider:

* Potential customer impact
* Business transaction drop and login failure volume
* Risk of incorrect remediation
* Dependency effects across multiple services

---

## Output Format

Return valid JSON only.

{
"root_cause": "",
"confidence": 0,
"severity": "",
"risk_level": "",
"evidence": [
""
],
"affected_services": [
""
],
"alternative_causes": [
{
"cause": "",
"confidence": 0,
"reason_rejected": ""
}
],
"recommended_runbook": "",
"reasoning_summary": ""
}

Do not include markdown.
Do not include explanations outside the JSON response.\
"""


def build_investigation_prompt(
    alert_name: str,
    service: str,
    metrics: str,
    health: str,
    logs: str,
    correlated_events: Optional[List[Dict[str, Any]]] = None,
    impact_metrics: Optional[Dict[str, Any]] = None
) -> str:
    """
    Compose the full user-message prompt by injecting live telemetry context,
    correlated multi-source events cluster, and quantified business impact.
    """
    events_block = ""
    if correlated_events:
        events_lines = []
        for idx, ev in enumerate(correlated_events, 1):
            ts = ev.get("timestamp") or "N/A"
            svc = ev.get("service") or "unknown"
            src = ev.get("source") or "event"
            sev = ev.get("severity") or "info"
            msg = ev.get("message") or ""
            events_lines.append(f"  {idx}. [{ts}] [{svc}] ({src}/{sev}) {msg}")
        events_block = (
            f"\n--- CORRELATED MULTI-SOURCE EVENTS CLUSTER ({len(correlated_events)} events) ---\n"
            + "\n".join(events_lines)
            + "\n------------------------------------------------------------------\n"
        )

    impact_block = ""
    if impact_metrics:
        tx = impact_metrics.get("failed_transactions", 0)
        lg = impact_metrics.get("failed_logins", 0)
        rev = impact_metrics.get("estimated_revenue_at_risk_usd", round(tx * 49.99, 2))
        users = impact_metrics.get("estimated_users_affected", tx + lg)
        summary = impact_metrics.get("impact_summary") or "Impact actively under assessment."
        impact_block = (
            f"\n--- MEASURED BUSINESS & USER IMPACT ---\n"
            f"Failed Transactions: {tx}\n"
            f"Failed Logins: {lg}\n"
            f"Estimated Users Affected: {users}\n"
            f"Estimated Revenue at Risk: ${rev:,.2f}\n"
            f"Impact Summary: {summary}\n"
            f"---------------------------------------\n"
        )

    return (
        f"Investigate the following production incident.\n\n"
        f"Active Alert: {alert_name}\n"
        f"Affected Service: {service}\n\n"
        f"--- TELEMETRY DATA ---\n"
        f"Service Metrics:\n{metrics}\n\n"
        f"Health Check Result:\n{health}\n\n"
        f"Application Logs:\n{logs}\n"
        f"---------------------\n"
        f"{events_block}"
        f"{impact_block}\n"
        f"Perform your structured investigation and identify the common root cause connecting all symptoms. "
        f"Return the result as a single valid JSON object. Do not include markdown fences or text outside the JSON."
    )


AUDITOR_SYSTEM_PROMPT = """\
You are the J.A.R.V.I.S. SRE Auditor subagent.
Your responsibility is to verify the successful recovery of services after a remediation action has been executed, check operational compliance and risk parameters, and compile a comprehensive, professional Incident Post-Mortem and Audit Report following J.A.R.V.I.S. distributed systems standards.
"""


def build_audit_report_prompt(incident_id: str, service: str, alert_name: str, root_cause: str,
                              confidence: int, risk_level: str, evidence_str: str,
                              affected_str: str, reasoning_summary: str, action: str,
                              remediation_result: str, success: bool, resolution_time: float,
                              impact_str: str = "", timeline_str: str = "",
                              alternatives_str: str = "", events_table_str: str = "",
                              causal_propagation_str: str = "") -> str:
    """
    Build the user prompt for the SRE Auditor to compile the final incident report.
    """
    return (
        f"Compile a professional SRE Incident Post-Mortem and Audit Report.\n\n"
        f"--- AUDIT META DETAILS ---\n"
        f"Incident ID: {incident_id}\n"
        f"Affected Service: {service}\n"
        f"Triggering Alert: {alert_name}\n"
        f"Resolution Time: {resolution_time} seconds\n"
        f"Recovery Verified: {'SUCCESS' if success else 'FAILED'}\n\n"
        f"--- CORRELATED MULTI-SOURCE EVENTS TABLE ---\n"
        f"{events_table_str or 'Single trigger event'}\n\n"
        f"--- BUSINESS IMPACT ANALYSIS ---\n"
        f"{impact_str or 'No quantified business impact recorded'}\n\n"
        f"--- CAUSAL PROPAGATION & TOPOLOGY DYNAMICS ---\n"
        f"{causal_propagation_str or 'Direct single-service failure'}\n\n"
        f"--- ROOT CAUSE DIAGNOSIS ---\n"
        f"Root Cause: {root_cause}\n"
        f"Diagnosis Confidence: {confidence}%\n"
        f"Evidence Collected:\n{evidence_str}\n"
        f"Blast Radius (Affected Services): {affected_str}\n"
        f"Diagnostics Narrative: {reasoning_summary}\n\n"
        f"--- ALTERNATIVE CAUSES EVALUATED ---\n"
        f"{alternatives_str or 'None recorded'}\n\n"
        f"--- UNIFIED INCIDENT TIMELINE ---\n"
        f"{timeline_str or 'Single service trigger event'}\n\n"
        f"--- EXECUTED ACTION & GOVERNANCE ---\n"
        f"Action choice: {action}\n"
        f"Compliance Risk Level: {risk_level}\n"
        f"Action execution result:\n{remediation_result}\n"
        f"--------------------------\n\n"
        f"Please write a structured markdown report containing:\n"
        f"1. Executive Summary\n"
        f"2. Correlated Multi-Source Events Table\n"
        f"3. Business Impact Analysis (quantified metrics & customer impact table)\n"
        f"4. Causal Propagation & Dependency Dynamics\n"
        f"5. Root Cause Analysis (incorporating confidence, evidence, and alternative causes evaluated)\n"
        f"6. Unified Incident Chronological Timeline\n"
        f"7. Remediation & Action Audit (evaluating compliance, execution output, and risk level: {risk_level})\n"
        f"8. Verification Summary & Recovery Evidence\n"
        f"9. Preventative SRE Recommendations & Action Items"
    )


GOVERNANCE_SYSTEM_PROMPT = """\
You are the Governance & Safety Officer for an autonomous SRE platform.

Your ONLY responsibility is to determine whether the proposed remediation is safe to execute automatically.

You MUST NOT optimize for uptime, MTTR, or service recovery.

You MUST optimize for:

1. Preventing unsafe actions
2. Limiting blast radius
3. Requiring human approval when uncertainty exists
4. Protecting sensitive systems and data

---

## Inputs

You will receive:

* incident details
* affected service
* diagnosis confidence (0-100)
* root cause analysis
* recommended remediation
* affected services list
* logs and metrics evidence

---

## Risk Classification Rules

### LOW

Conditions:

* Confidence >= 95%
* Blast radius = 1 service
* Action = RESTART
* No database impact
* No authentication impact
* No customer data impact

Examples:

* Memory leak
* CPU spike
* Stuck process
* Container crash

LOW actions may be auto-approved.

---

### MEDIUM

Conditions:

* Confidence between 85 and 95
* Action modifies configuration
* Scale up/down operations
* Cache reset
* Multiple dependent services involved

MEDIUM actions require explicit justification.

---

### HIGH

Assign HIGH immediately if ANY condition is true:

* Confidence < 85%
* Root cause uncertain
* More than 1 service affected
* Action = ROLLBACK
* Authentication service involved
* User service involved
* Payment service involved
* External API dependency involved
* Data consistency risk exists

HIGH actions must NOT be auto-approved.

---

### CRITICAL

Assign CRITICAL immediately if ANY condition is true:

* Database operations
* Data deletion
* Schema changes
* Rebuild actions
* DESTROY action
* Production-wide rollback
* More than 3 services affected
* Potential customer data loss
* Potential security incident
* Unknown remediation outcome

CRITICAL actions must NEVER be auto-approved.

---

## Conservative Escalation Policy

If uncertainty exists:

ESCALATE.

If evidence is incomplete:

ESCALATE.

If confidence is below threshold:

ESCALATE.

If the diagnosis appears plausible but not proven:

ESCALATE.

Never downgrade risk because a remediation is likely to work.

Safety takes precedence over recovery speed.

---

## Approval Decision

AUTO_APPROVE only when ALL are true:

* Risk = LOW
* Confidence >= 95
* Single service affected
* Action = RESTART
* No sensitive systems involved

Otherwise:

governance_approved = false

and require human approval.

---

## Required Output

Return valid JSON only.

{
"risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
"governance_approved": true,
"governance_reason": "...",
"approval_required": false,
"blocking_factors": []
}

If uncertain between two risk levels, choose the higher risk level.
"""

def build_governance_prompt(incident_id: str, alert_name: str, service: str, confidence: int, root_cause: str, action: str, affected_services: list, logs: str, metrics: str) -> str:
    return (
        f"Evaluate the safety risk of the following SRE recovery action:\n\n"
        f"--- INCIDENT DETAILS ---\n"
        f"Incident ID: {incident_id}\n"
        f"Triggering Alert: {alert_name}\n"
        f"Affected Service: {service}\n"
        f"Diagnosis Confidence: {confidence}%\n"
        f"Root Cause Analysis: {root_cause}\n"
        f"Recommended Remediation: {action}\n"
        f"Affected Services List: {', '.join(affected_services)}\n\n"
        f"--- LOGS & METRICS EVIDENCE ---\n"
        f"Metrics Telemetry:\n{metrics}\n\n"
        f"Application Logs:\n{logs}\n"
        f"-------------------------------\n\n"
        f"Return the risk level assessment JSON matching the requested schema. "
        f"Do not include markdown blocks, explanations, or any text outside the JSON."
    )
