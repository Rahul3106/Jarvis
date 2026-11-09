# J.A.R.V.I.S.
### Justified Analysis, Reasoning & Visualization of Incident Systems

> **AI Distributed Systems Incident Correlation, Root Cause Detection & Autonomous Resolution Platform**

---

## 📌 Problem Statement

Modern digital platforms use multiple connected services, applications, and servers. These systems continuously generate logs, alerts, and notifications. However, these alerts are usually handled separately, making it difficult to understand whether different problems are connected. For example, slow server responses, login failures, and failed payments may look like separate issues, even though they could all be caused by one server failure. 

Most monitoring systems generate alerts but do not explain how they are connected or what caused them. This leads to confusion, delayed problem-solving, and wasted time.

The challenge is to build **J.A.R.V.I.S.**, an intelligent system that:
1. Collects events from different sources.
2. Finds connections between them using timestamps, topological dependencies, and shared traces.
3. Tracks how incidents develop across services in a chronological timeline.
4. Identifies their most likely root cause through multi-agent hypothesis falsification.
5. Explains the business impact (blast radius, affected users, revenue at risk).
6. Suggests and autonomously executes vetted remediation runbooks with deterministic verification.

---

## 🎯 Suggested Challenge Scenario

### Digital Payment Platform Cascade Outage
A digital payment platform starts experiencing:
- **Login Failures**: Authentication timeouts in `user-service`.
- **Slow API Responses**: Downstream latency and HTTP 504 timeouts on `api-gateway`.
- **Failed Transactions**: Transaction drops and checkout failures across `order-service` and `payment-service`.

Traditional APM tools treat these as three isolated alerts and page three different on-call teams. 

**J.A.R.V.I.S. unifies them:**
1. Ingests the 3 simultaneous alert streams.
2. Traces topological adjacency to the shared `database-service` bottleneck (`trace_id=tr-pay-8821`).
3. Collapses the alerts into **1 Master Incident** (`INC-20261109-SAT`).
4. Identifies the true root cause: **PostgreSQL Connection Pool Saturation (100/100 active leases)**.
5. Falsifies competing theories (e.g. network partition, release bug).
6. Quantifies the business impact: **175 failed transactions (\$8,748.25 at risk)** and **95 failed logins**.
7. Autonomously executes `POOL_EXPANSION` and `CLEAR_STUCK_JOBS`, verifies health with an 18ms probe, and compiles a comprehensive 9-section Markdown post-mortem report in under 15 seconds.

---

## ⚡ Key Features & Expected Functionalities

| # | Feature | Implementation Details in J.A.R.V.I.S. |
| :-: | :--- | :--- |
| **1** | **Multiple Data Sources** | Ingests events from REST APIs (`POST /api/v1/events`), uploaded log files (`.log`, `.txt`, `.json`, `.jsonl` via `POST /api/v1/logs/upload`), Prometheus AlertManager webhooks, and simulated chaos streams. |
| **2** | **Root Cause Detection** | Local LLM (`qwen2.5:3b`) multi-agent diagnostic engine with deterministic rule fallbacks. Formulates, tests, and explicitly logs rejected alternative hypotheses. |
| **3** | **Impact Analysis** | Quantifies concrete customer & business blast radius: affected downstream microservices, user dropouts, and financial revenue at risk. |
| **4** | **Event Correlation** | Evaluates events over a sliding 120-second window using topological graph distance, shared infrastructure dependencies, distributed trace IDs, and causal error signatures (0 false merges). |
| **5** | **Incident Timeline** | Generates an interactive, chronological timeline showing how an incident ignited, propagated through dependencies, and was resolved. |
| **6** | **Smart Recommendations** | Recommends vetted operational runbooks (`CLEAR_STUCK_JOBS`, `CONTAINER_RESTART`, `POOL_EXPANSION`, `ROLLBACK`), executes them safely, and validates convergence with synthetic probes. |
| **7** | **Interactive Dashboard** | Dark-mode developer cockpit (Resend & Bolt.new aesthetic) featuring interactive service topology graphs, chronological timeline views, log upload workbench, live streaming telemetry, and downloadable post-mortems. |

---

## 🏆 Expected Outcome & Capabilities

- **Unified Ingestion**: Normalizes unstructured log dumps, webhook payloads, and metrics breaches into an ISO-8601 UTC schema.
- **Topological & Trace Correlation**: Collapses cascades into a single Master Incident rather than separate disjointed tickets.
- **Accurate Root Cause Analysis**: Identifies root cause with > 90% confidence and documents why alternative causes were ruled out.
- **Automated Incident Report**: Compiles a publication-ready 9-section Markdown Incident Post-Mortem Report detailing MTTR, trigger sequence, and preventive action items.

---

## 🖥️ System Architecture

```
[ Multi-Source Ingestion ]
    ├── Uploaded Logs (.log, .txt, .json, .jsonl)
    ├── REST Events API (POST /api/v1/events)
    ├── AlertManager Webhooks
    └── Chaos Fault Simulator
                │
                ▼
[ Event Normalizer & Schema Harmonizer ] (ISO-8601 UTC, Trace Extraction)
                │
                ▼
[ Graph-Based Event Correlation Engine ] (120s Window, Topology Mapping, 0 False Merges)
                │
                ▼
       [ Master Incident ] ── INC-20261109-SAT
                │
                ├─► Multi-Agent RCA (Qwen 2.5:3B / Heuristic Rule Fallback)
                ├─► Quantified Business Blast Radius ($8,748.25 at risk, 95 dropouts)
                ├─► Autonomous Remediation (POOL_EXPANSION, Restart, Rollback)
                └─► 9-Section Markdown Post-Mortem Generator (1-Click Export)
                │
                ▼
[ Interactive SRE Cockpit Dashboard ] (Next.js, Live Topology, Timeline, Terminal)
```

---

## 🛠️ Microservices Simulation Stack

J.A.R.V.I.S. runs against a realistic microservice architecture:

| Service | Port | Role & Dependencies |
| :--- | :--- | :--- |
| **`api-gateway`** | `8001` | Edge ingress, auth routing, circuit breakers (Depends on `user-service`, `order-service`) |
| **`user-service`** | `8002` | Session management, authentication, user profiles (Depends on `database-service`) |
| **`order-service`** | `8003` | Cart operations, checkout management (Depends on `payment-service`, `database-service`) |
| **`payment-service`** | `8004` | Transaction settlement, payment gateway integration (Depends on `database-service`, `notification-service`) |
| **`notification-service`** | `8005` | Async customer notifications and webhooks |
| **`database-service`** | `5432` / Mock | Shared PostgreSQL connection pool bottleneck |

---

## 🚀 Quickstart & Setup

### Prerequisites
1. **Ollama** installed on your host:
   ```bash
   ollama pull qwen2.5:3b
   ```
2. **Node.js** (v18+) and **Python** (3.10+) installed.

---

### Option A: Local Host-Native Execution (Recommended)

1. Run the local startup script:
   - **PowerShell**:
     ```powershell
     ./start_local.ps1
     ```
   - **Windows Command Prompt**:
     ```cmd
     start_local.bat
     ```
2. The script boots:
   - 5 Mock microservices (`ports 8001–8005`)
   - FastAPI Backend with Correlation Engine on `http://localhost:8000`
   - Next.js SRE Console Dashboard on `http://localhost:3000`
3. Open **`http://localhost:3000`** in your browser.

---

### Option B: Docker Compose Execution

```bash
docker compose up --build
```
- Next.js Control Deck: `http://localhost:3000`
- FastAPI SRE API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- AlertManager: `http://localhost:9093`

---

## 🧪 Testing Multi-Source Log Ingestion

Pre-configured sample logs are available in [`test_logs/`](./test_logs):

| Test Log File | Failure Simulated |
| :--- | :--- |
| **`01_challenge_db_saturation_cascade.log`** | Shared PostgreSQL connection pool saturation causing cascade across 4 services (`trace_id=tr-pay-8821`). |
| **`02_payment_oom_heap_leak.log`** | `payment-service` heap memory exhaustion and container crash (`trace_id=tr-mem-9912`). |
| **`03_api_gateway_500_storm.log`** | Gateway HTTP 500 error spike and circuit breaker trip (`trace_id=tr-gw-4401`). |
| **`04_structured_cloud_stream.jsonl`** | Streaming JSON Lines format with structured cloud telemetry metadata. |
| **`05_multi_service_batch_dump.json`** | Multi-service JSON array batch telemetry dump. |

### Manual Upload via UI:
1. Open the **Console Deck** at `http://localhost:3000/dashboard`.
2. Click **Inject Multi-Source Event** or navigate to the Ingestion modal.
3. Choose any file from `test_logs/` and click **Run Ingestion**.
4. The dashboard automatically switches to the synthesized Master Incident and displays all correlated events.

### Upload via cURL:
```bash
curl -X POST "http://localhost:8000/api/v1/logs/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@test_logs/01_challenge_db_saturation_cascade.log"
```

---

## 📡 API Reference

- **`POST /api/v1/events`**: Ingest a single telemetry event.
- **`POST /api/v1/events/batch`**: Ingest multiple events in bulk.
- **`POST /api/v1/logs/upload`**: Upload and parse `.log`, `.txt`, `.json`, or `.jsonl` files.
- **`POST /api/v1/alerts/webhook`**: Prometheus AlertManager receiver.
- **`POST /api/v1/simulation/payment-platform-outage`**: 1-Click trigger for the digital payment challenge scenario.
- **`GET /api/v1/incidents`**: Retrieve all active and resolved master incidents.
- **`GET /api/v1/incidents/{id}/correlated-events`**: Retrieve all correlated events grouped under an incident.
- **`GET /api/v1/incidents/{id}/timeline`**: Retrieve chronological incident development timeline.
- **`GET /api/v1/benchmarks`**: Retrieve real-time MTTR and incident resolution metrics.
- **`GET /api/v1/incidents/{id}/post-mortem/download`**: Download the publication-ready 9-section Markdown incident report.

---

## 📜 License
MIT License. Built for the J.A.R.V.I.S. AI Distributed Systems Challenge.
