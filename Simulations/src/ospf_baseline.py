"""Simplified OSPF-style link-state baseline.

This is not a full OSPF implementation. It models the behavior relevant to the
assignment comparison: link-state shortest-path routing with a static
bandwidth-derived cost and no ASHR-style adaptive metric or security checks.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass
class OSPFRunResult:
    convergence_time: int
    converged: bool
    control_messages: int


class OSPFBaseline:
    def __init__(self, graph: nx.Graph, reference_bandwidth_mbps: float = 1000.0):
        self.graph = graph
        self.reference_bandwidth_mbps = reference_bandwidth_mbps
        self.poisoned_routes: dict[tuple[str, str], dict[str, object]] = {}

    def _active_directed_edge_count(self) -> int:
        return sum(2 for _, _, data in self.graph.edges(data=True) if not data.get("failed", False))

    def _ospf_cost(self, data: dict) -> float:
        return max(1.0, self.reference_bandwidth_mbps / max(float(data["bandwidth_mbps"]), 1.0))

    def _weighted_graph(self) -> nx.Graph:
        weighted = nx.Graph()
        weighted.add_nodes_from(self.graph.nodes(data=True))
        for u, v, data in self.graph.edges(data=True):
            if data.get("failed", False):
                continue
            weighted.add_edge(u, v, weight=self._ospf_cost(data))
        return weighted

    def run_spf(self) -> OSPFRunResult:
        # One LSA flood phase and one SPF calculation phase.
        return OSPFRunResult(convergence_time=2, converged=True, control_messages=self._active_directed_edge_count() * 2)

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

    def apply_link_failure(self, u: str, v: str) -> OSPFRunResult:
        if not self.graph.has_edge(u, v):
            raise ValueError(f"Cannot fail missing link {u}-{v}")
        self.graph[u][v]["failed"] = True
        return self.run_spf()

    def update_link_metrics(self, u: str, v: str, **attrs: float) -> OSPFRunResult:
        if not self.graph.has_edge(u, v):
            raise ValueError(f"Cannot update missing link {u}-{v}")
        for key, value in attrs.items():
            if key in self.graph[u][v]:
                self.graph[u][v][key] = value
        # The baseline uses only bandwidth cost. Congestion, loss, and latency
        # changes do not trigger a route change in this model.
        return OSPFRunResult(convergence_time=0, converged=True, control_messages=0)

    def apply_fake_low_cost_advertisement(self, attacker: str, victim: str, destination: str, advertised_cost: float = 0.0) -> bool:
        if attacker not in self.graph.nodes or victim not in self.graph.nodes or destination not in self.graph.nodes:
            return False
        self.poisoned_routes[(victim, destination)] = {
            "path": [victim, attacker, destination],
            "cost": advertised_cost,
        }
        return True
