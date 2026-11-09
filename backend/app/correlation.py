"""
J.A.R.V.I.S. Dedicated Event Correlation & Incident Grouping Engine
Correlates incoming alerts, logs, and API events across time windows, service topology,
shared infrastructure dependencies, trace IDs, and causal error signatures.
Prevents false-grouping of independent, unrelated concurrent failures.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Tuple

from sqlalchemy.orm import Session
from app.database import Incident, Event, IncidentLog, SessionLocal
from app.topology import (
    get_topological_distance,
    get_shared_dependencies,
    are_services_topologically_related,
    ALL_SERVICES
)

logger = logging.getLogger("jarvis-correlation")

# Default configuration
DEFAULT_CORRELATION_WINDOW_SECONDS = 35.0
MIN_CORRELATION_SCORE = 0.60

# Error signature taxonomies for causal matching
SIGNATURE_PATTERNS = {
    "DATABASE_OUTAGE": [
        "database", "postgres", "connection pool", "checkout timed out",
        "pool exhausted", "databasesaturation", "databasecorruption", "sql",
        "deadlock", "table", "lock timeout"
    ],
    "CASCADING_TIMEOUT": [
        "504", "gateway timeout", "timeout", "timed out", "slow",
        "cascadingfailure", "backpressure", "queue saturated", "502 bad gateway",
        "503 service unavailable", "downstream"
    ],
    "HTTP_500_STORM": [
        "http 500", "status 500", "status=500", "500 internal", "httperrorspike", "error spike", "500:"
    ],
    "CPU_ANOMALY": [
        "cpu", "highcpuusage", "busy loop", "thread pool executor", "utilization"
    ],
    "MEMORY_ANOMALY": [
        "memory", "heap", "outofmemoryerror", "highmemoryusage", "oom", "leak"
    ],
    "NETWORK_OUTAGE": [
        "networkpartition", "unreachable", "socket timeout", "connection refused",
        "broken pipe", "dns"
    ],
    "CONFIG_DRIFT": [
        "config", "configurationdrift", "property", "drifted", "setting"
    ],
    "CERT_EXPIRATION": [
        "certificate", "ssl", "certificateexpiration", "handshake", "tls", "expired"
    ],
    "AUTH_FAILURE": [
        "auth", "login", "jwt", "unauthorized", "token", "session"
    ],
    "TRANSACTION_FAILURE": [
        "payment", "transaction", "checkout", "order", "charge", "refund"
    ]
}

def extract_error_signatures(text: str) -> Set[str]:
    """Extracts high-level failure taxonomy categories from message or payload."""
    if not text:
        return set()
    text_lower = text.lower()
    matches = set()
    for category, keywords in SIGNATURE_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            matches.add(category)
    return matches

def signatures_are_causally_compatible(sigs_a: Set[str], sigs_b: Set[str]) -> float:
    """
    Evaluates causal affinity between two failure signatures.
    Returns a score between 0.0 (incompatible) and 1.0 (exact match).
    """
    if not sigs_a or not sigs_b:
        return 0.3  # neutral

    # Strictly incompatible failure modes (independent root causes)
    incompatible_pairs = [
        ({"MEMORY_ANOMALY"}, {"DATABASE_OUTAGE", "CONFIG_DRIFT", "CERT_EXPIRATION", "AUTH_FAILURE"}),
        ({"CPU_ANOMALY"}, {"DATABASE_OUTAGE", "CONFIG_DRIFT", "CERT_EXPIRATION", "AUTH_FAILURE"}),
        ({"CONFIG_DRIFT"}, {"DATABASE_OUTAGE", "MEMORY_ANOMALY", "CPU_ANOMALY"}),
        ({"CERT_EXPIRATION"}, {"DATABASE_OUTAGE", "MEMORY_ANOMALY", "CPU_ANOMALY"}),
    ]
    for group_1, group_2 in incompatible_pairs:
        if (sigs_a & group_1 and sigs_b & group_2) or (sigs_b & group_1 and sigs_a & group_2):
            return 0.0

    # Direct overlap (same failure class)
    overlap = sigs_a.intersection(sigs_b)
    if overlap:
        return 1.0

    # Causal chain pairings
    # e.g., DATABASE_OUTAGE causes CASCADING_TIMEOUT, HTTP_500_STORM, AUTH_FAILURE, TRANSACTION_FAILURE
    causal_chains = [
        ({"DATABASE_OUTAGE"}, {"CASCADING_TIMEOUT", "HTTP_500_STORM", "AUTH_FAILURE", "TRANSACTION_FAILURE"}),
        ({"CASCADING_TIMEOUT"}, {"HTTP_500_STORM", "TRANSACTION_FAILURE"}),
        ({"NETWORK_OUTAGE"}, {"CASCADING_TIMEOUT", "HTTP_500_STORM"}),
        ({"CPU_ANOMALY"}, {"CASCADING_TIMEOUT"}),
    ]

    for source_set, target_set in causal_chains:
        if (sigs_a & source_set and sigs_b & target_set) or (sigs_b & source_set and sigs_a & target_set):
            return 0.85

    return 0.0

class CorrelationEngine:
    """
    Core engine responsible for computing event-to-event and event-to-incident correlation.
    Clusters multi-service symptoms into unified incident records while protecting against false groupings.
    """

    def __init__(self, time_window_seconds: float = DEFAULT_CORRELATION_WINDOW_SECONDS, min_score: float = MIN_CORRELATION_SCORE):
        self.time_window_seconds = time_window_seconds
        self.min_score = min_score

    def compute_event_correlation(self, event_a: Dict[str, Any], event_b: Dict[str, Any]) -> float:
        """
        Computes composite correlation score S in [0.0, 1.0] between two events.
        """
        # 1. Deterministic Trace ID Override
        trace_a = event_a.get("trace_id")
        trace_b = event_b.get("trace_id")
        if trace_a and trace_b and trace_a == trace_b:
            return 1.0

        # 2. Temporal Proximity
        ts_a = event_a.get("timestamp") or datetime.utcnow()
        ts_b = event_b.get("timestamp") or datetime.utcnow()
        if isinstance(ts_a, str):
            try:
                ts_a = datetime.fromisoformat(ts_a.replace("Z", ""))
            except Exception:
                ts_a = datetime.utcnow()
        if isinstance(ts_b, str):
            try:
                ts_b = datetime.fromisoformat(ts_b.replace("Z", ""))
            except Exception:
                ts_b = datetime.utcnow()

        delta_sec = abs((ts_a - ts_b).total_seconds())
        if delta_sec > self.time_window_seconds:
            return 0.0

        score_time = max(0.0, 1.0 - (delta_sec / self.time_window_seconds))

        # 3. Topological Proximity
        svc_a = event_a.get("service", "unknown")
        svc_b = event_b.get("service", "unknown")

        if svc_a == svc_b and svc_a != "unknown":
            score_topo = 1.0
        else:
            dist = get_topological_distance(svc_a, svc_b)
            if dist == 1:
                # Direct caller-callee or shared DB infrastructure
                shared_infra = get_shared_dependencies(svc_a, svc_b)
                score_topo = 0.90 if shared_infra else 0.80
            elif dist == 2:
                score_topo = 0.50
            else:
                score_topo = 0.0  # Disconnected services

        # 4. Error Signature Affinity
        msg_a = f"{event_a.get('message', '')} {event_a.get('event_type', '')}"
        msg_b = f"{event_b.get('message', '')} {event_b.get('event_type', '')}"
        sigs_a = extract_error_signatures(msg_a)
        sigs_b = extract_error_signatures(msg_b)

        score_sig = signatures_are_causally_compatible(sigs_a, sigs_b)

        # 5. False-Correlation Guard:
        # If error signatures are incompatible (e.g. OOM vs Database Outage) OR services are disconnected,
        # correlation is definitively rejected.
        if score_sig == 0.0 or score_topo == 0.0:
            return 0.0

        # Weighted calculation
        # Weights: Time (25%), Topology (45%), Error Signature (30%)
        final_score = (0.25 * score_time) + (0.45 * score_topo) + (0.30 * score_sig)
        return round(final_score, 3)

    def correlate_event_with_incident(self, db: Session, incident: Incident, event_dict: Dict[str, Any]) -> float:
        """
        Computes how strongly an incoming event correlates with an ongoing Incident.
        Evaluates against the incident's primary service, its affected services set,
        and its attached events.
        """
        # Primary service comparison
        incident_event_mock = {
            "service": incident.service,
            "timestamp": incident.created_at,
            "message": f"{incident.alert_name} {incident.root_cause or ''}",
            "trace_id": None
        }
        max_score = self.compute_event_correlation(event_dict, incident_event_mock)

        # Check against existing events linked to this incident
        linked_events = db.query(Event).filter(Event.incident_id == incident.id).order_by(Event.timestamp.desc()).limit(15).all()
        for le in linked_events:
            score = self.compute_event_correlation(event_dict, le.to_dict())
            if score > max_score:
                max_score = score
            if max_score >= 0.95:
                break

        # Check affected_services list only if event has non-zero affinity
        if incident.affected_services and max_score > 0.0:
            try:
                affected = json.loads(incident.affected_services)
                if isinstance(affected, list) and event_dict.get("service") in affected:
                    max_score = max(max_score, 0.75)
            except Exception:
                pass

        return max_score

    def find_matching_active_incident(self, db: Session, event_dict: Dict[str, Any]) -> Tuple[Optional[Incident], float]:
        """
        Finds the active incident that best correlates with the incoming event.
        Returns (Incident, score) or (None, 0.0) if no match meets min_score.
        """
        active_incidents = db.query(Incident).filter(
            Incident.status.in_(["INVESTIGATING", "ROOT_CAUSE_FOUND", "EXECUTING_FIX", "VERIFYING", "PENDING_APPROVAL"])
        ).order_by(Incident.created_at.desc()).all()

        best_match = None
        best_score = 0.0

        for inc in active_incidents:
            score = self.correlate_event_with_incident(db, inc, event_dict)
            if score > best_score and score >= self.min_score:
                best_score = score
                best_match = inc

        return best_match, best_score

    def correlate_and_assign(self, db: Session, event: Event) -> Dict[str, Any]:
        """
        Processes a newly ingested Event record:
        - If it correlates with an active incident, attaches it and updates blast radius.
        - If it does not, checks for unassigned correlated events in the time window.
        """
        event_dict = event.to_dict()

        # 1. Check against ongoing active incidents
        matched_incident, score = self.find_matching_active_incident(db, event_dict)

        if matched_incident:
            # Attach event to matched incident
            event.incident_id = matched_incident.id

            # Update affected_services list
            current_affected = []
            if matched_incident.affected_services:
                try:
                    current_affected = json.loads(matched_incident.affected_services)
                except Exception:
                    current_affected = [matched_incident.service]
            else:
                current_affected = [matched_incident.service]

            if event.service not in current_affected and event.service != "unknown":
                current_affected.append(event.service)
                matched_incident.affected_services = json.dumps(current_affected)

            # Update business impact counts if event signals failures
            msg_lower = (event.message or "").lower()
            if "login" in msg_lower and ("fail" in msg_lower or "500" in msg_lower or "timeout" in msg_lower):
                matched_incident.failed_logins = (matched_incident.failed_logins or 0) + 1
            if ("payment" in msg_lower or "transaction" in msg_lower or "checkout" in msg_lower) and ("fail" in msg_lower or "500" in msg_lower or "timeout" in msg_lower):
                matched_incident.failed_transactions = (matched_incident.failed_transactions or 0) + 1

            # Log correlation step
            log_entry = IncidentLog(
                incident_id=matched_incident.id,
                level="INFO",
                message=f"[CorrelationEngine] Correlated event '{event.id}' from '{event.service}' into incident '{matched_incident.id}' (Score: {score:.2f})",
                timestamp=datetime.utcnow()
            )
            db.add(log_entry)
            db.commit()

            logger.info(f"Correlated event {event.id} ({event.service}) -> incident {matched_incident.id} (Score: {score})")
            return {
                "action": "attached_to_incident",
                "incident_id": matched_incident.id,
                "correlation_score": score,
                "affected_services": current_affected
            }

        db.commit()
        return {
            "action": "stored_unassigned",
            "incident_id": None,
            "correlation_score": 0.0
        }

    def cluster_unassigned_events(self, db: Session, window_seconds: Optional[float] = None) -> List[List[Event]]:
        """
        Scans recent unassigned events (incident_id is NULL) and clusters them into correlated groups.
        Useful for batch ingestion or log uploads.
        """
        window = window_seconds or self.time_window_seconds
        cutoff = datetime.utcnow() - timedelta(seconds=window)

        unassigned = db.query(Event).filter(
            Event.incident_id.is_(None),
            Event.timestamp >= cutoff
        ).order_by(Event.timestamp.asc()).all()

        if not unassigned:
            return []

        clusters: List[List[Event]] = []

        for evt in unassigned:
            evt_dict = evt.to_dict()
            assigned = False
            for cluster in clusters:
                # Check correlation with cluster representative
                rep_dict = cluster[0].to_dict()
                score = self.compute_event_correlation(evt_dict, rep_dict)
                if score >= self.min_score:
                    cluster.append(evt)
                    assigned = True
                    break
            if not assigned:
                clusters.append([evt])

        return clusters

# Global singleton
correlation_engine = CorrelationEngine()
