import { Component, OnInit, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { DashboardSummary } from '../../models/dashboard.model';
import { ServiceHealthComponent } from '../service-health/service-health.component';
import { BatchStatusComponent } from '../batch-status/batch-status.component';
import { ErrorLogsComponent } from '../error-logs/error-logs.component';
import { SlowRequestsComponent } from '../slow-requests/slow-requests.component';

@Component({
    selector: 'app-dashboard',
    standalone: true,
    imports: [CommonModule, ServiceHealthComponent, BatchStatusComponent, ErrorLogsComponent, SlowRequestsComponent],
    templateUrl: './dashboard.component.html',
    styleUrl: './dashboard.component.css'
})
export class DashboardComponent implements OnInit {
    dashboardData: DashboardSummary | null = null;
    isLoading: boolean = true;
    activeTab: string = 'overview';
    mode: string = '';

    @ViewChild('errorChart', { static: false }) errorChartRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('rootCauseChart', { static: false }) rootCauseChartRef!: ElementRef<HTMLCanvasElement>;

    constructor(private apiService: ApiService, private router: Router) { }

    ngOnInit(): void {
        const stored = sessionStorage.getItem('dashboardData');
        this.mode = sessionStorage.getItem('dashboardMode') || '';

        if (stored) {
            try {
                this.dashboardData = JSON.parse(stored);
                this.isLoading = false;
                setTimeout(() => this.renderCharts(), 100);
            } catch {
                this.router.navigate(['/']);
            }
        } else {
            this.router.navigate(['/']);
        }
    }

    setTab(tab: string): void {
        this.activeTab = tab;
        if (tab === 'overview') {
            setTimeout(() => this.renderCharts(), 100);
        }
    }

    goBack(): void {
        sessionStorage.removeItem('dashboardData');
        sessionStorage.removeItem('dashboardMode');
        this.router.navigate(['/']);
    }

    // ── Chart Rendering ──────────────────────────────────────

    renderCharts(): void {
        if (this.dashboardData) {
            this.drawErrorTrendChart();
            this.drawRootCauseChart();
        }
    }

    drawErrorTrendChart(): void {
        const canvas = this.errorChartRef?.nativeElement;
        if (!canvas || !this.dashboardData) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const data = this.dashboardData.hourly_error_trend || [];
        if (data.length === 0) return;

        const width = canvas.width = canvas.parentElement?.offsetWidth || 600;
        const height = canvas.height = 220;
        const padding = { top: 20, right: 20, bottom: 40, left: 50 };
        const chartW = width - padding.left - padding.right;
        const chartH = height - padding.top - padding.bottom;

        ctx.clearRect(0, 0, width, height);

        const maxVal = Math.max(...data.map((d: any) => d.error_count), 1);
        const barWidth = Math.max((chartW / data.length) - 3, 4);

        // Y-axis labels
        ctx.font = '10px Inter, sans-serif';
        ctx.fillStyle = '#64748b';
        ctx.textAlign = 'right';
        for (let i = 0; i <= 4; i++) {
            const val = Math.round((maxVal / 4) * i);
            const y = padding.top + chartH - (chartH * (val / maxVal));
            ctx.fillText(val.toString(), padding.left - 8, y + 3);
            ctx.strokeStyle = 'rgba(255,255,255,0.05)';
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(width - padding.right, y);
            ctx.stroke();
        }

        // Bars
        data.forEach((d: any, i: number) => {
            const barH = (d.error_count / maxVal) * chartH;
            const x = padding.left + (i * (chartW / data.length)) + 1.5;
            const y = padding.top + chartH - barH;

            const gradient = ctx.createLinearGradient(x, y, x, y + barH);
            gradient.addColorStop(0, '#6366f1');
            gradient.addColorStop(1, '#8b5cf6');
            ctx.fillStyle = gradient;
            ctx.beginPath();
            ctx.roundRect(x, y, barWidth, barH, [3, 3, 0, 0]);
            ctx.fill();

            // X-axis labels (every 4th)
            if (i % 4 === 0) {
                ctx.fillStyle = '#64748b';
                ctx.textAlign = 'center';
                ctx.font = '9px Inter, sans-serif';
                const hourLabel = (d.hour || '').split(' ')[1] || '';
                ctx.fillText(hourLabel, x + barWidth / 2, height - padding.bottom + 15);
            }
        });
    }

    drawRootCauseChart(): void {
        const canvas = this.rootCauseChartRef?.nativeElement;
        if (!canvas || !this.dashboardData) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const data = this.dashboardData.root_cause_distribution || [];
        if (data.length === 0) return;

        const width = canvas.width = canvas.parentElement?.offsetWidth || 600;
        const height = canvas.height = Math.max(data.length * 32 + 20, 150);
        const padding = { top: 10, right: 60, bottom: 10, left: 10 };
        const maxCount = Math.max(...data.map((d: any) => d.count), 1);

        ctx.clearRect(0, 0, width, height);

        const barH = 20;
        const gap = 12;
        const maxBarWidth = width - padding.left - padding.right - 160;

        const colors = ['#ef4444', '#f97316', '#f59e0b', '#eab308', '#84cc16', '#22c55e', '#06b6d4', '#3b82f6', '#6366f1', '#8b5cf6', '#a855f7'];

        data.forEach((d: any, i: number) => {
            const y = padding.top + i * (barH + gap);
            const w = (d.count / maxCount) * maxBarWidth;

            // Label
            ctx.font = '11px Inter, sans-serif';
            ctx.fillStyle = '#94a3b8';
            ctx.textAlign = 'left';
            const label = (d.root_cause || '').length > 28 ? (d.root_cause || '').substring(0, 28) + '…' : (d.root_cause || '');
            ctx.fillText(label, padding.left, y + 14);

            // Bar
            const barX = padding.left + 180;
            ctx.fillStyle = colors[i % colors.length];
            ctx.beginPath();
            ctx.roundRect(barX, y, w, barH, 4);
            ctx.fill();

            // Count
            ctx.font = '11px Inter, sans-serif';
            ctx.fillStyle = '#f1f5f9';
            ctx.textAlign = 'left';
            ctx.fillText(d.count.toString(), barX + w + 8, y + 14);
        });
    }
}
