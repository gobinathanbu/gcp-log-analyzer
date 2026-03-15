"""
Pydantic models for the GCP Log Analyzer Dashboard.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# ── Request Models ──────────────────────────────────────────────

class GCPConnectionRequest(BaseModel):
    """Request model for connecting to GCP."""
    project_id: str = Field(..., description="GCP Project ID")
    service_account_json: Optional[str] = Field(
        None, description="Service account JSON content (optional if using default credentials)"
    )


class LogQueryRequest(BaseModel):
    """Request model for querying logs."""
    project_id: str
    hours_back: int = Field(default=24, ge=1, le=168, description="Hours to look back (1-168)")
    service_names: Optional[list[str]] = Field(
        default=None, description="Filter by specific microservice names"
    )


# ── Enums ───────────────────────────────────────────────────────

class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class IssueCategory(str, Enum):
    BATCH_FAILURE = "BATCH_FAILURE"
    API_500 = "API_500"
    API_502 = "API_502"
    API_504 = "API_504"
    SLOW_REQUEST = "SLOW_REQUEST"
    DB_TIMEOUT = "DB_TIMEOUT"
    OOM = "OUT_OF_MEMORY"
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    UNKNOWN = "UNKNOWN"


class RootCause(str, Enum):
    DATABASE_TIMEOUT = "Database Connection Timeout"
    CONNECTION_POOL_EXHAUSTED = "Connection Pool Exhausted"
    SERVICE_UNAVAILABLE = "Downstream Service Unavailable"
    OUT_OF_MEMORY = "Out of Memory (OOM)"
    NULL_POINTER = "NullPointerException / Unhandled Null"
    DATA_INTEGRITY = "Data Integrity Violation"
    NETWORK_TIMEOUT = "Network Timeout"
    GC_PAUSE = "JVM Garbage Collection Pause"
    QUERY_SLOW = "Slow Database Query"
    RATE_LIMITED = "Rate Limited / Throttled"
    AUTH_FAILURE = "Authentication / Authorization Failure"
    UNKNOWN = "Unknown Root Cause"


# ── Response Models ─────────────────────────────────────────────

class ContextClue(BaseModel):
    """A nearby log event that helps explain why an error occurred."""
    timestamp: str
    clue_type: str  # e.g. "POD_RESTART", "DB_DOWN", "OOM_KILL", "HEALTH_CHECK_FAIL"
    service_name: str
    message: str
    severity: str


class LogEntry(BaseModel):
    """A single processed log entry."""
    timestamp: str
    service_name: str
    severity: str
    category: str
    message: str
    root_cause: str
    http_status: Optional[int] = None
    latency_ms: Optional[float] = None
    trace_id: Optional[str] = None
    log_name: Optional[str] = None
    resource_type: Optional[str] = None
    context_clues: list[ContextClue] = []


class ServiceHealth(BaseModel):
    """Health summary for a single microservice."""
    service_name: str
    total_requests: int = 0
    success_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    error_rate: float = 0.0
    status: str = "HEALTHY"  # HEALTHY, DEGRADED, CRITICAL


class BatchStatus(BaseModel):
    """Status of a batch job."""
    job_name: str
    scheduled_time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status: str  # SUCCESS, FAILED, RUNNING, NOT_STARTED
    records_processed: Optional[int] = None
    error_message: Optional[str] = None
    root_cause: Optional[str] = None


class DashboardSummary(BaseModel):
    """Complete dashboard summary response."""
    project_id: str
    query_period_hours: int
    fetched_at: str
    total_log_entries: int
    total_errors: int
    total_warnings: int
    batch_failures: int
    api_500_errors: int
    api_502_errors: int
    slow_requests: int
    services: list[ServiceHealth]
    batch_statuses: list[BatchStatus]
    error_logs: list[LogEntry]
    slow_request_logs: list[LogEntry]
    hourly_error_trend: list[dict]
    root_cause_distribution: list[dict]


class ConnectionTestResult(BaseModel):
    """Result of a GCP connection test."""
    success: bool
    project_id: str
    message: str
    available_services: list[str] = []
