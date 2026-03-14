import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogEntry } from '../../models/dashboard.model';

@Component({
    selector: 'app-error-logs',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './error-logs.component.html',
    styleUrl: './error-logs.component.css'
})
export class ErrorLogsComponent {
    @Input() errorLogs: LogEntry[] = [];
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

    getSeverityClass(severity: string): string {
        return severity.toLowerCase();
    }

    getCategoryLabel(category: string): string {
        switch (category) {
            case 'API_500': return 'HTTP 500';
            case 'API_502': return 'HTTP 502';
            case 'API_504': return 'HTTP 504';
            case 'BATCH_FAILURE': return 'Batch Failure';
            default: return category;
        }
    }
}
