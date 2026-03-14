import { Routes } from '@angular/router';
import { ConnectionComponent } from './components/connection/connection.component';
import { DashboardComponent } from './components/dashboard/dashboard.component';

export const routes: Routes = [
    { path: '', component: ConnectionComponent },
    { path: 'dashboard', component: DashboardComponent },
    { path: '**', redirectTo: '' },
];
