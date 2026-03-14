# GCP Log Analyzer Dashboard

A full-stack application to monitor **batch failures**, **API 500/502 errors**, and **slow requests** from Google Cloud Logging — all in a single dashboard with **automated root cause analysis**.

![Tech Stack](https://img.shields.io/badge/Backend-FastAPI%20(Python)-009688?style=flat-square&logo=fastapi)
![Tech Stack](https://img.shields.io/badge/Frontend-Angular%2020-DD0031?style=flat-square&logo=angular)
![Tech Stack](https://img.shields.io/badge/Cloud-Google%20Cloud%20Logging-4285F4?style=flat-square&logo=googlecloud)

## Features

- 🔑 **GCP Connection** — Connect using Project ID + Service Account JSON or Application Default Credentials
- 📊 **Service Health Overview** — Real-time health status of all microservices (HEALTHY / DEGRADED / CRITICAL)
- 🔴 **Batch Job Monitoring** — Track midnight batch job success/failure with error details
- 🟠 **API Error Tracking** — HTTP 500 & 502 errors grouped by microservice with timestamps
- 🐌 **Slow Request Detection** — APIs taking > 2 seconds with latency breakdown
- 🧠 **Root Cause Analysis** — Auto-categorizes WHY failures happened (DB timeout, OOM, connection pool, etc.)
- 📈 **Error Trend Charts** — Hourly error distribution and root cause breakdown
- 🎮 **Demo Mode** — View realistic mock data without a GCP connection

## Root Cause Categories

The analyzer automatically detects these root causes from log messages:

| Root Cause | Pattern Detected |
|---|---|
| Database Connection Timeout | JDBC timeout, SQL timeout |
| Connection Pool Exhausted | HikariCP pool errors |
| Out of Memory (OOM) | `OutOfMemoryError`, heap space |
| NullPointerException | Unhandled null references |
| Data Integrity Violation | Constraint violations, duplicate keys |
| Downstream Service Unavailable | Connection refused, 503 errors |
| Network Timeout | Socket timeout, deadline exceeded |
| JVM Garbage Collection Pause | Full GC, stop-the-world |
| Slow Database Query | Long-running queries |
| Rate Limited | 429 errors, quota exceeded |
| Authentication Failure | 401/403, token expired |

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.13 + FastAPI |
| **Frontend** | Angular 20 + TypeScript |
| **GCP SDK** | `google-cloud-logging` (Python) |
| **Styling** | Vanilla CSS with CSS Custom Properties (Dark Theme) |

## Project Structure

```
gcp-log-analyzer/
├── backend/
│   ├── main.py                 # FastAPI server & API endpoints
│   ├── gcp_log_service.py      # GCP log fetching & root cause analysis
│   ├── models.py               # Pydantic data models
│   └── requirements.txt        # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── components/
│   │   │   │   ├── connection/     # GCP connection page
│   │   │   │   ├── dashboard/      # Main dashboard
│   │   │   │   ├── batch-status/   # Batch job monitoring
│   │   │   │   ├── error-logs/     # API error logs
│   │   │   │   ├── service-health/ # Microservice health cards
│   │   │   │   └── slow-requests/  # Slow request analysis
│   │   │   ├── models/            # TypeScript interfaces
│   │   │   └── services/          # Angular HTTP service
│   │   ├── styles.css             # Global dark theme
│   │   └── index.html
│   ├── angular.json
│   └── package.json
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- Angular CLI (`npm install -g @angular/cli`)
- GCP Service Account with **Logging Viewer** role (for production use)

### 1. Backend Setup

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.  
Swagger docs at `http://localhost:8000/docs`.

### 2. Frontend Setup

```bash
cd frontend
npm install
ng serve --port 4200
```

The dashboard will be available at `http://localhost:4200`.

### 3. Usage

1. Open `http://localhost:4200`
2. Enter your **GCP Project ID**
3. Upload your **Service Account JSON** (optional — uses ADC if omitted)
4. Click **Connect to GCP** or **View Demo** for mock data
5. Navigate to the dashboard to view batch failures, API errors, and slow requests

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/connect` | Test GCP connection |
| `GET` | `/api/connection-status` | Check active connection |
| `POST` | `/api/disconnect` | Clear session |
| `GET` | `/api/dashboard?hours_back=24` | Fetch real GCP log data |
| `GET` | `/api/dashboard/demo` | Get realistic mock data |

## License

MIT
