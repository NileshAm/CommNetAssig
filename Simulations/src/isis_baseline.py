"""Simplified IS-IS-style hierarchical link-state baseline."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass
class ISISRunResult:
    convergence_time: int
    converged: bool
    control_messages: int


class ISISBaseline:
    """Static-metric hierarchical link-state baseline.

    The model stores a configured metric at startup, similar to an engineered
    IS-IS deployment using configured link metrics. It can recompute after
    failures but does not adapt to transient congestion the way ASHR does.
    """

    def __init__(self, graph: nx.Graph):
        self.graph = graph
        self.configured_metrics = {
            tuple(sorted((u, v))): self._configured_metric(data)
            for u, v, data in graph.edges(data=True)
        }
        self.poisoned_routes: dict[tuple[str, str], dict[str, object]] = {}

    def _configured_metric(self, data: dict) -> float:
        return float(data.get("hop_cost", 1)) + float(data["latency_ms"]) / 10.0

    def _active_directed_edge_count(self) -> int:
        return sum(2 for _, _, data in self.graph.edges(data=True) if not data.get("failed", False))

    def _weighted_graph(self) -> nx.Graph:
        weighted = nx.Graph()
        weighted.add_nodes_from(self.graph.nodes(data=True))
        for u, v, data in self.graph.edges(data=True):
            if data.get("failed", False):
                continue
            weighted.add_edge(u, v, weight=self.configured_metrics[tuple(sorted((u, v)))])
        return weighted

    def run_spf(self) -> ISISRunResult:
        # Hierarchical summaries reduce flooding compared with a flat baseline.
        summary_messages = 2
        return ISISRunResult(convergence_time=2, converged=True, control_messages=self._active_directed_edge_count() + summary_messages)

    def get_path(self, source: str, destination: str) -> list[str]:
        poisoned = self.poisoned_routes.get((source, destination))
        if poisoned:
            return list(poisoned["path"])
        try:
            return nx.shortest_path(self._weighted_graph(), source, destination, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_cost(self, source: str, destination: str) -> float:
        poisoned = self.poisoned_routes.get((source, destination))
        if poisoned:
            return float(poisoned["cost"])
        try:
            return float(nx.shortest_path_length(self._weighted_graph(), source, destination, weight="weight"))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return float("inf")

    def apply_link_failure(self, u: str, v: str) -> ISISRunResult:
        if not self.graph.has_edge(u, v):
            raise ValueError(f"Cannot fail missing link {u}-{v}")
        self.graph[u][v]["failed"] = True
        return self.run_spf()

    def update_link_metrics(self, u: str, v: str, **attrs: float) -> ISISRunResult:
        if not self.graph.has_edge(u, v):
            raise ValueError(f"Cannot update missing link {u}-{v}")
        for key, value in attrs.items():
            if key in self.graph[u][v]:
                self.graph[u][v][key] = value
        # Configured IS-IS metrics remain unchanged in this baseline.
        return ISISRunResult(convergence_time=0, converged=True, control_messages=0)

    def apply_fake_low_cost_advertisement(self, attacker: str, victim: str, destination: str, advertised_cost: float = 0.0) -> bool:
        if attacker not in self.graph.nodes or victim not in self.graph.nodes or destination not in self.graph.nodes:
            return False
        self.poisoned_routes[(victim, destination)] = {
            "path": [victim, attacker, destination],
            "cost": advertised_cost,
        }
        return True
