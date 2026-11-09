# J.A.R.V.I.S. Test Log Files for Manual Upload

This directory contains pre-configured test log files designed to test J.A.R.V.I.S.'s **multi-source ingestion**, **schema normalization**, and **cross-service incident correlation** engines.

---

## 📁 Available Test Log Files

| File | Format | Scenario | Key Trigger & Correlated Services |
| :--- | :--- | :--- | :--- |
| **`01_challenge_db_saturation_cascade.log`** | Plaintext Microservices Log | **Challenge Scenario** · Shared DB Saturation | `database-service` pool exhaustion (100/100) causing cascade across `payment-service`, `order-service`, `user-service`, and `api-gateway` (Shared `trace_id=tr-pay-8821`). |
| **`02_payment_oom_heap_leak.log`** | Plaintext Application Log | JVM Heap Leak / OutOfMemory Crash | `payment-service` heap memory surge to 93.1%, `OutOfMemoryError` crash, container health probe failure (`trace_id=tr-mem-9912`). |
| **`03_api_gateway_500_storm.log`** | Plaintext Access & Ingress Log | Gateway Error Spike & Circuit Breaker | `api-gateway` HTTP 500 error burst, `user-service` timeout, and circuit breaker transition to `OPEN` (`trace_id=tr-gw-4401`). |
| **`04_structured_cloud_stream.jsonl`** | JSON Lines (JSONL) | Cloud Native Structured Telemetry | Modern streaming JSON lines normalized into standard `Event` records with trace mapping (`trace_id=tr-json-7701`). |
| **`05_multi_service_batch_dump.json`** | JSON Array Batch | Multi-Service Batch Ingestion Dump | JSON telemetry dump covering metric breaches, timeouts, and checkout failures (`trace_id=tr-batch-1001`). |

---

## 🚀 How to Test Manually

### Option A: Upload via the J.A.R.V.I.S. Console UI (Recommended)

1. Open the **Operations Console** at [http://localhost:3000/dashboard](http://localhost:3000/dashboard).
2. Scroll to the **Fault Injection & Chaos Testing** panel on the left sidebar.
3. Locate the **Upload Log File (.log, .txt, .json)** section.
4. Click **Choose File** and select any file from this `test_logs/` folder (e.g., `01_challenge_db_saturation_cascade.log`).
5. Observe:
   - J.A.R.V.I.S. automatically uploads the file to `POST /api/v1/logs/upload`.
   - The notification pill confirms: `Uploaded 01_challenge_db_saturation_cascade.log: Ingested 9 events (9 correlated).`
   - The **Incident Investigation Drawer** and **Real-Time Event Stream** reflect the correlated trace and topological cluster!

---

### Option B: Upload via cURL / Command Line

```bash
# Upload Challenge Scenario Log
curl -X POST "http://localhost:8000/api/v1/logs/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@test_logs/01_challenge_db_saturation_cascade.log"

# Upload JSON Lines Structured Log
curl -X POST "http://localhost:8000/api/v1/logs/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@test_logs/04_structured_cloud_stream.jsonl"
```

### Option C: Upload via PowerShell

```powershell
$filePath = "test_logs/01_challenge_db_saturation_cascade.log"
$form = @{
    file = Get-Item -Path $filePath
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/logs/upload" -Method Post -Form $form
```

---

## 🔍 Expected Outcomes

1. **Schema Normalization**: Every line is assigned an `id` (`EVT-LOG-...`), ISO-8601 UTC timestamp, normalized severity (`critical`, `error`, `warning`, `info`), and inferred service.
2. **Correlation Matching**: Lines sharing `trace_id` are automatically clustered into a single ongoing or newly created Master Incident.
3. **Topological Mapping**: Unrelated service errors that share the `database-service` dependency are linked topologically with 0 false merges.

