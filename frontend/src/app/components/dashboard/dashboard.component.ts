import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';
import { DashboardSummary } from '../../models/dashboard.model';
import { ServiceHealthComponent } from '../service-health/service-health.component';
import { BatchStatusComponent } from '../batch-status/batch-status.component';
import { ErrorLogsComponent } from '../error-logs/error-logs.component';
import { SlowRequestsComponent } from '../slow-requests/slow-requests.component';

@Component({
    selector: 'app-dashboard',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        ServiceHealthComponent,
        BatchStatusComponent,
        ErrorLogsComponent,
        SlowRequestsComponent,
    ],
    templateUrl: './dashboard.component.html',
    styleUrl: './dashboard.component.css'
})
export class DashboardComponent implements OnInit {
    data: DashboardSummary | null = null;
    isLoading: boolean = false;
    errorMessage: string = '';
    hoursBack: number = 24;
    isDemo: boolean = false;
    activeTab: string = 'overview';
    lastRefreshed: string = '';

    constructor(private apiService: ApiService) { }

    ngOnInit(): void {
        this.loadDemoData();
    }

    loadDemoData(): void {
        this.isLoading = true;
        this.isDemo = true;
        this.errorMessage = '';

        this.apiService.getDemoDashboard().subscribe({
            next: (data) => {
                this.data = data;
                this.isLoading = false;
                this.lastRefreshed = new Date().toLocaleTimeString();
            },
            error: (err) => {
                this.errorMessage = 'Failed to load demo data. Is the backend running?';
                this.isLoading = false;
            }
        });
    }

    loadRealData(): void {
        this.isLoading = true;
        this.isDemo = false;
        this.errorMessage = '';

        this.apiService.getDashboard(this.hoursBack).subscribe({
            next: (data) => {
                this.data = data;
                this.isLoading = false;
                this.lastRefreshed = new Date().toLocaleTimeString();
            },
            error: (err) => {
                this.errorMessage = err.error?.detail || 'Failed to fetch dashboard data.';
                this.isLoading = false;
            }
        });
    }

    refresh(): void {
        if (this.isDemo) {
            this.loadDemoData();
        } else {
            this.loadRealData();
        }
    }

    setTab(tab: string): void {
        this.activeTab = tab;
    }

    getRootCauseChartWidth(count: number): number {
        if (!this.data || this.data.root_cause_distribution.length === 0) return 0;
        const max = Math.max(...this.data.root_cause_distribution.map(r => r.count));
        return (count / max) * 100;
    }

    getHourlyChartHeight(count: number): number {
        if (!this.data || this.data.hourly_error_trend.length === 0) return 0;
        const max = Math.max(...this.data.hourly_error_trend.map(h => h.error_count));
        return max > 0 ? (count / max) * 100 : 0;
    }

    getHourLabel(hour: string): string {
        const parts = hour.split(' ');
        if (parts.length > 1) {
            return parts[1].replace(':00', 'h');
        }
        return hour;
    }

    getBarColor(count: number): string {
        if (!this.data) return 'var(--primary)';
        const max = Math.max(...this.data.hourly_error_trend.map(h => h.error_count));
        const ratio = count / max;
        if (ratio > 0.7) return 'var(--danger)';
        if (ratio > 0.4) return 'var(--warning)';
        return 'var(--primary)';
    }

    getRootCauseColor(index: number): string {
        const colors = [
            'var(--danger)', 'var(--warning)', '#f97316', 'var(--primary)',
            '#8b5cf6', '#06b6d4', 'var(--success)', '#ec4899',
            '#14b8a6', '#f59e0b', '#6366f1',
        ];
        return colors[index % colors.length];
    }
}
