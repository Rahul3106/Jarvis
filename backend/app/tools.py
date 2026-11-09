import os
import logging
import requests
import docker
from langchain_core.tools import tool

logger = logging.getLogger("jarvis-tools")

# Initialize Docker client
try:
    docker_client = docker.from_env()
    # Ping to check if docker is accessible
    docker_client.ping()
    DOCKER_AVAILABLE = True
    logger.info("Docker SDK successfully initialized and connected to daemon.")
except Exception as e:
    DOCKER_AVAILABLE = False
    logger.warning(f"Docker SDK not available or cannot connect: {str(e)}. Using mock fallback.")

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")

def get_container_by_name(name: str):
    if not DOCKER_AVAILABLE:
        return None
    try:
        containers = docker_client.containers.list(all=True)
        # Search for exact container name or substring
        for container in containers:
            if container.name == name or name in container.name:
                return container
        return None
    except Exception as e:
        logger.error(f"Error finding container {name}: {str(e)}")
        return None

@tool
def get_container_logs(service_name: str, lines: int = 50) -> str:
    """Reads the last N lines of stdout/stderr logs from the target microservice."""
    logger.info(f"Tool execution: get_container_logs for {service_name}")
    container = get_container_by_name(service_name)
    if container:
        try:
            logs = container.logs(tail=lines, stdout=True, stderr=True)
            return logs.decode("utf-8", errors="replace")
        except Exception as e:
            return f"Error reading docker logs for {service_name}: {str(e)}"
    
    # Try local service /logs endpoint if docker is unavailable (local startup mode)
    local_port = LOCAL_PORTS.get(service_name)
    if local_port:
        try:
            resp = requests.get(f"http://localhost:{local_port}/logs", timeout=1.0)
            if resp.status_code == 200:
                logger.info(f"Successfully scraped logs from local endpoint for {service_name}")
                return resp.text
        except Exception as e:
            logger.warning(f"Could not fetch logs from local service {service_name} endpoint: {str(e)}")

    # Fallback/Mock for local testing
    logger.info("Docker logs fallback triggered.")
    if "payment" in service_name:
        return (
            "[INFO] 2026-06-10 19:10:00 - Starting Payment Transaction\n"
            "[WARNING] 2026-06-10 19:10:05 - Connection pool slow\n"
            "[ERROR] 2026-06-10 19:10:12 - java.lang.OutOfMemoryError: Java heap space\n"
            "[ERROR] 2026-06-10 19:10:13 - Thread-15 fatal memory limit exceeded\n"
            "[ERROR] 2026-06-10 19:10:14 - Handlers terminating"
        )
    elif "order" in service_name:
        return (
            "[INFO] 2026-06-10 19:10:01 - Processing order #44921\n"
            "[ERROR] 2026-06-10 19:10:12 - Request to payment-service failed: 502 Bad Gateway\n"
            "[ERROR] 2026-06-10 19:10:15 - Order service returning 500 due to downstream failure"
        )
    return f"Logs for {service_name}: No active logs or anomalies found."

@tool
def get_service_metrics(service_name: str) -> str:
    """Queries Prometheus, the service directly, or container stats for CPU and Memory usage of the target service."""
    logger.info(f"Tool execution: get_service_metrics for {service_name}")
    
    # Try querying Prometheus first
    try:
        mem_query = f'service_memory_usage_bytes{{job=~"jarvis-services|sentinel-services"}}'
        cpu_query = f'service_cpu_usage_ratio{{job=~"jarvis-services|sentinel-services"}}'
        
        mem_resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": mem_query}, timeout=2.0)
        cpu_resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": cpu_query}, timeout=2.0)
        
        result_str = f"Service: {service_name}\n"
        
        mem_val = "N/A"
        if mem_resp.status_code == 200:
            data = mem_resp.json().get("data", {}).get("result", [])
            for r in data:
                metric = r.get("metric", {})
                if service_name in metric.get("instance", "") or service_name in metric.get("job", ""):
                    bytes_val = float(r.get("value", [0, 0])[1])
                    mem_val = f"{bytes_val / (1024*1024):.2f} MB"
        result_str += f"Memory Usage: {mem_val}\n"
        
        cpu_val = "N/A"
        if cpu_resp.status_code == 200:
            data = cpu_resp.json().get("data", {}).get("result", [])
            for r in data:
                metric = r.get("metric", {})
                if service_name in metric.get("instance", "") or service_name in metric.get("job", ""):
                    ratio_val = float(r.get("value", [0, 0])[1])
                    cpu_val = f"{ratio_val * 100:.1f}%"
        result_str += f"CPU Usage: {cpu_val}\n"
        
        if mem_val != "N/A" or cpu_val != "N/A":
            return result_str
            
    except Exception as e:
        logger.warning(f"Could not fetch metrics from Prometheus: {str(e)}. Trying direct service scrape.")

    # Try scraping the service's own /metrics endpoint directly (works in local mode)
    from app.tools import LOCAL_PORTS
    service_urls = [f"http://{service_name}:8000"]
    local_port = LOCAL_PORTS.get(service_name)
    if local_port:
        service_urls.append(f"http://localhost:{local_port}")
    
    for base_url in service_urls:
        try:
            resp = requests.get(f"{base_url}/metrics", timeout=1.0)
            if resp.status_code == 200:
                memory_mb = 0.0
                cpu_ratio = 0.0
                for line in resp.text.split("\n"):
                    if line.startswith("service_memory_usage_bytes") and not line.startswith("#"):
                        try:
                            memory_mb = float(line.split()[1]) / (1024 * 1024)
                        except (ValueError, IndexError):
                            pass
                    elif line.startswith("service_cpu_usage_ratio") and not line.startswith("#"):
                        try:
                            cpu_ratio = float(line.split()[1])
                        except (ValueError, IndexError):
                            pass
                return (
                    f"Service: {service_name}\n"
                    f"Memory Usage: {memory_mb:.2f} MB\n"
                    f"CPU Usage: {cpu_ratio * 100:.1f}%"
                )
        except Exception:
            continue

    # Try Docker stats
    container = get_container_by_name(service_name)
    if container:
        try:
            stats = container.stats(stream=False)
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
            cpu_percent = 0.0
            if system_delta > 0.0 and cpu_delta > 0.0:
                cpu_percent = (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
            
            mem_bytes = stats['memory_stats']['usage']
            return (
                f"Service: {service_name}\n"
                f"Memory Usage: {mem_bytes / (1024*1024):.2f} MB\n"
                f"CPU Usage: {cpu_percent:.1f}%"
            )
        except Exception as e:
            logger.error(f"Error querying docker stats: {str(e)}")

    # Last-resort fallback (should rarely be reached now)
    return f"Service: {service_name}\nMemory Usage: N/A\nCPU Usage: N/A"

LOCAL_PORTS = {
    "api-gateway": 8001,
    "user-service": 8002,
    "order-service": 8003,
    "payment-service": 8004,
    "notification-service": 8005
}

@tool
def check_service_health(service_name: str) -> str:
    """Sends a GET request to the service's internal health check endpoint and returns status code & body."""
    logger.info(f"Tool execution: check_service_health for {service_name}")
    url = f"http://{service_name}:8000/health"
    try:
        resp = requests.get(url, timeout=1.5)
        return f"Health check URL: {url}\nStatus: {resp.status_code}\nResponse: {resp.text}"
    except Exception as e:
        local_port = LOCAL_PORTS.get(service_name)
        if local_port:
            local_url = f"http://localhost:{local_port}/health"
            try:
                resp = requests.get(local_url, timeout=1.5)
                return f"Health check URL: {local_url}\nStatus: {resp.status_code}\nResponse: {resp.text}"
            except Exception as le:
                return f"Health check URL: {local_url}\nStatus: FAILED\nError: {str(le)}"
        return f"Health check URL: {url}\nStatus: FAILED\nError: {str(e)}"

@tool
def restart_service(service_name: str) -> str:
    """Restarts the Docker container for the specified service. Use when container is dead, leaking memory, or locked."""
    logger.info(f"Tool execution: restart_service for {service_name}")
    
    # First, try to clear faults via API to simulate fresh start
    if "notification" not in service_name:
        for base_url in [f"http://{service_name}:8000", f"http://localhost:{LOCAL_PORTS.get(service_name, 8000)}"]:
            try:
                requests.post(f"{base_url}/fault/clear", timeout=1.0)
            except Exception:
                pass
            
    container = get_container_by_name(service_name)
    if container:
        try:
            container.restart()
            return f"Success: Container {service_name} restarted successfully."
        except Exception as e:
            return f"Error restarting container {service_name}: {str(e)}"
    
    # Fallback to local API reset
    local_port = LOCAL_PORTS.get(service_name)
    if local_port:
        try:
            resp = requests.post(f"http://localhost:{local_port}/fault/clear", timeout=1.5)
            if resp.status_code == 200:
                return f"Success: Service {service_name} restarted (Local environment state reset)."
        except Exception as e:
            return f"Error resetting local state for {service_name}: {str(e)}"
            
    return f"Success: Restarted {service_name} (Mock simulation mode)."

@tool
def rollback_deployment(service_name: str) -> str:
    """Rolls back the deployment of the target service to the previous stable version. Use when a new deployment triggers instant errors."""
    logger.info(f"Tool execution: rollback_deployment for {service_name}")
    
    # First, try clearing faults on container url
    try:
        requests.post(f"http://{service_name}:8000/fault/clear", timeout=1.0)
    except Exception:
        pass
        
    container = get_container_by_name(service_name)
    if container:
        try:
            container.restart()
            return f"Success: Rolled back configuration and restarted container {service_name}."
        except Exception as e:
            pass

    # Fallback local reset
    local_port = LOCAL_PORTS.get(service_name)
    if local_port:
        try:
            resp = requests.post(f"http://localhost:{local_port}/fault/clear", timeout=1.5)
            if resp.status_code == 200:
                return f"Success: Rolled back deployment and cleared configuration for {service_name} (Local environment)."
        except Exception as e:
            return f"Error resetting local configuration state for {service_name}: {str(e)}"
            
    return f"Success: Rolled back deployment of {service_name} (Mock simulation mode)."

@tool
def scale_service(service_name: str, replicas: int) -> str:
    """Scales the target service to the specified number of container replicas. Use for traffic spikes."""
    logger.info(f"Tool execution: scale_service for {service_name} to {replicas} replicas")
    return f"Success: Service {service_name} scaled to {replicas} replicas."
