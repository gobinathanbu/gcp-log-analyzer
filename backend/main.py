"""
FastAPI Backend — GCP Log Analyzer Dashboard API.
Exposes REST endpoints for the Angular frontend to consume.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

from models import (
    GCPConnectionRequest, LogQueryRequest,
    DashboardSummary, ConnectionTestResult,
)
from gcp_log_service import test_connection, fetch_dashboard_data


# ── App Setup ───────────────────────────────────────────────────

app = FastAPI(
    title="GCP Log Analyzer API",
    description="Backend API for the GCP Log Analyzer Dashboard. Fetches and analyzes batch failures, API errors, and slow requests from Google Cloud Logging.",
    version="1.0.0",
)

# CORS — Allow Angular dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:4300", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for the current session's service account JSON
_session_store: dict = {}


# ── Health Check ────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "UP",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "gcp-log-analyzer-api",
    }


# ── GCP Connection ──────────────────────────────────────────────

@app.post("/api/connect", response_model=ConnectionTestResult)
async def connect_to_gcp(
    project_id: str = Form(...),
    service_account_file: Optional[UploadFile] = File(None),
):
    """
    Test connection to GCP using the provided project ID and optional service account key.
    The service account file (JSON) is stored in-memory for subsequent API calls.
    """
    sa_json: Optional[str] = None

    if service_account_file:
        try:
            content = await service_account_file.read()
            sa_json = content.decode("utf-8")
            # Validate it's valid JSON
            json.loads(sa_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid service account JSON file.")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")

    try:
        result = test_connection(project_id, sa_json)

        if result.success:
            _session_store["project_id"] = project_id
            _session_store["sa_json"] = sa_json

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")


@app.get("/api/connection-status")
def connection_status():
    """Check if a GCP project is currently connected."""
    if "project_id" in _session_store:
        return {
            "connected": True,
            "project_id": _session_store["project_id"],
        }
    return {"connected": False, "project_id": None}


@app.post("/api/disconnect")
def disconnect():
    """Clear the current GCP session."""
    _session_store.clear()
    return {"message": "Disconnected successfully."}


# ── Dashboard Data ──────────────────────────────────────────────

@app.get("/api/dashboard", response_model=DashboardSummary)
def get_dashboard(
    hours_back: int = 24,
    service_names: Optional[str] = None,
):
    """
    Fetch dashboard data from GCP Cloud Logging.
    Requires an active GCP connection (call /api/connect first).

    Args:
        hours_back: Number of hours to look back (1-168, default 24).
        service_names: Comma-separated list of service names to filter by.
    """
    if "project_id" not in _session_store:
        raise HTTPException(
            status_code=400,
            detail="No GCP project connected. Please connect first via /api/connect.",
        )

    project_id = _session_store["project_id"]
    sa_json = _session_store.get("sa_json")

    svc_list = None
    if service_names:
        svc_list = [s.strip() for s in service_names.split(",") if s.strip()]

    try:
        data = fetch_dashboard_data(
            project_id=project_id,
            hours_back=hours_back,
            service_account_json=sa_json,
            service_names=svc_list,
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching dashboard data: {str(e)}")


# ── Demo / Mock Endpoint ───────────────────────────────────────

@app.get("/api/dashboard/demo", response_model=DashboardSummary)
def get_demo_dashboard():
    """
    Returns realistic mock dashboard data for demo/testing purposes.
    No GCP connection required.
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)

    from models import LogEntry, ServiceHealth, BatchStatus

    services = [
        ServiceHealth(
            service_name="auth-service",
            total_requests=4520,
            success_count=4480,
            error_count=35,
            warning_count=5,
            avg_latency_ms=145.32,
            max_latency_ms=890.5,
            error_rate=0.77,
            status="HEALTHY",
        ),
        ServiceHealth(
            service_name="order-service",
            total_requests=8930,
            success_count=8650,
            error_count=240,
            warning_count=40,
            avg_latency_ms=2350.8,
            max_latency_ms=12500.0,
            error_rate=2.69,
            status="DEGRADED",
        ),
        ServiceHealth(
            service_name="payment-service",
            total_requests=3210,
            success_count=2890,
            error_count=290,
            warning_count=30,
            avg_latency_ms=890.45,
            max_latency_ms=8200.0,
            error_rate=9.03,
            status="DEGRADED",
        ),
        ServiceHealth(
            service_name="inventory-service",
            total_requests=6780,
            success_count=6700,
            error_count=60,
            warning_count=20,
            avg_latency_ms=98.12,
            max_latency_ms=450.0,
            error_rate=0.88,
            status="HEALTHY",
        ),
        ServiceHealth(
            service_name="notification-service",
            total_requests=2150,
            success_count=1800,
            error_count=320,
            warning_count=30,
            avg_latency_ms=310.9,
            max_latency_ms=5600.0,
            error_rate=14.88,
            status="CRITICAL",
        ),
    ]

    batch_statuses = [
        BatchStatus(
            job_name="order-reconciliation-batch",
            scheduled_time=(now.replace(hour=0, minute=0) - timedelta(days=0)).isoformat(),
            start_time=(now.replace(hour=0, minute=0, second=5) - timedelta(days=0)).isoformat(),
            end_time=(now.replace(hour=0, minute=12, second=45) - timedelta(days=0)).isoformat(),
            status="FAILED",
            records_processed=8420,
            error_message="org.springframework.dao.DataIntegrityViolationException: could not execute batch; SQL [insert into order_reconciliation ...]; constraint [uk_order_ref]",
            root_cause="Data Integrity Violation",
        ),
        BatchStatus(
            job_name="payment-settlement-batch",
            scheduled_time=(now.replace(hour=0, minute=30) - timedelta(days=0)).isoformat(),
            start_time=(now.replace(hour=0, minute=30, second=2) - timedelta(days=0)).isoformat(),
            end_time=(now.replace(hour=1, minute=15, second=30) - timedelta(days=0)).isoformat(),
            status="FAILED",
            records_processed=3200,
            error_message="com.zaxxer.hikari.pool.HikariPool$PoolInitializationException: Failed to initialize pool: Connection refused to host: 10.128.0.15:5432",
            root_cause="Connection Pool Exhausted",
        ),
        BatchStatus(
            job_name="inventory-sync-batch",
            scheduled_time=(now.replace(hour=1, minute=0) - timedelta(days=0)).isoformat(),
            start_time=(now.replace(hour=1, minute=0, second=3) - timedelta(days=0)).isoformat(),
            end_time=(now.replace(hour=1, minute=8, second=12) - timedelta(days=0)).isoformat(),
            status="SUCCESS",
            records_processed=15200,
            error_message=None,
            root_cause=None,
        ),
        BatchStatus(
            job_name="user-notification-batch",
            scheduled_time=(now.replace(hour=2, minute=0) - timedelta(days=0)).isoformat(),
            start_time=(now.replace(hour=2, minute=0, second=8) - timedelta(days=0)).isoformat(),
            status="FAILED",
            records_processed=0,
            error_message="java.lang.OutOfMemoryError: Java heap space at com.app.notification.service.BulkEmailSender.loadTemplates",
            root_cause="Out of Memory (OOM)",
        ),
    ]

    error_logs = [
        LogEntry(
            timestamp=(now - timedelta(hours=2, minutes=15)).isoformat(),
            service_name="order-service",
            severity="ERROR",
            category="API_500",
            message="java.lang.NullPointerException: Cannot invoke method getId() on null reference at com.app.order.service.OrderService.processOrder(OrderService.java:142)",
            root_cause="NullPointerException / Unhandled Null",
            http_status=500,
            latency_ms=45.2,
            trace_id="abc123def456",
        ),
        LogEntry(
            timestamp=(now - timedelta(hours=3, minutes=42)).isoformat(),
            service_name="payment-service",
            severity="ERROR",
            category="API_502",
            message="upstream connect error or disconnect/reset before headers. reset reason: connection failure, transport failure reason: delayed connect error: 111",
            root_cause="Downstream Service Unavailable",
            http_status=502,
            latency_ms=30000.0,
            trace_id="xyz789ghi012",
        ),
        LogEntry(
            timestamp=(now - timedelta(hours=1, minutes=5)).isoformat(),
            service_name="notification-service",
            severity="CRITICAL",
            category="API_500",
            message="org.springframework.jdbc.CannotGetJdbcConnectionException: Failed to obtain JDBC Connection; nested exception is com.zaxxer.hikari.pool.HikariPool$PoolInitializationException: Failed to initialize pool: FATAL: too many connections for role 'app_user'",
            root_cause="Connection Pool Exhausted",
            http_status=500,
            latency_ms=5023.0,
            trace_id="conn_pool_001",
        ),
        LogEntry(
            timestamp=(now - timedelta(hours=5, minutes=20)).isoformat(),
            service_name="order-service",
            severity="ERROR",
            category="API_500",
            message="org.hibernate.exception.JDBCConnectionException: Unable to acquire JDBC Connection; SQL [n/a]; nested exception: connection timed out after 30000ms",
            root_cause="Database Connection Timeout",
            http_status=500,
            latency_ms=30120.5,
            trace_id="db_timeout_001",
        ),
        LogEntry(
            timestamp=(now - timedelta(hours=4)).isoformat(),
            service_name="auth-service",
            severity="ERROR",
            category="API_500",
            message="io.jsonwebtoken.ExpiredJwtException: JWT expired at 2026-03-13T23:45:00Z. Current time: 2026-03-14T00:15:00Z. Token expired 30 minutes ago.",
            root_cause="Authentication / Authorization Failure",
            http_status=500,
            latency_ms=12.5,
            trace_id="auth_exp_001",
        ),
        LogEntry(
            timestamp=(now - timedelta(hours=6, minutes=10)).isoformat(),
            service_name="payment-service",
            severity="ERROR",
            category="API_502",
            message="com.netflix.hystrix.exception.HystrixRuntimeException: PaymentGateway_processPayment timed out and fallback failed.",
            root_cause="Network Timeout",
            http_status=502,
            latency_ms=61000.0,
            trace_id="hystrix_001",
        ),
    ]

    slow_logs = [
        LogEntry(
            timestamp=(now - timedelta(hours=1, minutes=30)).isoformat(),
            service_name="order-service",
            severity="WARNING",
            category="SLOW_REQUEST",
            message="GET /api/orders?page=1&size=100 — Slow query detected: SELECT * FROM orders o JOIN order_items oi ON o.id = oi.order_id WHERE o.status = 'PENDING' — Full table scan on 2.4M rows",
            root_cause="Slow Database Query",
            http_status=200,
            latency_ms=8540.0,
            trace_id="slow_001",
        ),
        LogEntry(
            timestamp=(now - timedelta(hours=2, minutes=50)).isoformat(),
            service_name="order-service",
            severity="WARNING",
            category="SLOW_REQUEST",
            message="POST /api/orders/bulk-create — N+1 query problem detected: 1 query for orders + 500 individual queries for order_items. Total DB time: 4.2s",
            root_cause="Slow Database Query",
            http_status=201,
            latency_ms=5200.0,
            trace_id="slow_002",
        ),
        LogEntry(
            timestamp=(now - timedelta(hours=3, minutes=15)).isoformat(),
            service_name="payment-service",
            severity="WARNING",
            category="SLOW_REQUEST",
            message="POST /api/payments/process — GC pause detected: 2.8s full GC (old gen: 95% used). Heap: 3.2GB/4GB. Consider increasing max heap or optimizing object creation.",
            root_cause="JVM Garbage Collection Pause",
            http_status=200,
            latency_ms=4800.0,
            trace_id="slow_003",
        ),
        LogEntry(
            timestamp=(now - timedelta(hours=4, minutes=45)).isoformat(),
            service_name="notification-service",
            severity="WARNING",
            category="SLOW_REQUEST",
            message="POST /api/notifications/send-bulk — Synchronous call chain: notification-service → auth-service (320ms) → order-service (1200ms) → payment-service (timeout). Total chain latency: 12.4s",
            root_cause="Network Timeout",
            http_status=200,
            latency_ms=12400.0,
            trace_id="slow_004",
        ),
    ]

    hourly_trend = []
    for i in range(24):
        h = (now - timedelta(hours=23 - i))
        import random
        base_errors = random.randint(2, 8)
        # Spike errors during batch hours (midnight-2am)
        hour_of_day = h.hour
        if 0 <= hour_of_day <= 2:
            base_errors = random.randint(25, 65)
        elif 8 <= hour_of_day <= 10:
            base_errors = random.randint(10, 25)
        hourly_trend.append({
            "hour": h.strftime("%Y-%m-%d %H:00"),
            "error_count": base_errors,
        })

    root_cause_dist = [
        {"root_cause": "Connection Pool Exhausted", "count": 145},
        {"root_cause": "Database Connection Timeout", "count": 98},
        {"root_cause": "NullPointerException / Unhandled Null", "count": 72},
        {"root_cause": "Downstream Service Unavailable", "count": 65},
        {"root_cause": "Slow Database Query", "count": 54},
        {"root_cause": "Out of Memory (OOM)", "count": 38},
        {"root_cause": "Network Timeout", "count": 31},
        {"root_cause": "Authentication / Authorization Failure", "count": 22},
        {"root_cause": "JVM Garbage Collection Pause", "count": 15},
        {"root_cause": "Data Integrity Violation", "count": 12},
        {"root_cause": "Unknown Root Cause", "count": 45},
    ]

    return DashboardSummary(
        project_id="demo-project-gcp",
        query_period_hours=24,
        fetched_at=now.isoformat(),
        total_log_entries=25590,
        total_errors=945,
        total_warnings=125,
        batch_failures=3,
        api_500_errors=540,
        api_502_errors=290,
        slow_requests=len(slow_logs),
        services=services,
        batch_statuses=batch_statuses,
        error_logs=error_logs,
        slow_request_logs=slow_logs,
        hourly_error_trend=hourly_trend,
        root_cause_distribution=root_cause_dist,
    )


# ── Run ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
