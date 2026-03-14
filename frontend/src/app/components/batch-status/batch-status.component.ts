import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BatchStatus } from '../../models/dashboard.model';

@Component({
    selector: 'app-batch-status',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './batch-status.component.html',
    styleUrl: './batch-status.component.css'
})
export class BatchStatusComponent {
    @Input() batchStatuses: BatchStatus[] = [];
    expandedIndex: number | null = null;

    toggleExpand(index: number): void {
        this.expandedIndex = this.expandedIndex === index ? null : index;
    }

    getStatusIcon(status: string): string {
        switch (status) {
            case 'SUCCESS': return '✅';
            case 'FAILED': return '❌';
            case 'RUNNING': return '🔄';
            default: return '⏳';
        }
    }

    formatTime(isoStr?: string): string {
        if (!isoStr) return '—';
        try {
            return new Date(isoStr).toLocaleString();
        } catch {
            return isoStr;
        }
    }

    getDuration(start?: string, end?: string): string {
        if (!start || !end) return '—';
        try {
            const diff = new Date(end).getTime() - new Date(start).getTime();
            const minutes = Math.floor(diff / 60000);
            const seconds = Math.floor((diff % 60000) / 1000);
            return `${minutes}m ${seconds}s`;
        } catch {
            return '—';
        }
    }
}
