"""Adaptive normalized link metric for ASHR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import networkx as nx

from .topology import active_edges


WEIGHTS = {
    "hop": 0.20,
    "latency": 0.30,
    "bandwidth": 0.25,
    "packet_loss": 0.15,
    "congestion": 0.10,
}

DEFAULT_THETA = 0.15


@dataclass(frozen=True)
class MetricRanges:
    max_hop: float
    min_latency: float
    max_latency: float
    min_inverse_bandwidth: float
    max_inverse_bandwidth: float
    min_packet_loss: float
    max_packet_loss: float
    min_congestion: float
    max_congestion: float


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return 0.0
    return _bounded((value - minimum) / (maximum - minimum))


def compute_metric_ranges(graph: nx.Graph) -> MetricRanges:
    edges = list(active_edges(graph))
    if not edges:
        return MetricRanges(1, 0, 1, 0, 1, 0, 1, 0, 1)

    hop_values = [float(data.get("hop_cost", 1)) for _, _, data in edges]
    latency_values = [float(data["latency_ms"]) for _, _, data in edges]
    inverse_bandwidth_values = [1.0 / max(float(data["bandwidth_mbps"]), 0.000001) for _, _, data in edges]
    packet_loss_values = [float(data["packet_loss"]) for _, _, data in edges]
    congestion_values = [float(data["congestion"]) for _, _, data in edges]

    return MetricRanges(
        max_hop=max(max(hop_values), 1.0),
        min_latency=min(latency_values),
        max_latency=max(latency_values),
        min_inverse_bandwidth=min(inverse_bandwidth_values),
        max_inverse_bandwidth=max(inverse_bandwidth_values),
        min_packet_loss=min(packet_loss_values),
        max_packet_loss=max(packet_loss_values),
        min_congestion=min(congestion_values),
        max_congestion=max(congestion_values),
    )


def normalized_components(link_data: Mapping[str, float], ranges: MetricRanges) -> dict[str, float]:
    """Return bounded normalized metric components for a link."""
    hop = _bounded(float(link_data.get("hop_cost", 1)) / ranges.max_hop)
    latency = _normalize(float(link_data["latency_ms"]), ranges.min_latency, ranges.max_latency)
    inverse_bandwidth = 1.0 / max(float(link_data["bandwidth_mbps"]), 0.000001)
    bandwidth = _normalize(
        inverse_bandwidth,
        ranges.min_inverse_bandwidth,
        ranges.max_inverse_bandwidth,
    )
    packet_loss = _normalize(float(link_data["packet_loss"]), ranges.min_packet_loss, ranges.max_packet_loss)
    congestion = _normalize(float(link_data["congestion"]), ranges.min_congestion, ranges.max_congestion)
    return {
        "hop": hop,
        "latency": latency,
        "bandwidth": bandwidth,
        "packet_loss": packet_loss,
        "congestion": congestion,
    }


def adaptive_link_cost(link_data: Mapping[str, float], ranges: MetricRanges) -> float:
    """Compute ASHR composite cost.

    Cij = 0.20H' + 0.30L' + 0.25B' + 0.15P' + 0.10Q'
    """
    components = normalized_components(link_data, ranges)
    cost = sum(WEIGHTS[name] * components[name] for name in WEIGHTS)
    return _bounded(cost)


def should_trigger_update(old_cost: float, new_cost: float, theta: float = DEFAULT_THETA) -> bool:
    """Metric damping: ignore small fluctuations below theta."""
    return abs(float(new_cost) - float(old_cost)) > theta


def path_cost(graph: nx.Graph, path: list[str], ranges: MetricRanges | None = None) -> float:
    if not path or len(path) == 1:
        return 0.0
    ranges = ranges or compute_metric_ranges(graph)
    total = 0.0
    for u, v in zip(path, path[1:]):
        if graph[u][v].get("failed", False):
            return float("inf")
        total += adaptive_link_cost(graph[u][v], ranges)
    return total
