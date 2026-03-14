"""
GCP Log Service — Fetches, filters, and analyzes logs from Google Cloud Logging.
Provides root-cause analysis for batch failures, API errors, and slow requests.
"""

import json
import re
import os
import tempfile
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional

from google.cloud import logging as gcp_logging
from google.oauth2 import service_account

from models import (
    LogEntry, ServiceHealth, BatchStatus, DashboardSummary,
    IssueCategory, RootCause, ConnectionTestResult, Severity,
)


# ── Root Cause Analysis Rules ───────────────────────────────────

ROOT_CAUSE_PATTERNS = [
    (r"(?i)(connection\s*pool|hikari|pool\s*exhausted|no\s*available\s*connection)", RootCause.CONNECTION_POOL_EXHAUSTED),
    (r"(?i)(jdbc|sql.*timeout|database.*timeout|db.*timeout|query.*timeout)", RootCause.DATABASE_TIMEOUT),
    (r"(?i)(outofmemory|oom|heap\s*space|java\.lang\.OutOfMemoryError)", RootCause.OUT_OF_MEMORY),
    (r"(?i)(nullpointer|null\s*pointer|NullPointerException)", RootCause.NULL_POINTER),
    (r"(?i)(data\s*integrity|constraint\s*violation|duplicate\s*key|DataIntegrityViolation)", RootCause.DATA_INTEGRITY),
    (r"(?i)(connection\s*refused|connect\s*timed\s*out|service\s*unavailable|503|UNAVAILABLE)", RootCause.SERVICE_UNAVAILABLE),
    (r"(?i)(socket\s*timeout|read\s*timed\s*out|network\s*timeout|deadline\s*exceeded)", RootCause.NETWORK_TIMEOUT),
    (r"(?i)(gc\s*pause|garbage\s*collection|full\s*gc|stop.*world)", RootCause.GC_PAUSE),
    (r"(?i)(slow\s*query|query\s*took|long\s*running\s*query)", RootCause.QUERY_SLOW),
    (r"(?i)(rate\s*limit|throttl|429|too\s*many\s*requests|quota)", RootCause.RATE_LIMITED),
    (r"(?i)(unauthorized|forbidden|401|403|auth.*fail|token.*expir)", RootCause.AUTH_FAILURE),
]


def analyze_root_cause(message: str) -> str:
    """Analyze a log message and determine the most likely root cause."""
    if not message:
        return RootCause.UNKNOWN.value

    for pattern, cause in ROOT_CAUSE_PATTERNS:
        if re.search(pattern, message):
            return cause.value

    return RootCause.UNKNOWN.value


def categorize_log(entry_dict: dict) -> str:
    """Categorize a log entry into an issue category."""
    message = str(entry_dict.get("message", "")).lower()
    http_status = entry_dict.get("http_status")
    severity = str(entry_dict.get("severity", "")).upper()

    # Check for batch-related failures
    batch_keywords = ["batch", "job", "scheduler", "cron", "scheduled", "spring batch", "step execution"]
    if any(kw in message for kw in batch_keywords) and severity in ("ERROR", "CRITICAL"):
        return IssueCategory.BATCH_FAILURE.value

    # Check HTTP status codes
    if http_status == 500:
        return IssueCategory.API_500.value
    elif http_status == 502:
        return IssueCategory.API_502.value
    elif http_status == 504:
        return IssueCategory.API_504.value

    # Check for slow requests
    latency = entry_dict.get("latency_ms")
    if latency and latency > 2000:
        return IssueCategory.SLOW_REQUEST.value

    # Fallback based on message content
    if "500" in message and ("internal server error" in message or "status" in message):
        return IssueCategory.API_500.value
    elif "502" in message and ("bad gateway" in message or "status" in message):
        return IssueCategory.API_502.value

    return IssueCategory.UNKNOWN.value


def extract_http_status(entry) -> Optional[int]:
    """Extract HTTP status code from a GCP log entry."""
    try:
        if hasattr(entry, "http_request") and entry.http_request:
            req = entry.http_request
            if isinstance(req, dict):
                return req.get("status")
            elif hasattr(req, "status"):
                return req.status
    except Exception:
        pass

    # Try extracting from the payload
    payload = _get_payload(entry)
    payload_str = str(payload)

    status_match = re.search(r'(?:status["\s:=]+|httpStatus["\s:=]+|statusCode["\s:=]+)(\d{3})', payload_str)
    if status_match:
        return int(status_match.group(1))

    return None


def extract_latency(entry) -> Optional[float]:
    """Extract request latency in milliseconds from a GCP log entry."""
    try:
        if hasattr(entry, "http_request") and entry.http_request:
            req = entry.http_request
            if isinstance(req, dict):
                latency = req.get("latency")
                if latency:
                    if isinstance(latency, str) and latency.endswith("s"):
                        return float(latency[:-1]) * 1000
                    elif isinstance(latency, (int, float)):
                        return float(latency) * 1000
            elif hasattr(req, "latency"):
                latency = req.latency
                if hasattr(latency, "total_seconds"):
                    return latency.total_seconds() * 1000
    except Exception:
        pass

    # Try extracting from payload
    payload = _get_payload(entry)
    payload_str = str(payload)

    latency_match = re.search(r'(?:latency|duration|elapsed|took|responseTime)["\s:=]+(\d+(?:\.\d+)?)\s*(ms|s|seconds|milliseconds)?', payload_str, re.IGNORECASE)
    if latency_match:
        value = float(latency_match.group(1))
        unit = (latency_match.group(2) or "ms").lower()
        if unit in ("s", "seconds"):
            return value * 1000
        return value

    return None


def extract_service_name(entry) -> str:
    """Extract the microservice name from a GCP log entry."""
    try:
        if hasattr(entry, "resource") and entry.resource:
            labels = entry.resource.labels
            if isinstance(labels, dict):
                for key in ("service_name", "container_name", "module_id", "job_name", "service"):
                    if key in labels and labels[key]:
                        return labels[key]
    except Exception:
        pass

    try:
        if hasattr(entry, "labels") and entry.labels:
            for key in ("k8s-pod/app", "compute.googleapis.com/resource_name", "app", "service"):
                if key in entry.labels and entry.labels[key]:
                    return entry.labels[key]
    except Exception:
        pass

    # Fallback: extract from log_name
    try:
        if hasattr(entry, "log_name") and entry.log_name:
            parts = entry.log_name.split("/")
            return parts[-1] if parts else "unknown-service"
    except Exception:
        pass

    return "unknown-service"


def extract_trace_id(entry) -> Optional[str]:
    """Extract trace ID from a GCP log entry."""
    try:
        if hasattr(entry, "trace") and entry.trace:
            trace = entry.trace
            # Format: projects/{project}/traces/{trace_id}
            if "/" in trace:
                return trace.split("/")[-1]
            return trace
    except Exception:
        pass
    return None


def _get_payload(entry) -> str:
    """Safely extract the payload/message from a GCP log entry."""
    try:
        if hasattr(entry, "payload"):
            payload = entry.payload
            if isinstance(payload, dict):
                return json.dumps(payload)
            return str(payload)
        if hasattr(entry, "text_payload") and entry.text_payload:
            return entry.text_payload
        if hasattr(entry, "json_payload") and entry.json_payload:
            return json.dumps(entry.json_payload)
        if hasattr(entry, "proto_payload") and entry.proto_payload:
            return str(entry.proto_payload)
    except Exception:
        pass
    return ""


def _get_message(entry) -> str:
    """Extract the human-readable message from a log entry."""
    payload = _get_payload(entry)

    # For JSON payloads, try to extract a message field
    if isinstance(payload, str) and payload.startswith("{"):
        try:
            data = json.loads(payload)
            for key in ("message", "msg", "error", "errorMessage", "description", "textPayload"):
                if key in data and data[key]:
                    return str(data[key])
        except json.JSONDecodeError:
            pass

    return payload[:2000] if payload else "No message available"


def _get_severity(entry) -> str:
    """Extract severity from a log entry."""
    try:
        if hasattr(entry, "severity") and entry.severity:
            sev = str(entry.severity)
            if sev.isdigit():
                severity_map = {
                    "0": "DEFAULT", "100": "DEBUG", "200": "INFO",
                    "300": "NOTICE", "400": "WARNING", "500": "ERROR",
                    "600": "CRITICAL", "700": "ALERT", "800": "EMERGENCY"
                }
                return severity_map.get(sev, "ERROR")
            return sev.upper()
    except Exception:
        pass
    return "ERROR"


# ── GCP Client Management ──────────────────────────────────────

def _create_client(project_id: str, service_account_json: Optional[str] = None) -> gcp_logging.Client:
    """Create a GCP Logging client."""
    if service_account_json:
        # Write the JSON to a temp file for authentication
        info = json.loads(service_account_json)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return gcp_logging.Client(project=project_id, credentials=credentials)
    else:
        # Use Application Default Credentials
        return gcp_logging.Client(project=project_id)


# ── Public API ──────────────────────────────────────────────────

def test_connection(project_id: str, service_account_json: Optional[str] = None) -> ConnectionTestResult:
    """Test GCP connection and return available services."""
    try:
        client = _create_client(project_id, service_account_json)

        # Try to list a few log entries to verify access
        entries = list(client.list_entries(
            filter_=f'timestamp >= "{(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}"',
            max_results=5,
            order_by=gcp_logging.DESCENDING,
        ))

        services = set()
        for entry in entries:
            svc = extract_service_name(entry)
            if svc:
                services.add(svc)

        return ConnectionTestResult(
            success=True,
            project_id=project_id,
            message=f"Successfully connected to GCP project '{project_id}'. Found {len(entries)} recent log entries.",
            available_services=sorted(list(services)),
        )
    except Exception as e:
        return ConnectionTestResult(
            success=False,
            project_id=project_id,
            message=f"Connection failed: {str(e)}",
            available_services=[],
        )


def fetch_dashboard_data(
    project_id: str,
    hours_back: int = 24,
    service_account_json: Optional[str] = None,
    service_names: Optional[list[str]] = None,
) -> DashboardSummary:
    """Fetch and analyze GCP logs to produce a complete dashboard summary."""

    client = _create_client(project_id, service_account_json)
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(hours=hours_back)

    # ── Build log filter ────────────────────────────────────────
    base_filter = f'timestamp >= "{start_time.isoformat()}" AND timestamp <= "{now.isoformat()}"'

    # We want errors, warnings, and any HTTP requests (for latency analysis)
    error_filter = f'{base_filter} AND (severity >= ERROR OR httpRequest.status >= 500 OR httpRequest.latency > "2s")'

    if service_names:
        svc_filter = " OR ".join([f'resource.labels.service_name="{s}"' for s in service_names])
        error_filter = f'{error_filter} AND ({svc_filter})'

    # ── Fetch log entries ───────────────────────────────────────
    raw_entries = []
    try:
        entries_iter = client.list_entries(
            filter_=error_filter,
            max_results=2000,
            order_by=gcp_logging.DESCENDING,
        )
        raw_entries = list(entries_iter)
    except Exception as e:
        print(f"Error fetching logs: {e}")

    # ── Process entries ─────────────────────────────────────────
    processed_entries: list[LogEntry] = []
    error_logs: list[LogEntry] = []
    slow_logs: list[LogEntry] = []
    batch_statuses: list[BatchStatus] = []
    service_stats: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "success": 0, "error": 0, "warning": 0,
        "latencies": [], "errors": [],
    })
    hourly_errors: dict[str, int] = defaultdict(int)
    root_cause_counts: dict[str, int] = defaultdict(int)

    for entry in raw_entries:
        message = _get_message(entry)
        severity = _get_severity(entry)
        service = extract_service_name(entry)
        http_status = extract_http_status(entry)
        latency = extract_latency(entry)
        trace_id = extract_trace_id(entry)

        entry_dict = {
            "message": message,
            "severity": severity,
            "http_status": http_status,
            "latency_ms": latency,
        }

        category = categorize_log(entry_dict)
        root_cause = analyze_root_cause(message)

        timestamp_str = ""
        try:
            if hasattr(entry, "timestamp") and entry.timestamp:
                ts = entry.timestamp
                timestamp_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                # Track hourly error trend
                if severity in ("ERROR", "CRITICAL"):
                    hour_key = ts.strftime("%Y-%m-%d %H:00") if hasattr(ts, "strftime") else ""
                    if hour_key:
                        hourly_errors[hour_key] += 1
        except Exception:
            timestamp_str = str(datetime.now(timezone.utc))

        log_name = ""
        try:
            log_name = entry.log_name if hasattr(entry, "log_name") else ""
        except Exception:
            pass

        resource_type = ""
        try:
            if hasattr(entry, "resource") and entry.resource:
                resource_type = entry.resource.type if hasattr(entry.resource, "type") else ""
        except Exception:
            pass

        log_entry = LogEntry(
            timestamp=timestamp_str,
            service_name=service,
            severity=severity,
            category=category,
            message=message[:1500],
            root_cause=root_cause,
            http_status=http_status,
            latency_ms=latency,
            trace_id=trace_id,
            log_name=log_name,
            resource_type=resource_type,
        )

        processed_entries.append(log_entry)

        # ── Aggregate stats ─────────────────────────────────────
        stats = service_stats[service]
        stats["total"] += 1

        if severity in ("ERROR", "CRITICAL"):
            stats["error"] += 1
            error_logs.append(log_entry)
            root_cause_counts[root_cause] += 1
        elif severity == "WARNING":
            stats["warning"] += 1
        else:
            stats["success"] += 1

        if latency and latency > 2000:
            slow_logs.append(log_entry)

        if category == IssueCategory.BATCH_FAILURE.value:
            batch_statuses.append(BatchStatus(
                job_name=service,
                start_time=timestamp_str,
                status="FAILED",
                error_message=message[:500],
                root_cause=root_cause,
            ))

        if latency:
            stats["latencies"].append(latency)

    # ── Build service health summaries ──────────────────────────
    services_health: list[ServiceHealth] = []
    for svc_name, stats in service_stats.items():
        latencies = stats["latencies"]
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        max_lat = max(latencies) if latencies else 0
        total = stats["total"] or 1
        error_rate = (stats["error"] / total) * 100

        if error_rate > 10:
            status = "CRITICAL"
        elif error_rate > 5 or avg_lat > 2000:
            status = "DEGRADED"
        else:
            status = "HEALTHY"

        services_health.append(ServiceHealth(
            service_name=svc_name,
            total_requests=stats["total"],
            success_count=stats["success"],
            error_count=stats["error"],
            warning_count=stats["warning"],
            avg_latency_ms=round(avg_lat, 2),
            max_latency_ms=round(max_lat, 2),
            error_rate=round(error_rate, 2),
            status=status,
        ))

    # ── Build hourly trend ──────────────────────────────────────
    hourly_trend = [
        {"hour": hour, "error_count": count}
        for hour, count in sorted(hourly_errors.items())
    ]

    # ── Build root cause distribution ───────────────────────────
    rc_distribution = [
        {"root_cause": cause, "count": count}
        for cause, count in sorted(root_cause_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # ── Count summaries ─────────────────────────────────────────
    api_500 = sum(1 for e in processed_entries if e.category == IssueCategory.API_500.value)
    api_502 = sum(1 for e in processed_entries if e.category == IssueCategory.API_502.value)
    batch_fail_count = sum(1 for e in processed_entries if e.category == IssueCategory.BATCH_FAILURE.value)
    slow_count = len(slow_logs)
    total_errors = sum(1 for e in processed_entries if e.severity in ("ERROR", "CRITICAL"))
    total_warnings = sum(1 for e in processed_entries if e.severity == "WARNING")

    return DashboardSummary(
        project_id=project_id,
        query_period_hours=hours_back,
        fetched_at=now.isoformat(),
        total_log_entries=len(processed_entries),
        total_errors=total_errors,
        total_warnings=total_warnings,
        batch_failures=batch_fail_count,
        api_500_errors=api_500,
        api_502_errors=api_502,
        slow_requests=slow_count,
        services=services_health,
        batch_statuses=batch_statuses,
        error_logs=error_logs[:200],
        slow_request_logs=slow_logs[:100],
        hourly_error_trend=hourly_trend,
        root_cause_distribution=rc_distribution,
    )
