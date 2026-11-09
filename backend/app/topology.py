"""
J.A.R.V.I.S. Service Topology & Dependency Graph Module
Models service relationships, direct call graphs, and shared infrastructure dependencies.
Used by the Correlation Engine to determine topological proximity and root cause paths.
"""

from typing import Dict, List, Set, Any, Optional

# Directed call graph: service -> list of downstream services it calls
CALL_GRAPH: Dict[str, List[str]] = {
    "api-gateway": ["user-service", "order-service"],
    "user-service": [],
    "order-service": ["payment-service"],
    "payment-service": ["notification-service"],
    "notification-service": [],
}

# Shared infrastructure resources: resource -> list of services that depend on it
INFRASTRUCTURE_DEPENDENCIES: Dict[str, List[str]] = {
    "database-service": ["user-service", "order-service", "payment-service"],
}

# Inverted mapping: service -> list of shared infrastructure resources it uses
SERVICE_INFRASTRUCTURE: Dict[str, List[str]] = {}
for infra, svcs in INFRASTRUCTURE_DEPENDENCIES.items():
    for svc in svcs:
        SERVICE_INFRASTRUCTURE.setdefault(svc, []).append(infra)

# Inverted call graph: service -> list of upstream services that call it
REVERSE_CALL_GRAPH: Dict[str, List[str]] = {}
for upstream, downstreams in CALL_GRAPH.items():
    for downstream in downstreams:
        REVERSE_CALL_GRAPH.setdefault(downstream, []).append(upstream)

ALL_SERVICES = [
    "api-gateway",
    "user-service",
    "order-service",
    "payment-service",
    "notification-service",
    "database-service"
]

def get_topology_graph() -> Dict[str, Any]:
    """Returns complete topology representation for visualization and correlation."""
    return {
        "services": ALL_SERVICES,
        "call_graph": CALL_GRAPH,
        "infrastructure_dependencies": INFRASTRUCTURE_DEPENDENCIES,
        "service_infrastructure": SERVICE_INFRASTRUCTURE
    }

def get_downstream_services(service: str) -> List[str]:
    """Returns direct downstream dependencies of a service."""
    downstreams = list(CALL_GRAPH.get(service, []))
    # Include infrastructure dependencies as downstream
    downstreams.extend(SERVICE_INFRASTRUCTURE.get(service, []))
    return downstreams

def get_upstream_services(service: str) -> List[str]:
    """Returns services that directly call the given service."""
    upstreams = list(REVERSE_CALL_GRAPH.get(service, []))
    # If the service is an infrastructure resource (e.g. database-service),
    # return the services that depend on it
    if service in INFRASTRUCTURE_DEPENDENCIES:
        upstreams.extend(INFRASTRUCTURE_DEPENDENCIES[service])
    return upstreams

def get_shared_dependencies(service_a: str, service_b: str) -> List[str]:
    """Returns shared infrastructure resources between two services."""
    infra_a = set(SERVICE_INFRASTRUCTURE.get(service_a, []))
    infra_b = set(SERVICE_INFRASTRUCTURE.get(service_b, []))
    return list(infra_a.intersection(infra_b))

def get_topological_distance(service_a: str, service_b: str) -> int:
    """
    Computes shortest topological distance between two services.
    0: Same service
    1: Direct caller-callee relationship OR both share a common infrastructure resource
    2: 2-hop caller-callee relationship (e.g., api-gateway -> order-service -> payment-service)
    3+: Distant relationship
    999: Disconnected
    """
    if service_a == service_b:
        return 0

    # Direct edge
    if service_b in CALL_GRAPH.get(service_a, []) or service_a in CALL_GRAPH.get(service_b, []):
        return 1

    # Shared infrastructure resource (e.g. user-service and payment-service both use database-service)
    shared = get_shared_dependencies(service_a, service_b)
    if shared:
        return 1

    # Either is the shared infrastructure of the other
    if service_b in SERVICE_INFRASTRUCTURE.get(service_a, []) or service_a in SERVICE_INFRASTRUCTURE.get(service_b, []):
        return 1

    # BFS search for shortest path along call graph undirected
    queue = [(service_a, 0)]
    visited: Set[str] = {service_a}

    while queue:
        curr, dist = queue.pop(0)
        neighbors = set(CALL_GRAPH.get(curr, [])) | set(REVERSE_CALL_GRAPH.get(curr, []))
        for infra in SERVICE_INFRASTRUCTURE.get(curr, []):
            neighbors.add(infra)
            neighbors.update(INFRASTRUCTURE_DEPENDENCIES.get(infra, []))

        for nbr in neighbors:
            if nbr == service_b:
                return dist + 1
            if nbr not in visited:
                visited.add(nbr)
                queue.append((nbr, dist + 1))

    return 999

def are_services_topologically_related(service_a: str, service_b: str) -> bool:
    """Returns True if services have direct, shared, or 2-hop topological connection."""
    dist = get_topological_distance(service_a, service_b)
    return dist <= 2

