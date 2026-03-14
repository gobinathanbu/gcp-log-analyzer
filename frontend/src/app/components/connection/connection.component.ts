import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';
import { ConnectionTestResult } from '../../models/dashboard.model';

@Component({
    selector: 'app-connection',
    standalone: true,
    imports: [CommonModule, FormsModule],
    templateUrl: './connection.component.html',
    styleUrl: './connection.component.css'
})
export class ConnectionComponent {
    projectId: string = '';
    serviceAccountFile: File | null = null;
    isConnecting: boolean = false;
    connectionResult: ConnectionTestResult | null = null;
    errorMessage: string = '';

    constructor(private apiService: ApiService) { }

    onFileSelected(event: Event): void {
        const input = event.target as HTMLInputElement;
        if (input.files && input.files.length > 0) {
            this.serviceAccountFile = input.files[0];
        }
    }

    connect(): void {
        if (!this.projectId.trim()) {
            this.errorMessage = 'Please enter a GCP Project ID.';
            return;
        }

        this.isConnecting = true;
        this.errorMessage = '';
        this.connectionResult = null;

        this.apiService.testConnection(this.projectId, this.serviceAccountFile || undefined)
            .subscribe({
                next: (result) => {
                    this.connectionResult = result;
                    this.isConnecting = false;
                },
                error: (err) => {
                    this.errorMessage = err.error?.detail || 'Connection failed. Please check your credentials.';
                    this.isConnecting = false;
                }
            });
    }

    loadDemo(): void {
        this.connectionResult = {
            success: true,
            project_id: 'demo-project-gcp',
            message: 'Demo mode activated. Showing realistic mock data.',
            available_services: ['auth-service', 'order-service', 'payment-service', 'inventory-service', 'notification-service']
        };
    }
}
