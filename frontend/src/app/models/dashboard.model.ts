// ── TypeScript interfaces matching the FastAPI backend models ──

export interface ConnectionTestResult {
    success: boolean;
    project_id: string;
    message: string;
    available_services: string[];
}

export interface ServiceHealth {
    service_name: string;
    total_requests: number;
    success_count: number;
    error_count: number;
    warning_count: number;
    avg_latency_ms: number;
    max_latency_ms: number;
    error_rate: number;
    status: 'HEALTHY' | 'DEGRADED' | 'CRITICAL';
}

export interface BatchStatus {
    job_name: string;
    scheduled_time?: string;
    start_time?: string;
    end_time?: string;
    status: 'SUCCESS' | 'FAILED' | 'RUNNING' | 'NOT_STARTED';
    records_processed?: number;
    error_message?: string;
    root_cause?: string;
}

export interface LogEntry {
    timestamp: string;
    service_name: string;
    severity: string;
    category: string;
    message: string;
    root_cause: string;
    http_status?: number;
    latency_ms?: number;
    trace_id?: string;
    log_name?: string;
    resource_type?: string;
}

export interface HourlyTrend {
    hour: string;
    error_count: number;
}

export interface RootCauseDistribution {
    root_cause: string;
    count: number;
}

export interface DashboardSummary {
    project_id: string;
    query_period_hours: number;
    fetched_at: string;
    total_log_entries: number;
    total_errors: number;
    total_warnings: number;
    batch_failures: number;
    api_500_errors: number;
    api_502_errors: number;
    slow_requests: number;
    services: ServiceHealth[];
    batch_statuses: BatchStatus[];
    error_logs: LogEntry[];
    slow_request_logs: LogEntry[];
    hourly_error_trend: HourlyTrend[];
    root_cause_distribution: RootCauseDistribution[];
}
