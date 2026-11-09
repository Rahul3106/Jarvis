"""
J.A.R.V.I.S. Event Normalizer Module
Normalizes multi-source telemetry data (AlertManager webhooks, generic API events,
and uploaded log files (.log, .txt, .json)) into a unified Event schema.
"""

import re
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

SEVERITY_MAP = {
    "fatal": "critical",
    "crit": "critical",
    "critical": "critical",
    "err": "error",
    "error": "error",
    "warn": "warning",
    "warning": "warning",
    "info": "info",
    "informational": "info",
    "notice": "info",
    "debug": "info",
    "trace": "info"
}

KNOWN_SERVICES = [
    "api-gateway",
    "user-service",
    "order-service",
    "payment-service",
    "notification-service",
    "database-service"
]

def generate_event_id(prefix: str = "EVT") -> str:
    """Generates a unique event identifier."""
    date_str = datetime.utcnow().strftime("%Y%m%d")
    unique_suffix = str(uuid.uuid4())[:8].upper()
    return f"{prefix}-{date_str}-{unique_suffix}"

def _parse_timestamp(val: Any) -> datetime:
    """Attempts to parse string or numeric timestamps into datetime."""
    if not val:
        return datetime.utcnow()
    if isinstance(val, datetime):
        return val
    if isinstance(val, (int, float)):
        try:
            return datetime.utcfromtimestamp(val)
        except Exception:
            return datetime.utcnow()
    if isinstance(val, str):
        # Remove trailing Z for strptime compatibility
        clean_val = val.replace("Z", "").replace("+00:00", "").strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%H:%M:%S",
            "%Y/%m/%d %H:%M:%S"
        ):
            try:
                dt = datetime.strptime(clean_val, fmt)
                if fmt == "%H:%M:%S":
                    # Attach today's date if only time was given
                    today = datetime.utcnow().date()
                    dt = datetime.combine(today, dt.time())
                return dt
            except ValueError:
                continue
    return datetime.utcnow()

def _infer_service(text: str, fallback: str = "unknown") -> str:
    """Infers known service name from a string (message or filename)."""
    text_lower = text.lower()
    for svc in KNOWN_SERVICES:
        if svc in text_lower:
            return svc
        # Support aliases like 'payment' -> 'payment-service'
        prefix = svc.split("-")[0]
        if prefix in ["payment", "order", "user", "notification", "gateway", "database"]:
            if prefix in text_lower:
                return svc
    return fallback

def normalize_alertmanager_alert(alert_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes a single AlertManager alert dictionary into the unified Event schema.
    """
    labels = alert_dict.get("labels", {})
    annotations = alert_dict.get("annotations", {})

    alert_name = labels.get("alertname", "UnknownAlert")
    instance = labels.get("instance", "")
    service = labels.get("service") or labels.get("job")
    if not service:
        service = instance.split(":")[0] if ":" in instance else instance
    if not service or service in ["prometheus", "localhost", "127.0.0.1"]:
        service = _infer_service(alert_name, fallback="payment-service")

    raw_severity = labels.get("severity", "warning").lower()
    severity = SEVERITY_MAP.get(raw_severity, "warning")

    summary = annotations.get("summary") or annotations.get("description") or f"Alert {alert_name} fired on {service}"
    timestamp = _parse_timestamp(alert_dict.get("startsAt"))
    trace_id = labels.get("trace_id") or annotations.get("trace_id")

    return {
        "id": generate_event_id("EVT-ALM"),
        "source": "alertmanager",
        "service": service,
        "event_type": "alert",
        "severity": severity,
        "timestamp": timestamp,
        "message": summary,
        "trace_id": trace_id,
        "raw_payload": json.dumps(alert_dict),
        "metadata_json": json.dumps({"labels": labels, "annotations": annotations, "alert_name": alert_name})
    }

def normalize_api_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes an incoming API event payload into the unified Event schema.
    """
    service = payload.get("service")
    message = payload.get("message") or payload.get("msg") or "Generic API Event"
    if not service:
        service = _infer_service(message, fallback="api-gateway")

    raw_severity = str(payload.get("severity") or payload.get("level") or "info").lower()
    severity = SEVERITY_MAP.get(raw_severity, "info")

    event_type = payload.get("event_type") or payload.get("type") or "api_event"
    source = payload.get("source") or "api"

    timestamp = _parse_timestamp(payload.get("timestamp"))

    trace_id = (
        payload.get("trace_id") or
        payload.get("traceId") or
        payload.get("request_id") or
        payload.get("requestId")
    )

    metadata = payload.get("metadata")
    metadata_json = json.dumps(metadata) if isinstance(metadata, dict) else (json.dumps({"data": metadata}) if metadata else None)

    return {
        "id": payload.get("id") or generate_event_id("EVT-API"),
        "source": source,
        "service": service,
        "event_type": event_type,
        "severity": severity,
        "timestamp": timestamp,
        "message": message,
        "trace_id": trace_id,
        "raw_payload": json.dumps(payload),
        "metadata_json": metadata_json
    }

def normalize_log_line(line: str, service: str = "unknown", source: str = "file") -> Optional[Dict[str, Any]]:
    """
    Parses a single log line (JSON or plaintext) into the unified Event schema.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    # Check if JSON line
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data = json.loads(stripped)
            line_service = data.get("service") or service
            if line_service == "unknown":
                line_service = _infer_service(json.dumps(data), fallback="unknown")
            return normalize_api_event({
                **data,
                "service": line_service,
                "source": source,
                "event_type": data.get("event_type") or "log"
            })
        except Exception:
            pass

    # Plaintext parsing
    timestamp = datetime.utcnow()
    severity = "info"
    message = stripped
    trace_id = None

    # Look for trace_id pattern: trace_id=xyz, req_id=xyz, [req-xyz], [trace-xyz]
    trace_match = re.search(r'(?:trace_id|traceId|req_id|requestId)=([a-zA-Z0-9_\-]+)', stripped, re.IGNORECASE)
    if not trace_match:
        trace_match = re.search(r'\[(req-[a-zA-Z0-9_\-]+|trace-[a-zA-Z0-9_\-]+)\]', stripped, re.IGNORECASE)
    if trace_match:
        trace_id = trace_match.group(1)

    # Look for severity pattern
    level_match = re.search(r'\[(INFO|WARNING|WARN|ERROR|CRITICAL|FATAL|DEBUG)\]', stripped, re.IGNORECASE)
    if not level_match:
        level_match = re.search(r'\b(INFO|WARNING|WARN|ERROR|CRITICAL|FATAL|DEBUG)\b', stripped)
    if level_match:
        raw_level = level_match.group(1).lower()
        severity = SEVERITY_MAP.get(raw_level, "info")

    # Look for timestamp pattern
    # Pattern 1: YYYY-MM-DD HH:MM:SS
    ts_match = re.search(r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)', stripped)
    if ts_match:
        timestamp = _parse_timestamp(ts_match.group(1))
    else:
        # Pattern 2: [HH:MM:SS]
        ts_time_match = re.search(r'\[(\d{2}:\d{2}:\d{2})\]', stripped)
        if ts_time_match:
            timestamp = _parse_timestamp(ts_time_match.group(1))

    # Infer service if still unknown
    if service == "unknown":
        service = _infer_service(stripped, fallback="unknown")

    return {
        "id": generate_event_id("EVT-LOG"),
        "source": source,
        "service": service,
        "event_type": "log",
        "severity": severity,
        "timestamp": timestamp,
        "message": message,
        "trace_id": trace_id,
        "raw_payload": stripped,
        "metadata_json": None
    }

def parse_log_file_content(content: str, filename: str = "", default_service: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Parses full log file content (JSON array, JSONL, or plaintext) into a list of normalized events.
    """
    inferred_service = default_service or _infer_service(filename, fallback="unknown")
    events = []

    clean_content = content.strip()
    if not clean_content:
        return events

    # 1. Check if entire file is a single JSON array
    if clean_content.startswith("[") and clean_content.endswith("]"):
        try:
            records = json.loads(clean_content)
            if isinstance(records, list):
                for item in records:
                    if isinstance(item, dict):
                        item_svc = item.get("service") or inferred_service
                        norm = normalize_api_event({
                            **item,
                            "service": item_svc,
                            "source": "file",
                            "event_type": item.get("event_type") or "log"
                        })
                        events.append(norm)
                return events
        except Exception:
            pass

    # 2. Line by line parsing (Plaintext or JSON Lines)
    for line in clean_content.splitlines():
        norm_line = normalize_log_line(line, service=inferred_service, source="file")
        if norm_line:
            events.append(norm_line)

    return events

