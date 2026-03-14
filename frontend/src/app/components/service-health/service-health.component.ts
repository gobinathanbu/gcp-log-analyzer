import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ServiceHealth } from '../../models/dashboard.model';

@Component({
    selector: 'app-service-health',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './service-health.component.html',
    styleUrl: './service-health.component.css'
})
export class ServiceHealthComponent {
    @Input() services: ServiceHealth[] = [];

    getStatusClass(status: string): string {
        return status.toLowerCase();
    }

    getHealthWidth(service: ServiceHealth): number {
        return 100 - service.error_rate;
    }
}
