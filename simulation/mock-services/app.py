import os
import time
import uuid
import threading
import logging
from datetime import datetime
from fastapi import FastAPI, Response, HTTPException
from prometheus_client import start_http_server, Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mock-service")

SERVICE_NAME = os.getenv("SERVICE_NAME", "mock-service")
PORT = int(os.getenv("PORT", "8000"))
DOWNSTREAM_URLS = os.getenv("DOWNSTREAM_URLS", "").split(",")
DOWNSTREAM_URLS = [url.strip() for url in DOWNSTREAM_URLS if url.strip()]

app = FastAPI(title=SERVICE_NAME)

# Prometheus Metrics
REQUESTS = Counter(
    "http_requests_total", 
    "Total HTTP requests", 
    ["method", "endpoint", "status"]
)
LATENCY = Histogram(
    "http_request_duration_seconds", 
    "HTTP request latency in seconds", 
    ["method", "endpoint"]
)
MEMORY_GAUGE = Gauge(
    "service_memory_usage_bytes",
    "Simulated or actual resident memory usage in bytes"
)
CPU_GAUGE = Gauge(
    "service_cpu_usage_ratio",
    "Simulated or actual CPU usage ratio (0.0 to 1.0)"
)

# Fault States
FAULT_MEMORY_LEAK = False
FAULT_CPU_SPIKE = False
FAULT_ERROR_SPIKE = False
FAULT_DEPENDENCY_FAILURE = False
FAULT_DB_SATURATION = False
FAULT_SHARED_DB_SATURATION = False
FAULT_NETWORK_PARTITION = False
FAULT_CASCADING_FAILURE = False
FAULT_CONFIG_DRIFT = False
FAULT_CERT_EXPIRATION = False

# Memory leak storage
memory_leak_holder = []
cpu_threads = []
stop_cpu_threads = False

def memory_leak_worker():
    global FAULT_MEMORY_LEAK, memory_leak_holder
    logger.info("Starting memory leak worker thread...")
    while FAULT_MEMORY_LEAK:
        # Allocate ~15MB of data every second
        data = bytearray(15 * 1024 * 1024)
        memory_leak_holder.append(data)
        current_mem = len(memory_leak_holder) * 15 * 1024 * 1024 + 10 * 1024 * 1024
        MEMORY_GAUGE.set(current_mem)
        logger.info(f"Memory leak active. Simulated usage: {current_mem / (1024*1024):.1f} MB")
        time.sleep(1)

def cpu_spike_worker():
    global FAULT_CPU_SPIKE, stop_cpu_threads
    logger.info("Starting CPU spike worker thread...")
    while not stop_cpu_threads and FAULT_CPU_SPIKE:
        # Busy loop
        _ = 12345 * 54321
        # Periodically yield to avoid locking the system completely
        time.sleep(0.001)

@app.on_event("startup")
def startup_event():
    # Set default values for metrics
    MEMORY_GAUGE.set(20 * 1024 * 1024)  # 20MB baseline
    CPU_GAUGE.set(0.05)  # 5% baseline

@app.get("/health")
def health():
    if FAULT_ERROR_SPIKE:
        REQUESTS.labels(method="GET", endpoint="/health", status="500").inc()
        raise HTTPException(status_code=500, detail="HttpErrorSpike: Service Unhealthy (Error Spike Injected)")
    if FAULT_DEPENDENCY_FAILURE:
        REQUESTS.labels(method="GET", endpoint="/health", status="500").inc()
        raise HTTPException(status_code=500, detail="DependencyFailure: Connection failed to downstream service")
    if FAULT_DB_SATURATION:
        REQUESTS.labels(method="GET", endpoint="/health", status="500").inc()
        raise HTTPException(status_code=500, detail="DatabaseSaturation: Connection checkout timed out after 3000ms")
    if FAULT_SHARED_DB_SATURATION:
        REQUESTS.labels(method="GET", endpoint="/health", status="500").inc()
        if "user" in SERVICE_NAME:
            raise HTTPException(status_code=500, detail="DatabaseSaturation: Auth database connection checkout timed out after 3000ms. Login failures active.")
        elif "order" in SERVICE_NAME:
            raise HTTPException(status_code=500, detail="DatabaseSaturation: Order DB pool exhausted. Slow API latency and 504 timeouts.")
        elif "payment" in SERVICE_NAME:
            raise HTTPException(status_code=500, detail="DatabaseSaturation: Payment transaction commit failed. Ledger DB connection timeout.")
        else:
            raise HTTPException(status_code=500, detail="DatabaseSaturation: Shared database connection pool exhausted after 3000ms")
    if FAULT_NETWORK_PARTITION:
        REQUESTS.labels(method="GET", endpoint="/health", status="500").inc()
        raise HTTPException(status_code=500, detail="NetworkPartition: Network is unreachable on interface eth0")
    if FAULT_CASCADING_FAILURE:
        REQUESTS.labels(method="GET", endpoint="/health", status="500").inc()
        raise HTTPException(status_code=500, detail="CascadingFailure: Backpressure queue saturated")
    if FAULT_CONFIG_DRIFT:
        REQUESTS.labels(method="GET", endpoint="/health", status="500").inc()
        raise HTTPException(status_code=500, detail="ConfigurationDrift: Property database.max.connections has drifted to abc")
    if FAULT_CERT_EXPIRATION:
        REQUESTS.labels(method="GET", endpoint="/health", status="500").inc()
        raise HTTPException(status_code=500, detail="CertificateExpiration: SSL: CERTIFICATE_VERIFY_FAILED certificate has expired")
    
    REQUESTS.labels(method="GET", endpoint="/health", status="200").inc()
    return {"status": "healthy", "service": SERVICE_NAME}

@app.get("/metrics")
def metrics():
    # Update simulated metrics based on status
    if not FAULT_MEMORY_LEAK:
        # Normal baseline memory drift
        MEMORY_GAUGE.set(20 * 1024 * 1024 + (int(time.time()) % 100) * 1024)
    else:
        current_mem = len(memory_leak_holder) * 15 * 1024 * 1024 + 10 * 1024 * 1024
        MEMORY_GAUGE.set(current_mem)
        
    if not FAULT_CPU_SPIKE:
        CPU_GAUGE.set(0.05 + (int(time.time()) % 5) / 100.0)
    else:
        CPU_GAUGE.set(0.95)

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/")
def handle_request():
    start_time = time.time()
    
    # Check fault states
    if FAULT_ERROR_SPIKE:
        REQUESTS.labels(method="GET", endpoint="/", status="500").inc()
        raise HTTPException(status_code=500, detail=f"HttpErrorSpike: Internal Server Error in {SERVICE_NAME}")
    if FAULT_DEPENDENCY_FAILURE:
        REQUESTS.labels(method="GET", endpoint="/", status="503").inc()
        raise HTTPException(status_code=503, detail=f"DependencyFailure: Downstream service connection failed")
    if FAULT_DB_SATURATION:
        REQUESTS.labels(method="GET", endpoint="/", status="500").inc()
        raise HTTPException(status_code=500, detail=f"DatabaseSaturation: Connection checkout timed out after 3000ms")
    if FAULT_SHARED_DB_SATURATION:
        REQUESTS.labels(method="GET", endpoint="/", status="500").inc()
        if "user" in SERVICE_NAME:
            raise HTTPException(status_code=500, detail=f"DatabaseSaturation: Login authentication failed in {SERVICE_NAME} due to database pool exhaustion")
        elif "order" in SERVICE_NAME:
            raise HTTPException(status_code=504, detail=f"DatabaseSaturation: Gateway timeout on order checkout in {SERVICE_NAME} (latency: 3800ms)")
        elif "payment" in SERVICE_NAME:
            raise HTTPException(status_code=500, detail=f"DatabaseSaturation: Transaction commit failed in {SERVICE_NAME} due to database pool exhaustion")
        else:
            raise HTTPException(status_code=500, detail=f"DatabaseSaturation: Shared database error in {SERVICE_NAME}")
    if FAULT_NETWORK_PARTITION:
        REQUESTS.labels(method="GET", endpoint="/", status="500").inc()
        raise HTTPException(status_code=500, detail=f"NetworkPartition: Network is unreachable on interface eth0")
    if FAULT_CASCADING_FAILURE:
        REQUESTS.labels(method="GET", endpoint="/", status="500").inc()
        raise HTTPException(status_code=500, detail=f"CascadingFailure: Backpressure queue saturated")
    if FAULT_CONFIG_DRIFT:
        REQUESTS.labels(method="GET", endpoint="/", status="500").inc()
        raise HTTPException(status_code=500, detail=f"ConfigurationDrift: Property database.max.connections has drifted to abc")
    if FAULT_CERT_EXPIRATION:
        REQUESTS.labels(method="GET", endpoint="/", status="500").inc()
        raise HTTPException(status_code=500, detail=f"CertificateExpiration: SSL: CERTIFICATE_VERIFY_FAILED certificate has expired")

    # 2. Call Downstream Services
    downstream_results = {}
    for url in DOWNSTREAM_URLS:
        try:
            logger.info(f"{SERVICE_NAME} calling downstream: {url}")
            resp = requests.get(url, timeout=3.0)
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Downstream service {url} failed: {resp.text}")
            downstream_results[url] = resp.json()
        except Exception as e:
            logger.error(f"Downstream call failed: {str(e)}")
            REQUESTS.labels(method="GET", endpoint="/", status="500").inc()
            LATENCY.labels(method="GET", endpoint="/").observe(time.time() - start_time)
            raise HTTPException(status_code=500, detail=f"Error contacting downstream: {str(e)}")

    duration = time.time() - start_time
    LATENCY.labels(method="GET", endpoint="/").observe(duration)
    REQUESTS.labels(method="GET", endpoint="/", status="200").inc()
    
    return {
        "service": SERVICE_NAME,
        "status": "success",
        "timestamp": time.time(),
        "downstream": downstream_results
    }

# Fault Injection Endpoints
@app.post("/fault/memory-leak")
def inject_memory_leak():
    global FAULT_MEMORY_LEAK
    if not FAULT_MEMORY_LEAK:
        FAULT_MEMORY_LEAK = True
        threading.Thread(target=memory_leak_worker, daemon=True).start()
        logger.warning(f"Injected MEMORY LEAK into {SERVICE_NAME}")
    return {"message": f"Memory leak injected into {SERVICE_NAME}"}

@app.post("/fault/cpu-spike")
def inject_cpu_spike():
    global FAULT_CPU_SPIKE, stop_cpu_threads, cpu_threads
    if not FAULT_CPU_SPIKE:
        FAULT_CPU_SPIKE = True
        stop_cpu_threads = False
        cpu_threads = []
        # Start a thread per CPU core (or just 4 threads to make it spike)
        for i in range(4):
            t = threading.Thread(target=cpu_spike_worker, daemon=True)
            t.start()
            cpu_threads.append(t)
        logger.warning(f"Injected CPU SPIKE into {SERVICE_NAME}")
    return {"message": f"CPU spike injected into {SERVICE_NAME}"}

@app.post("/fault/error-spike")
def inject_error_spike():
    global FAULT_ERROR_SPIKE
    FAULT_ERROR_SPIKE = True
    logger.warning(f"Injected ERROR SPIKE into {SERVICE_NAME}")
    return {"message": f"Error spike injected into {SERVICE_NAME}"}

@app.post("/fault/dependency-failure")
def inject_dependency_failure():
    global FAULT_DEPENDENCY_FAILURE
    FAULT_DEPENDENCY_FAILURE = True
    logger.warning(f"Injected DEPENDENCY FAILURE into {SERVICE_NAME}")
    return {"message": f"Dependency failure injected into {SERVICE_NAME}"}

@app.post("/fault/db-saturation")
def inject_db_saturation():
    global FAULT_DB_SATURATION
    FAULT_DB_SATURATION = True
    logger.warning(f"Injected DATABASE SATURATION into {SERVICE_NAME}")
    return {"message": f"Database saturation injected into {SERVICE_NAME}"}

@app.post("/fault/shared-db-saturation")
def inject_shared_db_saturation():
    global FAULT_SHARED_DB_SATURATION
    FAULT_SHARED_DB_SATURATION = True
    logger.warning(f"Injected SHARED DATABASE SATURATION into {SERVICE_NAME}")
    return {"message": f"Shared database saturation injected into {SERVICE_NAME}"}

@app.post("/fault/network-partition")
def inject_network_partition():
    global FAULT_NETWORK_PARTITION
    FAULT_NETWORK_PARTITION = True
    logger.warning(f"Injected NETWORK PARTITION into {SERVICE_NAME}")
    return {"message": f"Network partition injected into {SERVICE_NAME}"}

@app.post("/fault/cascading-failure")
def inject_cascading_failure():
    global FAULT_CASCADING_FAILURE
    FAULT_CASCADING_FAILURE = True
    logger.warning(f"Injected CASCADING FAILURE into {SERVICE_NAME}")
    return {"message": f"Cascading failure injected into {SERVICE_NAME}"}

@app.post("/fault/config-drift")
def inject_config_drift():
    global FAULT_CONFIG_DRIFT
    FAULT_CONFIG_DRIFT = True
    logger.warning(f"Injected CONFIGURATION DRIFT into {SERVICE_NAME}")
    return {"message": f"Configuration drift injected into {SERVICE_NAME}"}

@app.post("/fault/cert-expiration")
def inject_cert_expiration():
    global FAULT_CERT_EXPIRATION
    FAULT_CERT_EXPIRATION = True
    logger.warning(f"Injected CERTIFICATE EXPIRATION into {SERVICE_NAME}")
    return {"message": f"Certificate expiration injected into {SERVICE_NAME}"}

@app.post("/fault/clear")
def clear_faults():
    global FAULT_MEMORY_LEAK, FAULT_CPU_SPIKE, FAULT_ERROR_SPIKE, FAULT_DEPENDENCY_FAILURE, FAULT_DB_SATURATION, FAULT_SHARED_DB_SATURATION, FAULT_NETWORK_PARTITION, FAULT_CASCADING_FAILURE, FAULT_CONFIG_DRIFT, FAULT_CERT_EXPIRATION, memory_leak_holder, stop_cpu_threads, cpu_threads
    logger.info(f"Clearing all faults for {SERVICE_NAME}")
    FAULT_MEMORY_LEAK = False
    FAULT_CPU_SPIKE = False
    FAULT_ERROR_SPIKE = False
    FAULT_DEPENDENCY_FAILURE = False
    FAULT_DB_SATURATION = False
    FAULT_SHARED_DB_SATURATION = False
    FAULT_NETWORK_PARTITION = False
    FAULT_CASCADING_FAILURE = False
    FAULT_CONFIG_DRIFT = False
    FAULT_CERT_EXPIRATION = False
    stop_cpu_threads = True
    
    # Wait for CPU threads to stop
    for t in cpu_threads:
        t.join(timeout=0.5)
    cpu_threads = []
    
    # Release memory leak allocations
    memory_leak_holder.clear()
    
    # Reset metrics
    MEMORY_GAUGE.set(20 * 1024 * 1024)
    CPU_GAUGE.set(0.05)
    
    return {"message": f"Faults cleared for {SERVICE_NAME}"}

@app.get("/logs")
def get_logs():
    lines = []
    timestamp_base = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    # Baseline normal logs
    lines.append(f"[INFO] {timestamp_base} - Starting request processing chain")
    lines.append(f"[INFO] {timestamp_base} - Connection pool healthy: active=5, idle=15")
    
    if FAULT_MEMORY_LEAK:
        lines.append(f"[WARNING] {timestamp_base} - JVM memory footprint approaching threshold")
        lines.append(f"[ERROR] {timestamp_base} - java.lang.OutOfMemoryError: Java heap space")
        lines.append(f"[ERROR] {timestamp_base} - Thread-15 fatal memory limit exceeded. Handlers terminating.")
    elif FAULT_CPU_SPIKE:
        lines.append(f"[WARNING] {timestamp_base} - CPU utilization crossed warning threshold (85%)")
        lines.append(f"[WARNING] {timestamp_base} - High utilization in thread pool executor: busy-loop detected")
        lines.append(f"[ERROR] {timestamp_base} - Process scheduler overloaded: CPU usage ratio=0.98")
    elif FAULT_ERROR_SPIKE:
        lines.append(f"[ERROR] {timestamp_base} - HTTP 500: Internal Server Error returned to gateway client")
        lines.append(f"[ERROR] {timestamp_base} - Unexpected validation failure in controller payload parsing")
    elif FAULT_DEPENDENCY_FAILURE:
        lines.append(f"[ERROR] {timestamp_base} - Error contacting downstream dependency: Connection refused")
        lines.append(f"[ERROR] {timestamp_base} - HTTP 503 Service Unavailable returned due to downstream outage")
    elif FAULT_DB_SATURATION:
        lines.append(f"[WARNING] {timestamp_base} - Database connection pool exhaustion warning")
        lines.append(f"[ERROR] {timestamp_base} - TimeoutException: Connection checkout timed out after 3000ms")
        lines.append(f"[ERROR] {timestamp_base} - Database saturated: active connections = 100, waiting = 45")
    elif FAULT_SHARED_DB_SATURATION:
        if "user" in SERVICE_NAME:
            lines.append(f"[WARNING] {timestamp_base} - DatabaseSaturation: Auth connection pool depleted. Active connections=50/50")
            lines.append(f"[ERROR] {timestamp_base} - DatabaseSaturation: User auth pool exhausted. Failed to authenticate user credentials trace_id=tr-pay-outage-01")
            lines.append(f"[ERROR] {timestamp_base} - Login failure: SELECT * FROM users query aborted due to timeout")
        elif "order" in SERVICE_NAME:
            lines.append(f"[WARNING] {timestamp_base} - High latency warning: order state commit delayed by 3800ms trace_id=tr-pay-outage-01")
            lines.append(f"[ERROR] {timestamp_base} - DatabaseSaturation: Order DB checkout timed out after 3000ms")
            lines.append(f"[ERROR] {timestamp_base} - HTTP 504 Gateway Timeout: API gateway slow response on checkout")
        elif "payment" in SERVICE_NAME:
            lines.append(f"[WARNING] {timestamp_base} - Shared database connection queue overflow on postgres-primary")
            lines.append(f"[ERROR] {timestamp_base} - DatabaseSaturation: Payment ledger transaction rollback: pool exhausted trace_id=tr-pay-outage-01")
            lines.append(f"[ERROR] {timestamp_base} - Transaction failure: Failed to commit payment charge of $49.99")
        else:
            lines.append(f"[WARNING] {timestamp_base} - Shared database connection pool exhausted")
            lines.append(f"[ERROR] {timestamp_base} - DatabaseSaturation: Connection checkout timed out after 3000ms trace_id=tr-pay-outage-01")
    elif FAULT_NETWORK_PARTITION:
        lines.append(f"[WARNING] {timestamp_base} - Socket timeout: connection to cluster peers dropped")
        lines.append(f"[ERROR] {timestamp_base} - Network partition active: unable to reach target subnet")
        lines.append(f"[ERROR] {timestamp_base} - OSError: Network is unreachable (routing table lookup failed)")
    elif FAULT_CASCADING_FAILURE:
        lines.append(f"[ERROR] {timestamp_base} - Downstream microservice failed with HTTP 500")
        lines.append(f"[ERROR] {timestamp_base} - Cascading failure: backpressure queue full, rejecting incoming traffic")
        lines.append(f"[ERROR] {timestamp_base} - RateLimiter: thread pool saturation, dropping request")
    elif FAULT_CONFIG_DRIFT:
        lines.append(f"[ERROR] {timestamp_base} - Configuration drift detected: parameter 'database.max.connections' holds drifted value 'abc'")
        lines.append(f"[ERROR] {timestamp_base} - Failed to initialize client session due to drifted config properties")
    elif FAULT_CERT_EXPIRATION:
        lines.append(f"[ERROR] {timestamp_base} - SSL connection handshake failed: remote host closed connection")
        lines.append(f"[ERROR] {timestamp_base} - SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired (_ssl.c:1129)")
        
    return Response(content="\n".join(lines), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
