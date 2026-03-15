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

    formatClueMessage(msg: string): string {
        // Splits the clue message from the python backend (Label \n→ Details)
        // into HTML for proper styling
        if (!msg) return '';
        const parts = msg.split('\n→ ');
        if (parts.length === 2) {
            return `<strong>${this.escapeHtml(parts[0])}</strong><br/><span class="clue-detail">→ ${this.escapeHtml(parts[1])}</span>`;
        }
        return this.escapeHtml(msg);
    }

    private escapeHtml(text: string): string {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }
}
