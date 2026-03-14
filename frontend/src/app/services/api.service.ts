import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ConnectionTestResult, DashboardSummary } from '../models/dashboard.model';

@Injectable({
    providedIn: 'root'
})
export class ApiService {
    private baseUrl = 'http://localhost:8000/api';

    constructor(private http: HttpClient) { }

    // ── Connection ──────────────────────────────────────────────

    testConnection(projectId: string, serviceAccountFile?: File): Observable<ConnectionTestResult> {
        const formData = new FormData();
        formData.append('project_id', projectId);
        if (serviceAccountFile) {
            formData.append('service_account_file', serviceAccountFile);
        }
        return this.http.post<ConnectionTestResult>(`${this.baseUrl}/connect`, formData);
    }

    getConnectionStatus(): Observable<{ connected: boolean; project_id: string | null }> {
        return this.http.get<{ connected: boolean; project_id: string | null }>(`${this.baseUrl}/connection-status`);
    }

    disconnect(): Observable<{ message: string }> {
        return this.http.post<{ message: string }>(`${this.baseUrl}/disconnect`, {});
    }

    // ── Dashboard Data ──────────────────────────────────────────

    getDashboard(hoursBack: number = 24, serviceNames?: string): Observable<DashboardSummary> {
        let params = new HttpParams().set('hours_back', hoursBack.toString());
        if (serviceNames) {
            params = params.set('service_names', serviceNames);
        }
        return this.http.get<DashboardSummary>(`${this.baseUrl}/dashboard`, { params });
    }

    getDemoDashboard(): Observable<DashboardSummary> {
        return this.http.get<DashboardSummary>(`${this.baseUrl}/dashboard/demo`);
    }

    healthCheck(): Observable<any> {
        return this.http.get(`${this.baseUrl}/health`);
    }
}
