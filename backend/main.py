"""
FastAPI Backend — GCP Log Analyzer Dashboard API (File Upload Mode).
Accepts exported GCP Console log files (JSON/CSV), parses them, and returns dashboard data.
No GCP API access required.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models import DashboardSummary
from gcp_log_service import process_uploaded_file

class GcloudFetchRequest(BaseModel):
    project_id: str
    filter_query: str = 'severity>=ERROR'
    hours: int = 24
    limit: int = 1000


# ── App Setup ───────────────────────────────────────────────────

app = FastAPI(
    title="GCP Log Analyzer API",
    description="Upload GCP Console exported log files (JSON/CSV) to analyze batch failures, API errors, and slow requests. No GCP API access required.",
    version="2.0.0",
)

# CORS — Allow Angular dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:4300", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {
        "status": "UP",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "gcp-log-analyzer-api",
        "mode": "file-upload",
    }


# ── File Upload & Parse ────────────────────────────────────────

@app.post("/api/upload", response_model=DashboardSummary)
async def upload_log_file(file: UploadFile = File(...)):
    """
    Upload a GCP Console exported log file (JSON or CSV) for analysis.

    How to export from GCP Console:
    1. Go to Cloud Logging → Logs Explorer
    2. Filter your logs (e.g., by severity, service)
    3. Click "Actions" → "Download logs"
    4. Choose JSON or CSV format
    5. Upload the downloaded file here
    """
    # Validate file type
    filename = file.filename or "unknown.json"
    if not filename.lower().endswith((".json", ".csv")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Please upload a .json or .csv file exported from GCP Console."
        )

    # Read file content
    try:
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File encoding error. Please ensure the file is UTF-8 encoded.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")

    if not content.strip():
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    # Parse and analyze
    try:
        result = process_uploaded_file(content, filename)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


# ── Gcloud Fetch Endpoint ──────────────────────────────────────

@app.post("/api/fetch-gcloud", response_model=DashboardSummary)
async def fetch_via_gcloud(req: GcloudFetchRequest):
    """
    Fetch exact root causes using the gcloud CLI itself,
    as an alternative to the GCP Cloud API or file uploads.
    """
    import subprocess
    
    start_time = (datetime.now(timezone.utc) - timedelta(hours=req.hours)).isoformat()
    query = f'{req.filter_query} AND timestamp >= "{start_time}"'
    
    cmd = [
        "gcloud", "logging", "read",
        query,
        "--project", req.project_id,
        "--format", "json",
        "--limit", str(req.limit)
    ]
    
    # Optional: Log the command being run for debugging purposes
    print(f"Executing: {' '.join(cmd)}")
    
    try:
        # We use timeout=120 as reading logs from gcloud can take some time
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        content = result.stdout
        
        if not content.strip() or content.strip() in ("[]", ""):
            raise HTTPException(status_code=400, detail="No logs found using the specified gcloud query. Try increasing the hours or checking your filter.")
            
        summary = process_uploaded_file(content, f"gcloud-{req.project_id}.json")
        return summary
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="gcloud logging read timed out.")
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"gcloud CLI error: {e.stderr}")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing gcloud logs: {str(e)}")


# ── Demo Endpoint ──────────────────────────────────────────────

@app.get("/api/dashboard/demo", response_model=DashboardSummary)
def get_demo_dashboard():
    """
    Returns realistic mock dashboard data for demo/testing purposes.
    No file upload required.
    """
    from models import LogEntry, ServiceHealth, BatchStatus
    import random

    now = datetime.now(timezone.utc)

    services = [
        ServiceHealth(service_name="auth-service", total_requests=4520, success_count=4480,
                      error_count=35, warning_count=5, avg_latency_ms=145.32, max_latency_ms=890.5,
                      error_rate=0.77, status="HEALTHY"),
        ServiceHealth(service_name="order-service", total_requests=8930, success_count=8650,
                      error_count=240, warning_count=40, avg_latency_ms=2350.8, max_latency_ms=12500.0,
                      error_rate=2.69, status="DEGRADED"),
        ServiceHealth(service_name="payment-service", total_requests=3210, success_count=2890,
                      error_count=290, warning_count=30, avg_latency_ms=890.45, max_latency_ms=8200.0,
                      error_rate=9.03, status="DEGRADED"),
        ServiceHealth(service_name="inventory-service", total_requests=6780, success_count=6700,
                      error_count=60, warning_count=20, avg_latency_ms=98.12, max_latency_ms=450.0,
                      error_rate=0.88, status="HEALTHY"),
        ServiceHealth(service_name="notification-service", total_requests=2150, success_count=1800,
                      error_count=320, warning_count=30, avg_latency_ms=310.9, max_latency_ms=5600.0,
                      error_rate=14.88, status="CRITICAL"),
    ]

    batch_statuses = [
        BatchStatus(job_name="order-reconciliation-batch",
                    scheduled_time=(now.replace(hour=0, minute=0) - timedelta(days=0)).isoformat(),
                    start_time=(now.replace(hour=0, minute=0, second=5) - timedelta(days=0)).isoformat(),
                    end_time=(now.replace(hour=0, minute=12, second=45) - timedelta(days=0)).isoformat(),
                    status="FAILED", records_processed=8420,
                    error_message="org.springframework.dao.DataIntegrityViolationException: could not execute batch; SQL [insert into order_reconciliation ...]; constraint [uk_order_ref]",
                    root_cause="Data Integrity Violation"),
        BatchStatus(job_name="payment-settlement-batch",
                    scheduled_time=(now.replace(hour=0, minute=30) - timedelta(days=0)).isoformat(),
                    start_time=(now.replace(hour=0, minute=30, second=2) - timedelta(days=0)).isoformat(),
                    end_time=(now.replace(hour=1, minute=15, second=30) - timedelta(days=0)).isoformat(),
                    status="FAILED", records_processed=3200,
                    error_message="com.zaxxer.hikari.pool.HikariPool$PoolInitializationException: Failed to initialize pool: Connection refused to host: 10.128.0.15:5432",
                    root_cause="Connection Pool Exhausted"),
        BatchStatus(job_name="inventory-sync-batch",
                    scheduled_time=(now.replace(hour=1, minute=0) - timedelta(days=0)).isoformat(),
                    start_time=(now.replace(hour=1, minute=0, second=3) - timedelta(days=0)).isoformat(),
                    end_time=(now.replace(hour=1, minute=8, second=12) - timedelta(days=0)).isoformat(),
                    status="SUCCESS", records_processed=15200),
        BatchStatus(job_name="user-notification-batch",
                    scheduled_time=(now.replace(hour=2, minute=0) - timedelta(days=0)).isoformat(),
                    start_time=(now.replace(hour=2, minute=0, second=8) - timedelta(days=0)).isoformat(),
                    status="FAILED", records_processed=0,
                    error_message="java.lang.OutOfMemoryError: Java heap space at com.app.notification.service.BulkEmailSender.loadTemplates",
                    root_cause="Out of Memory (OOM)"),
    ]

    error_logs = [
        LogEntry(timestamp=(now - timedelta(hours=2, minutes=15)).isoformat(), service_name="order-service",
                 severity="ERROR", category="API_500",
                 message="java.lang.NullPointerException: Cannot invoke method getId() on null reference at com.app.order.service.OrderService.processOrder(OrderService.java:142)",
                 root_cause="NullPointerException / Unhandled Null", http_status=500, latency_ms=45.2, trace_id="abc123def456"),
        LogEntry(timestamp=(now - timedelta(hours=3, minutes=42)).isoformat(), service_name="payment-service",
                 severity="ERROR", category="API_502",
                 message="upstream connect error or disconnect/reset before headers. reset reason: connection failure, transport failure reason: delayed connect error: 111",
                 root_cause="Downstream Service Unavailable", http_status=502, latency_ms=30000.0, trace_id="xyz789ghi012"),
        LogEntry(timestamp=(now - timedelta(hours=1, minutes=5)).isoformat(), service_name="notification-service",
                 severity="CRITICAL", category="API_500",
                 message="org.springframework.jdbc.CannotGetJdbcConnectionException: Failed to obtain JDBC Connection; nested exception is com.zaxxer.hikari.pool.HikariPool$PoolInitializationException: Failed to initialize pool: FATAL: too many connections for role 'app_user'",
                 root_cause="Connection Pool Exhausted", http_status=500, latency_ms=5023.0, trace_id="conn_pool_001"),
        LogEntry(timestamp=(now - timedelta(hours=5, minutes=20)).isoformat(), service_name="order-service",
                 severity="ERROR", category="API_500",
                 message="org.hibernate.exception.JDBCConnectionException: Unable to acquire JDBC Connection; SQL [n/a]; nested exception: connection timed out after 30000ms",
                 root_cause="Database Connection Timeout", http_status=500, latency_ms=30120.5, trace_id="db_timeout_001"),
        LogEntry(timestamp=(now - timedelta(hours=4)).isoformat(), service_name="auth-service",
                 severity="ERROR", category="API_500",
                 message="io.jsonwebtoken.ExpiredJwtException: JWT expired at 2026-03-13T23:45:00Z. Current time: 2026-03-14T00:15:00Z. Token expired 30 minutes ago.",
                 root_cause="Authentication / Authorization Failure", http_status=500, latency_ms=12.5, trace_id="auth_exp_001"),
        LogEntry(timestamp=(now - timedelta(hours=6, minutes=10)).isoformat(), service_name="payment-service",
                 severity="ERROR", category="API_502",
                 message="com.netflix.hystrix.exception.HystrixRuntimeException: PaymentGateway_processPayment timed out and fallback failed.",
                 root_cause="Network Timeout", http_status=502, latency_ms=61000.0, trace_id="hystrix_001"),
    ]

    slow_logs = [
        LogEntry(timestamp=(now - timedelta(hours=1, minutes=30)).isoformat(), service_name="order-service",
                 severity="WARNING", category="SLOW_REQUEST",
                 message="GET /api/orders?page=1&size=100 — Slow query detected: SELECT * FROM orders o JOIN order_items oi ON o.id = oi.order_id WHERE o.status = 'PENDING' — Full table scan on 2.4M rows",
                 root_cause="Slow Database Query", http_status=200, latency_ms=8540.0, trace_id="slow_001"),
        LogEntry(timestamp=(now - timedelta(hours=2, minutes=50)).isoformat(), service_name="order-service",
                 severity="WARNING", category="SLOW_REQUEST",
                 message="POST /api/orders/bulk-create — N+1 query problem detected: 1 query for orders + 500 individual queries for order_items. Total DB time: 4.2s",
                 root_cause="Slow Database Query", http_status=201, latency_ms=5200.0, trace_id="slow_002"),
        LogEntry(timestamp=(now - timedelta(hours=3, minutes=15)).isoformat(), service_name="payment-service",
                 severity="WARNING", category="SLOW_REQUEST",
                 message="POST /api/payments/process — GC pause detected: 2.8s full GC (old gen: 95% used). Heap: 3.2GB/4GB.",
                 root_cause="JVM Garbage Collection Pause", http_status=200, latency_ms=4800.0, trace_id="slow_003"),
        LogEntry(timestamp=(now - timedelta(hours=4, minutes=45)).isoformat(), service_name="notification-service",
                 severity="WARNING", category="SLOW_REQUEST",
                 message="POST /api/notifications/send-bulk — Synchronous call chain: notification-service → auth-service (320ms) → order-service (1200ms) → payment-service (timeout). Total chain latency: 12.4s",
                 root_cause="Network Timeout", http_status=200, latency_ms=12400.0, trace_id="slow_004"),
    ]

    hourly_trend = []
    for i in range(24):
        h = (now - timedelta(hours=23 - i))
        hour_of_day = h.hour
        if 0 <= hour_of_day <= 2:
            base_errors = random.randint(25, 65)
        elif 8 <= hour_of_day <= 10:
            base_errors = random.randint(10, 25)
        else:
            base_errors = random.randint(2, 8)
        hourly_trend.append({"hour": h.strftime("%Y-%m-%d %H:00"), "error_count": base_errors})

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
        total_log_entries=25590, total_errors=945, total_warnings=125,
        batch_failures=3, api_500_errors=540, api_502_errors=290, slow_requests=len(slow_logs),
        services=services, batch_statuses=batch_statuses,
        error_logs=error_logs, slow_request_logs=slow_logs,
        hourly_error_trend=hourly_trend, root_cause_distribution=root_cause_dist,
    )


# ── Run ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
