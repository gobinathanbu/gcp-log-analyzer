import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogEntry } from '../../models/dashboard.model';

@Component({
    selector: 'app-slow-requests',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './slow-requests.component.html',
    styleUrl: './slow-requests.component.css'
})
export class SlowRequestsComponent {
    @Input() slowLogs: LogEntry[] = [];
    expandedIndex: number | null = null;

    toggleExpand(index: number): void {
        this.expandedIndex = this.expandedIndex === index ? null : index;
    }

    formatTime(isoStr: string): string {
        try {
            return new Date(isoStr).toLocaleString();
        } catch {
            return isoStr;
        }
    }

    formatLatency(ms?: number): string {
        if (!ms) return '—';
        if (ms >= 1000) {
            return (ms / 1000).toFixed(1) + 's';
        }
        return ms.toFixed(0) + 'ms';
    }

    getLatencySeverity(ms?: number): string {
        if (!ms) return '';
        if (ms > 10000) return 'critical';
        if (ms > 5000) return 'high';
        if (ms > 2000) return 'medium';
        return 'low';
    }

    getLatencyBarWidth(ms?: number): number {
        if (!ms) return 0;
        // Normalize: 30s = 100%
        return Math.min((ms / 30000) * 100, 100);
    }
}
