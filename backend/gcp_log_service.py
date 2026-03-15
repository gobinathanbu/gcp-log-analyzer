"""
GCP Log File Parser — Parses exported GCP Console log files (JSON/CSV).
Applies root-cause analysis for batch failures, API errors, and slow requests.
No GCP API access required — works completely offline with exported files.
"""

import csv
import io
import json
import re
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional

from models import (
    LogEntry, ServiceHealth, BatchStatus, DashboardSummary,
    IssueCategory, RootCause, ContextClue,
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


def categorize_log(message: str, http_status: Optional[int], severity: str) -> str:
    """Categorize a log entry into an issue category."""
    msg_lower = (message or "").lower()
    sev = (severity or "").upper()

    # Check for batch-related failures
    batch_keywords = ["batch", "job", "scheduler", "cron", "scheduled", "spring batch", "step execution"]
    if any(kw in msg_lower for kw in batch_keywords) and sev in ("ERROR", "CRITICAL"):
        return IssueCategory.BATCH_FAILURE.value

    # Check HTTP status codes
    if http_status == 500:
        return IssueCategory.API_500.value
    elif http_status == 502:
        return IssueCategory.API_502.value
    elif http_status == 504:
        return IssueCategory.API_504.value

    # Fallback based on message content
    if "500" in msg_lower and ("internal server error" in msg_lower or "status" in msg_lower):
        return IssueCategory.API_500.value
    elif "502" in msg_lower and ("bad gateway" in msg_lower or "status" in msg_lower):
        return IssueCategory.API_502.value

    return IssueCategory.UNKNOWN.value


# ── File Parsers ────────────────────────────────────────────────

def parse_gcp_json_logs(content: str) -> list[dict]:
    """
    Parse GCP Console exported JSON log entries.
    GCP exports logs either as a JSON array or as newline-delimited JSON (NDJSON).
    """
    entries = []

    # Try JSON array first
    content_stripped = content.strip()
    if content_stripped.startswith("["):
        try:
            raw_entries = json.loads(content_stripped)
            if isinstance(raw_entries, list):
                return raw_entries
        except json.JSONDecodeError:
            pass

    # Try newline-delimited JSON (NDJSON) — each line is a separate JSON object
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip lines that are just commas (sometimes in array-style exports)
        if line in (",", "[", "]"):
            continue
        # Remove trailing comma if present
        if line.endswith(","):
            line = line[:-1]
        try:
            entry = json.loads(line)
            if isinstance(entry, dict):
                entries.append(entry)
        except json.JSONDecodeError:
            continue

    return entries


def parse_csv_logs(content: str) -> list[dict]:
    """Parse CSV exported log entries."""
    entries = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        entries.append(dict(row))
    return entries


def extract_from_gcp_entry(raw: dict) -> dict:
    """
    Extract structured fields from a GCP Console exported JSON log entry.

    GCP JSON log format typically has these fields:
    - timestamp, severity, logName, resource, httpRequest, textPayload,
      jsonPayload, protoPayload, labels, trace, etc.
    """
    result = {}

    # ── Timestamp ───────────────────────────────────────────
    result["timestamp"] = (
        raw.get("timestamp")
        or raw.get("receiveTimestamp")
        or raw.get("Timestamp")
        or raw.get("time")
        or ""
    )

    # ── Severity ────────────────────────────────────────────
    result["severity"] = (
        raw.get("severity")
        or raw.get("Severity")
        or raw.get("level")
        or "ERROR"
    ).upper()

    # ── Message ─────────────────────────────────────────────
    message = ""
    if raw.get("textPayload"):
        message = raw["textPayload"]
    elif raw.get("jsonPayload"):
        jp = raw["jsonPayload"]
        if isinstance(jp, dict):
            for key in ("message", "msg", "error", "errorMessage", "description", "exception"):
                if jp.get(key):
                    message = str(jp[key])
                    break
            if not message:
                message = json.dumps(jp)
        else:
            message = str(jp)
    elif raw.get("protoPayload"):
        pp = raw["protoPayload"]
        if isinstance(pp, dict):
            message = pp.get("status", {}).get("message", "") if isinstance(pp.get("status"), dict) else str(pp)
        else:
            message = str(pp)
    elif raw.get("message") or raw.get("Message"):
        message = raw.get("message") or raw.get("Message", "")

    result["message"] = message[:2000] if message else "No message available"

    # ── Service Name ────────────────────────────────────────
    service = "unknown-service"
    resource = raw.get("resource", {})
    if isinstance(resource, dict):
        labels = resource.get("labels", {})
        if isinstance(labels, dict):
            for key in ("service_name", "container_name", "module_id", "job_name", "service"):
                if labels.get(key):
                    service = labels[key]
                    break
    # Fallback to top-level labels
    if service == "unknown-service":
        top_labels = raw.get("labels", {})
        if isinstance(top_labels, dict):
            for key in ("k8s-pod/app", "app", "service"):
                if top_labels.get(key):
                    service = top_labels[key]
                    break
    # Fallback to logName
    if service == "unknown-service" and raw.get("logName"):
        parts = raw["logName"].split("/")
        service = parts[-1] if parts else "unknown-service"

    result["service_name"] = service

    # ── HTTP Status ─────────────────────────────────────────
    http_status = None
    http_req = raw.get("httpRequest", {})
    if isinstance(http_req, dict):
        status = http_req.get("status") or http_req.get("responseStatusCode")
        if status is not None:
            try:
                http_status = int(status)
            except (ValueError, TypeError):
                pass
    # Fallback: search in message
    if http_status is None:
        status_match = re.search(r'(?:status["\s:=]+|httpStatus["\s:=]+|statusCode["\s:=]+)(\d{3})', message)
        if status_match:
            http_status = int(status_match.group(1))

    result["http_status"] = http_status

    # ── Latency ─────────────────────────────────────────────
    latency_ms = None
    if isinstance(http_req, dict):
        lat = http_req.get("latency")
        if lat:
            if isinstance(lat, str) and lat.endswith("s"):
                try:
                    latency_ms = float(lat[:-1]) * 1000
                except ValueError:
                    pass
            elif isinstance(lat, (int, float)):
                latency_ms = float(lat) * 1000
    # Fallback: search in message
    if latency_ms is None:
        lat_match = re.search(
            r'(?:latency|duration|elapsed|took|responseTime)["\s:=]+(\d+(?:\.\d+)?)\s*(ms|s|seconds|milliseconds)?',
            message, re.IGNORECASE
        )
        if lat_match:
            value = float(lat_match.group(1))
            unit = (lat_match.group(2) or "ms").lower()
            latency_ms = value * 1000 if unit in ("s", "seconds") else value

    result["latency_ms"] = latency_ms

    # ── Trace ID ────────────────────────────────────────────
    trace = raw.get("trace", "")
    if trace and "/" in trace:
        trace = trace.split("/")[-1]
    result["trace_id"] = trace or None

    # ── Log Name & Resource Type ────────────────────────────
    result["log_name"] = raw.get("logName", "")
    result["resource_type"] = resource.get("type", "") if isinstance(resource, dict) else ""

    return result


# ── Main Processing ─────────────────────────────────────────────

def process_uploaded_file(content: str, filename: str) -> DashboardSummary:
    """
    Parse and analyze an uploaded GCP Console log export file.
    Supports JSON (array or NDJSON) and CSV formats.
    """

    # ── Parse the file ──────────────────────────────────────
    if filename.lower().endswith(".csv"):
        raw_entries = parse_csv_logs(content)
    else:
        raw_entries = parse_gcp_json_logs(content)

    if not raw_entries:
        raise ValueError(f"No log entries found in the uploaded file '{filename}'. Please check the file format.")

    # ── Process entries ─────────────────────────────────────
    processed_entries: list[LogEntry] = []
    error_logs: list[LogEntry] = []
    slow_logs: list[LogEntry] = []
    batch_statuses: list[BatchStatus] = []

    service_stats: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "success": 0, "error": 0, "warning": 0, "latencies": [],
    })
    hourly_errors: dict[str, int] = defaultdict(int)
    root_cause_counts: dict[str, int] = defaultdict(int)

    for raw in raw_entries:
        extracted = extract_from_gcp_entry(raw)

        message = extracted["message"]
        severity = extracted["severity"]
        service = extracted["service_name"]
        http_status = extracted["http_status"]
        latency_ms = extracted["latency_ms"]

        category = categorize_log(message, http_status, severity)
        
        # Override severity to ERROR if it's an API Error (e.g. 500/502), 
        # because GCP access logs often come in with INFO severity.
        if category in (IssueCategory.API_500.value, IssueCategory.API_502.value):
            severity = "ERROR"

        root_cause = analyze_root_cause(message)
        
        # If there's no stack trace pattern matched, give a better default for HTTP errors
        if root_cause == RootCause.UNKNOWN.value:
            if category == IssueCategory.API_500.value:
                root_cause = "Internal Server Error (No exact stack trace in this log entry)"
            elif category == IssueCategory.API_502.value:
                root_cause = "Bad Gateway (Downstream service failed/unreachable)"
            elif category == IssueCategory.API_504.value:
                root_cause = "Gateway Timeout"

        log_entry = LogEntry(
            timestamp=extracted["timestamp"],
            service_name=service,
            severity=severity,
            category=category,
            message=message[:1500],
            root_cause=root_cause,
            http_status=http_status,
            latency_ms=latency_ms,
            trace_id=extracted["trace_id"],
            log_name=extracted["log_name"],
            resource_type=extracted["resource_type"],
        )

        processed_entries.append(log_entry)

        # ── Aggregate stats ─────────────────────────────────
        stats = service_stats[service]
        stats["total"] += 1

        if severity in ("ERROR", "CRITICAL"):
            stats["error"] += 1
            error_logs.append(log_entry)
            root_cause_counts[root_cause] += 1

            # Hourly trend
            ts = extracted["timestamp"]
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    hour_key = dt.strftime("%Y-%m-%d %H:00")
                    hourly_errors[hour_key] += 1
                except (ValueError, TypeError):
                    pass
        elif severity == "WARNING":
            stats["warning"] += 1
        else:
            stats["success"] += 1

        if latency_ms and latency_ms > 2000:
            slow_logs.append(log_entry)

        if category == IssueCategory.BATCH_FAILURE.value:
            batch_statuses.append(BatchStatus(
                job_name=service,
                start_time=extracted["timestamp"],
                status="FAILED",
                error_message=message[:500],
                root_cause=root_cause,
            ))

        if latency_ms:
            stats["latencies"].append(latency_ms)

    # ── Build service health summaries ──────────────────────
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

    # ── Contextual Correlation ─────────────────────────────────
    # For each error log, scan ALL entries within ±5 min window
    # to find evidence of pod crashes, DB failures, OOM, etc.
    _correlate_context_clues(error_logs, processed_entries)
    _correlate_context_clues(slow_logs, processed_entries)

    # ── Build hourly trend ──────────────────────────────────
    hourly_trend = [
        {"hour": hour, "error_count": count}
        for hour, count in sorted(hourly_errors.items())
    ]

    # ── Build root cause distribution ───────────────────────
    rc_distribution = [
        {"root_cause": cause, "count": count}
        for cause, count in sorted(root_cause_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # ── Count summaries ─────────────────────────────────────
    api_500 = sum(1 for e in processed_entries if e.category == IssueCategory.API_500.value)
    api_502 = sum(1 for e in processed_entries if e.category == IssueCategory.API_502.value)
    batch_fail_count = sum(1 for e in processed_entries if e.category == IssueCategory.BATCH_FAILURE.value)
    total_errors = sum(1 for e in processed_entries if e.severity in ("ERROR", "CRITICAL"))
    total_warnings = sum(1 for e in processed_entries if e.severity == "WARNING")

    return DashboardSummary(
        project_id=f"Uploaded: {filename}",
        query_period_hours=0,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        total_log_entries=len(processed_entries),
        total_errors=total_errors,
        total_warnings=total_warnings,
        batch_failures=batch_fail_count,
        api_500_errors=api_500,
        api_502_errors=api_502,
        slow_requests=len(slow_logs),
        services=services_health,
        batch_statuses=batch_statuses,
        error_logs=error_logs[:200],
        slow_request_logs=slow_logs[:100],
        hourly_error_trend=hourly_trend,
        root_cause_distribution=rc_distribution,
    )


# ── Contextual Correlation Engine ───────────────────────────────
#
# For each error, scans all log entries within a ±5 minute window
# looking for evidence of WHY the error happened:
#   - Pod restarts / CrashLoopBackOff
#   - Database connection failures
#   - OOM kills
#   - Health check failures
#   - Connection pool exhaustion
#   - Upstream/downstream service failures
#   - Deployment rollouts
# ────────────────────────────────────────────────────────────────

CONTEXT_PATTERNS = [
    # (regex_pattern, clue_type, human_readable_label)
    (r"(?i)(pod|container).*?(restart|crash|CrashLoopBackOff|terminated|OOMKilled|BackOff|kill)",
     "POD_RESTART", "⚠️ Pod/Container was restarting or crashed"),
    (r"(?i)(readiness|liveness|startup)\s*(probe|check)\s*(fail|timed\s*out|unhealthy|error)",
     "HEALTH_CHECK_FAIL", "🏥 Health check (readiness/liveness probe) was failing"),
    (r"(?i)(connection\s*refused|ECONNREFUSED|connect\s*timed\s*out|dial\s*tcp.*refused)",
     "CONNECTION_REFUSED", "🔌 Connection was being refused (target service/pod was down)"),
    (r"(?i)(hikari|connection\s*pool|pool\s*exhausted|cannot\s*get.*connection|no\s*available\s*connection|too\s*many\s*connections)",
     "DB_POOL_EXHAUSTED", "🗄️ Database connection pool was exhausted (all connections in use)"),
    (r"(?i)(jdbc|database|db|mysql|postgres|sql).*?(timeout|timed\s*out|refused|unavailable|unreachable|down|fail)",
     "DB_DOWN", "💾 Database was unreachable or timing out"),
    (r"(?i)(OutOfMemoryError|OOMKilled|oom|heap\s*space|memory\s*limit|cannot\s*allocate\s*memory)",
     "OOM_KILL", "💀 Out of Memory — JVM heap or container memory limit was exceeded"),
    (r"(?i)(full\s*gc|gc\s*pause|garbage\s*collection|stop.*world|gc.*overhead)",
     "GC_PRESSURE", "♻️ Heavy garbage collection — JVM was under memory pressure"),
    (r"(?i)(deploy|rollout|rolling\s*update|image\s*pull|scaling|replica|autoscal)",
     "DEPLOYMENT", "🚀 A deployment/rollout was in progress"),
    (r"(?i)(upstream|downstream|backend)\s*(timeout|unavailable|fail|error|unhealthy|reset|connect\s*error)",
     "UPSTREAM_FAIL", "🔗 Upstream/downstream dependency was failing"),
    (r"(?i)(503\s|service\s*unavailable|no\s*healthy\s*upstream|no\s*endpoints)",
     "SERVICE_UNAVAILABLE", "🚫 Service was returning 503 / no healthy endpoints available"),
    (r"(?i)(disk\s*(full|space|quota)|no\s*space\s*left|storage.*exceeded)",
     "DISK_FULL", "💿 Disk space was full or storage quota exceeded"),
    (r"(?i)(certificate|tls|ssl|x509|handshake)\s*(error|fail|expired|invalid|mismatch)",
     "TLS_ERROR", "🔒 TLS/SSL certificate error"),
    (r"(?i)(dns|name\s*resolution|resolve.*fail|nxdomain|could\s*not\s*resolve)",
     "DNS_FAILURE", "🌐 DNS resolution failed — could not resolve hostname"),
    (r"(?i)(rate\s*limit|throttl|429|too\s*many\s*requests|quota.*exceeded)",
     "RATE_LIMITED", "🚦 Rate limit or quota was exceeded"),
]


def _parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Try to parse a timestamp string into a datetime object."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    # Try other common formats
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _correlate_context_clues(target_logs: list[LogEntry], all_entries: list[LogEntry],
                              window_minutes: int = 5):
    """
    For each error in target_logs, scan all_entries within ±window_minutes
    and find context clues that explain the root cause.
    """
    for error_entry in target_logs:
        error_ts = _parse_timestamp(error_entry.timestamp)
        if not error_ts:
            continue

        window_start = error_ts - timedelta(minutes=window_minutes)
        window_end = error_ts + timedelta(minutes=window_minutes)

        clues: list[ContextClue] = []
        seen_clue_types: set[str] = set()  # avoid duplicate clue types per error

        for entry in all_entries:
            # Skip the error entry itself
            if entry.timestamp == error_entry.timestamp and entry.message == error_entry.message:
                continue

            entry_ts = _parse_timestamp(entry.timestamp)
            if not entry_ts:
                continue

            # Check if within the time window
            if not (window_start <= entry_ts <= window_end):
                continue

            msg = entry.message or ""
            for pattern, clue_type, label in CONTEXT_PATTERNS:
                if clue_type in seen_clue_types:
                    continue  # One clue of each type per error is enough
                if re.search(pattern, msg):
                    clues.append(ContextClue(
                        timestamp=entry.timestamp,
                        clue_type=clue_type,
                        service_name=entry.service_name,
                        message=f"{label}\n→ {msg[:300]}",
                        severity=entry.severity,
                    ))
                    seen_clue_types.add(clue_type)
                    break  # Don't match multiple patterns on the same entry

            if len(clues) >= 8:  # Cap at 8 clues per error
                break

        # ── Upgrade root cause if we found compelling evidence ──
        if clues and error_entry.root_cause.startswith(("Internal Server Error", "Bad Gateway", "Unknown")):
            # Pick the most critical clue as the upgraded root cause
            priority_order = ["OOM_KILL", "DB_DOWN", "DB_POOL_EXHAUSTED", "POD_RESTART",
                              "HEALTH_CHECK_FAIL", "CONNECTION_REFUSED", "UPSTREAM_FAIL",
                              "SERVICE_UNAVAILABLE", "DNS_FAILURE", "GC_PRESSURE",
                              "DISK_FULL", "TLS_ERROR", "DEPLOYMENT", "RATE_LIMITED"]
            for prio in priority_order:
                for clue in clues:
                    if clue.clue_type == prio:
                        # Extract the human-readable label (before the " → " part)
                        label_part = clue.message.split("\n")[0] if "\n" in clue.message else clue.message
                        error_entry.root_cause = f"{label_part} (on {clue.service_name} at {clue.timestamp})"
                        break
                if not error_entry.root_cause.startswith(("Internal Server Error", "Bad Gateway", "Unknown")):
                    break

        error_entry.context_clues = clues

