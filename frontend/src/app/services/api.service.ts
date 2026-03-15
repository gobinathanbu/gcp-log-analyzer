import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { DashboardSummary } from '../models/dashboard.model';

@Injectable({
    providedIn: 'root'
})
export class ApiService {
    private baseUrl = 'http://localhost:8000/api';

    constructor(private http: HttpClient) { }

    // ── File Upload (Main Feature) ──────────────────────────

    uploadLogFile(file: File): Observable<DashboardSummary> {
        const formData = new FormData();
        formData.append('file', file);
        return this.http.post<DashboardSummary>(`${this.baseUrl}/upload`, formData);
    }

    // ── Demo Data ───────────────────────────────────────────

    getDemoDashboard(): Observable<DashboardSummary> {
        return this.http.get<DashboardSummary>(`${this.baseUrl}/dashboard/demo`);
    }

    // ── Health Check ────────────────────────────────────────

    healthCheck(): Observable<any> {
        return this.http.get(`${this.baseUrl}/health`);
    }
}
