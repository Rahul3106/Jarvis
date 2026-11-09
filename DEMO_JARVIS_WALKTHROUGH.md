# J.A.R.V.I.S. AI Distributed Systems Challenge Demonstration Walkthrough

This document provides a complete guide for judges and evaluators to run, inspect, and verify **J.A.R.V.I.S. AI**, an intelligent SRE orchestration platform fulfilling the **J.A.R.V.I.S. AI Distributed Systems Problem Statement**.

---

## 1. Challenge Scenario Overview

In modern distributed microservice platforms, a single underlying infrastructure failure causes widespread cascading symptoms across independent applications:
- **Login Failures** in `user-service`
- **HTTP 504 Gateway Timeouts** in `order-service`
- **Transaction Rollbacks** in `payment-service`

Traditional monitoring tools treat these as three isolated incidents, resulting in alert fatigue and delayed mean time to resolution (MTTR).

**J.A.R.V.I.S.** ingests symptoms from multiple disparate sources, correlates them using topology adjacency, temporal proximity, and distributed trace IDs, identifies their common root cause (`database-service` connection pool saturation), quantifies business impact, and executes safe remediation under 4-tier governance.

---

## 2. Key Capabilities Implemented

| Feature | Implementation in J.A.R.V.I.S. | Verification |
| :--- | :--- | :--- |
| **1. Multiple Data Sources** | REST API (`/api/v1/events`), Log file upload (`/api/v1/logs/upload`), Prometheus/AlertManager webhooks, and simulated telemetry. | `test_phase1_ingestion.py` |
| **2. Event Correlation** | Dedicated Multi-Factor Correlation Engine combining temporal decay, call-graph distance, shared infrastructure dependencies, trace IDs, and error signatures. | `test_phase2_correlation.py` |
| **3. Root Cause Detection** | 6-subagent LangGraph SRE team identifying shared root causes with alternative candidate evaluation and likelihood scoring. | `test_phase4_rca_impact.py` |
| **4. Impact Analysis** | Real-time tracking of failed transactions, failed customer logins, estimated users affected, and revenue at risk. | `test_phase4_rca_impact.py` |
| **5. Incident Timeline** | Unified chronological timeline weaving initial symptom arrivals $\rightarrow$ correlation $\rightarrow$ investigation $\rightarrow$ governance $\rightarrow$ remediation $\rightarrow$ recovery. | `test_phase5_timeline.py` |
| **6. Smart Recommendations** | Structured runbooks with explicit rationale, compliance risk rating, and rollback safeguards. | `test_phase4_rca_impact.py` |
| **7. Interactive Dashboard** | Next.js 16 UI with SVG Causal Graph, Impact Metrics, Chronological Timeline, Correlated Cluster, and Post-Mortem Viewer. | Next.js 16 Build Verified |
| **8. Shared-Dependency Scenario**| 1-click Payment Platform Outage simulation proving 3 disparate alerts converge on 1 master incident. | `test_phase3_scenario.py` |

---

## 3. Running the Demo via CLI

### Step 1: Start Backend API
```powershell
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Step 2: Run the Automated Challenge Scenario Script
In a separate terminal window:
```powershell
.\demo_jarvis_scenario.ps1
```

The script will automatically:
1. Ingest an API authentication failure event on `user-service`.
2. Upload a raw log file capturing HTTP 504 timeouts on `order-service`.
3. Ingest an AlertManager critical alert on `payment-service`.
4. Trigger the shared database saturation scenario.
5. Prove that all 3 events are correlated into **one master incident card**.
6. Ingest an unrelated memory leak on `notification-service` to prove **false-correlation isolation** (remains in a separate incident).
7. Generate and download a comprehensive 9-section Markdown Post-Mortem report (`post-mortem-<ID>.md`).

---

## 4. Running the Demo via Frontend Dashboard

### Step 1: Start Frontend
```powershell
cd frontend
npm run dev
```

### Step 2: Open Dashboard
Navigate to: [http://localhost:3000/dashboard](http://localhost:3000/dashboard)

### Step 3: Interactive Exploration
1. **Launch Scenario**: Click **Data Ingestion** at the top right, then click **Launch Digital Payment Outage Scenario**.
2. **Observe Master Incident**: Notice a single master incident card appears in the feed with the badge `3 Correlated Events`.
3. **Inspect Tabs**:
   - **Overview & Impact**: View measured counters for Failed Transactions, Failed Logins, and Estimated Revenue at Risk.
   - **Causal Graph**: Observe the SVG dependency topology with `database-service` highlighted in red as the common root cause, and downstream services highlighted in orange.
   - **Timeline**: Review the unified chronological progression from symptom arrivals to resolution.
   - **Events Cluster**: Inspect the multi-source raw events bundled under this master incident.
   - **Post-Mortem**: Review the complete audit report and click **Export Markdown** to download it.

---

## 5. Verification Test Suite

To run all automated verification tests across all 8 phases:
```powershell
python -m pytest backend/tests/test_phase1_ingestion.py `
                 backend/tests/test_phase2_correlation.py `
                 backend/tests/test_phase3_scenario.py `
                 backend/tests/test_phase4_rca_impact.py `
                 backend/tests/test_phase5_timeline.py `
                 backend/tests/test_phase7_postmortem.py `
                 backend/tests/test_phase8_challenge_e2e.py
```
All tests run with 100% pass rate, validating schema compatibility, correlation scoring, multi-agent RCA, business impact quantification, and false-correlation defenses.

