import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ApiService } from '../../services/api.service';

@Component({
    selector: 'app-connection',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './connection.component.html',
    styleUrl: './connection.component.css'
})
export class ConnectionComponent {
    selectedFile: File | null = null;
    isUploading: boolean = false;
    errorMessage: string = '';
    isDragOver: boolean = false;

    constructor(private apiService: ApiService, private router: Router) { }

    onFileSelected(event: Event): void {
        const input = event.target as HTMLInputElement;
        if (input.files && input.files.length > 0) {
            this.selectedFile = input.files[0];
            this.errorMessage = '';
        }
    }

    onDragOver(event: DragEvent): void {
        event.preventDefault();
        this.isDragOver = true;
    }

    onDragLeave(event: DragEvent): void {
        event.preventDefault();
        this.isDragOver = false;
    }

    onDrop(event: DragEvent): void {
        event.preventDefault();
        this.isDragOver = false;
        if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
            const file = event.dataTransfer.files[0];
            if (file.name.endsWith('.json') || file.name.endsWith('.csv')) {
                this.selectedFile = file;
                this.errorMessage = '';
            } else {
                this.errorMessage = 'Please upload a .json or .csv file exported from GCP Console.';
            }
        }
    }

    upload(): void {
        if (!this.selectedFile) {
            this.errorMessage = 'Please select a log file to upload.';
            return;
        }

        this.isUploading = true;
        this.errorMessage = '';

        this.apiService.uploadLogFile(this.selectedFile).subscribe({
            next: (data) => {
                this.isUploading = false;
                // Store result and navigate to dashboard
                sessionStorage.setItem('dashboardData', JSON.stringify(data));
                sessionStorage.setItem('dashboardMode', 'uploaded');
                this.router.navigate(['/dashboard']);
            },
            error: (err) => {
                this.errorMessage = err.error?.detail || 'Failed to parse the log file. Please check the format.';
                this.isUploading = false;
            }
        });
    }

    loadDemo(): void {
        this.isUploading = true;
        this.errorMessage = '';

        this.apiService.getDemoDashboard().subscribe({
            next: (data) => {
                this.isUploading = false;
                sessionStorage.setItem('dashboardData', JSON.stringify(data));
                sessionStorage.setItem('dashboardMode', 'demo');
                this.router.navigate(['/dashboard']);
            },
            error: (err) => {
                this.errorMessage = 'Failed to load demo data. Is the backend running on port 8000?';
                this.isUploading = false;
            }
        });
    }

    formatFileSize(bytes: number): string {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    }
}
