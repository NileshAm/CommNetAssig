"""Network topology construction for the ASHR assignment simulation."""

from __future__ import annotations

from typing import Iterable

import networkx as nx


AREA_1_ROUTERS = ["R1", "R2", "R3", "R4", "R5", "R6"]
BACKBONE_ROUTERS = ["ABR1", "ABR2"]
AREA_2_ROUTERS = ["R7", "R8", "R9", "R10"]


def _add_link(
    graph: nx.Graph,
    u: str,
    v: str,
    latency_ms: float,
    bandwidth_mbps: float,
    packet_loss: float,
    congestion: float,
    error_rate: float | None = None,
    hop_cost: int = 1,
) -> None:
    if error_rate is None:
        error_rate = float(packet_loss) * 0.5
    graph.add_edge(
        u,
        v,
        latency_ms=float(latency_ms),
        bandwidth_mbps=float(bandwidth_mbps),
        packet_loss=float(packet_loss),
        congestion=float(congestion),
        error_rate=float(error_rate),
        failed=False,
        hop_cost=int(hop_cost),
    )


def create_hierarchical_topology() -> nx.Graph:
    """Create the deterministic ASHR study topology.

    The graph intentionally includes two independent R1-to-R10 corridors:
    one through R2/R3/ABR1 and another through R4/R5/R6/ABR2. This allows
    fast backup next-hop behavior to be demonstrated after a primary-link
    failure.
    """
    graph = nx.Graph(name="ASHR hierarchical topology")

    for router in AREA_1_ROUTERS:
        graph.add_node(router, area_id=1, role="internal")
    for router in BACKBONE_ROUTERS:
        graph.add_node(router, area_id=0, role="area_border")
    for router in AREA_2_ROUTERS:
        graph.add_node(router, area_id=2, role="internal")

    # Area 1 primary corridor.
    _add_link(graph, "R1", "R2", latency_ms=4, bandwidth_mbps=200, packet_loss=0.001, congestion=0.05)
    _add_link(graph, "R2", "R3", latency_ms=5, bandwidth_mbps=200, packet_loss=0.001, congestion=0.05)
    _add_link(graph, "R3", "ABR1", latency_ms=4, bandwidth_mbps=200, packet_loss=0.001, congestion=0.05)

    # Area 1 redundant corridor.
    _add_link(graph, "R1", "R4", latency_ms=8, bandwidth_mbps=120, packet_loss=0.002, congestion=0.12)
    _add_link(graph, "R4", "R5", latency_ms=6, bandwidth_mbps=120, packet_loss=0.002, congestion=0.12)
    _add_link(graph, "R5", "R6", latency_ms=5, bandwidth_mbps=120, packet_loss=0.002, congestion=0.12)
    _add_link(graph, "R6", "ABR2", latency_ms=5, bandwidth_mbps=150, packet_loss=0.001, congestion=0.08)

    # Cross-links inside Area 1 improve resilience without hiding the main path.
    _add_link(graph, "R2", "R5", latency_ms=8, bandwidth_mbps=100, packet_loss=0.003, congestion=0.18)
    _add_link(graph, "R3", "R6", latency_ms=9, bandwidth_mbps=100, packet_loss=0.003, congestion=0.18)

    # Backbone. ABR1-ABR2 is the intended normal inter-area transit link.
    _add_link(graph, "ABR1", "ABR2", latency_ms=3, bandwidth_mbps=1000, packet_loss=0.0005, congestion=0.03)

    # Area 2. ABR2 to R8/R10 is the preferred low-delay exit; ABR1 to R7 is
    # available but intentionally less attractive before congestion changes.
    _add_link(graph, "ABR1", "R7", latency_ms=13, bandwidth_mbps=90, packet_loss=0.003, congestion=0.20)
    _add_link(graph, "ABR2", "R8", latency_ms=5, bandwidth_mbps=180, packet_loss=0.001, congestion=0.06)
    _add_link(graph, "R8", "R10", latency_ms=6, bandwidth_mbps=160, packet_loss=0.001, congestion=0.06)
    _add_link(graph, "R8", "R9", latency_ms=5, bandwidth_mbps=130, packet_loss=0.002, congestion=0.10)
    _add_link(graph, "R7", "R9", latency_ms=5, bandwidth_mbps=120, packet_loss=0.002, congestion=0.12)
    _add_link(graph, "R9", "R10", latency_ms=4, bandwidth_mbps=140, packet_loss=0.002, congestion=0.10)

    return graph


def create_scalable_hierarchical_topology(node_count: int) -> nx.Graph:
    """Create a larger deterministic hierarchical topology for scalability tests.

    ``node_count`` includes the two backbone ABRs. The generated topology keeps
    the same ASHR idea as the assignment topology: two areas connected through a
    backbone, plus a redundant source-side exit so backup next-hop behavior can
    be tested as the network grows.
    """
    if node_count < 12:
        raise ValueError("Scalable topology requires at least 12 routers")

    area_1_count = max(5, (node_count - 2) // 2)
    area_2_count = node_count - 2 - area_1_count
    if area_2_count < 5:
        area_2_count = 5
        area_1_count = node_count - 2 - area_2_count

    graph = nx.Graph(name=f"ASHR scalable topology ({node_count} routers)")
    area_1 = [f"A1R{i}" for i in range(1, area_1_count + 1)]
    area_2 = [f"A2R{i}" for i in range(1, area_2_count + 1)]

    for router in area_1:
        graph.add_node(router, area_id=1, role="internal")
    graph.add_node("ABR1", area_id=0, role="area_border")
    graph.add_node("ABR2", area_id=0, role="area_border")
    for router in area_2:
        graph.add_node(router, area_id=2, role="internal")

    for index, (u, v) in enumerate(zip(area_1, area_1[1:]), start=1):
        _add_link(
            graph,
            u,
            v,
            latency_ms=3 + (index % 3),
            bandwidth_mbps=220,
            packet_loss=0.001,
            congestion=0.05,
        )
    _add_link(graph, area_1[-1], "ABR1", latency_ms=4, bandwidth_mbps=220, packet_loss=0.001, congestion=0.05)

    # Redundant source-side route into ABR2. It is deliberately a little less
    # attractive than the primary chain but remains available after first-hop
    # failure.
    midpoint_1 = area_1[max(2, area_1_count // 2)]
    _add_link(graph, area_1[0], midpoint_1, latency_ms=11, bandwidth_mbps=120, packet_loss=0.003, congestion=0.16)
    _add_link(graph, midpoint_1, "ABR2", latency_ms=8, bandwidth_mbps=140, packet_loss=0.002, congestion=0.12)
    for index in range(2, area_1_count - 1, 4):
        _add_link(
            graph,
            area_1[index],
            area_1[min(index + 2, area_1_count - 1)],
            latency_ms=10,
            bandwidth_mbps=110,
            packet_loss=0.003,
            congestion=0.18,
        )

    _add_link(graph, "ABR1", "ABR2", latency_ms=3, bandwidth_mbps=1000, packet_loss=0.0005, congestion=0.03)

    _add_link(graph, "ABR2", area_2[0], latency_ms=4, bandwidth_mbps=220, packet_loss=0.001, congestion=0.05)
    for index, (u, v) in enumerate(zip(area_2, area_2[1:]), start=1):
        _add_link(
            graph,
            u,
            v,
            latency_ms=3 + (index % 3),
            bandwidth_mbps=210,
            packet_loss=0.001,
            congestion=0.05,
        )

    midpoint_2 = area_2[max(2, area_2_count // 2)]
    _add_link(graph, "ABR1", midpoint_2, latency_ms=12, bandwidth_mbps=120, packet_loss=0.003, congestion=0.15)
    _add_link(graph, midpoint_2, area_2[-1], latency_ms=8, bandwidth_mbps=130, packet_loss=0.002, congestion=0.12)
    for index in range(1, area_2_count - 2, 5):
        _add_link(
            graph,
            area_2[index],
            area_2[min(index + 2, area_2_count - 1)],
            latency_ms=9,
            bandwidth_mbps=120,
            packet_loss=0.002,
            congestion=0.14,
        )

    graph.graph["source"] = area_1[0]
    graph.graph["destination"] = area_2[-1]
    return graph


def active_edges(graph: nx.Graph) -> Iterable[tuple[str, str, dict]]:
    for u, v, data in graph.edges(data=True):
        if not data.get("failed", False):
            yield u, v, data


def fail_link(graph: nx.Graph, u: str, v: str) -> None:
    if not graph.has_edge(u, v):
        raise ValueError(f"Cannot fail missing link {u}-{v}")
    graph[u][v]["failed"] = True


def restore_link(graph: nx.Graph, u: str, v: str) -> None:
    if not graph.has_edge(u, v):
        raise ValueError(f"Cannot restore missing link {u}-{v}")
    graph[u][v]["failed"] = False


def router_area(graph: nx.Graph, router_id: str) -> int:
    return int(graph.nodes[router_id]["area_id"])


def set_link_attributes(graph: nx.Graph, u: str, v: str, **attrs: float) -> None:
    if not graph.has_edge(u, v):
        raise ValueError(f"Cannot update missing link {u}-{v}")
    for key, value in attrs.items():
        if key not in graph[u][v]:
            raise ValueError(f"Unknown link attribute {key}")
        graph[u][v][key] = value
