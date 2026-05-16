"""Simplified BGP-style path-vector baseline.

The model is intentionally small: it chooses a route by AS-path length over the
available topology and ignores intradomain quality signals such as congestion,
latency, and packet loss.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass
class BGPRunResult:
    convergence_time: int
    converged: bool
    control_messages: int


class BGPBaseline:
    def __init__(self, graph: nx.Graph):
        self.graph = graph
        self.poisoned_routes: dict[tuple[str, str], dict[str, object]] = {}

    def _active_directed_edge_count(self) -> int:
        return sum(2 for _, _, data in self.graph.edges(data=True) if not data.get("failed", False))

    def _active_graph(self) -> nx.Graph:
        active = nx.Graph()
        active.add_nodes_from(self.graph.nodes(data=True))
        for u, v, data in self.graph.edges(data=True):
            if not data.get("failed", False):
                active.add_edge(u, v)
        return active

    def converge(self) -> BGPRunResult:
        # Path-vector withdrawals and re-advertisements are intentionally
        # modeled as slower than intradomain link-state recomputation.
        convergence_time = 6
        return BGPRunResult(
            convergence_time=convergence_time,
            converged=True,
            control_messages=self._active_directed_edge_count() * convergence_time,
        )

    def get_path(self, source: str, destination: str) -> list[str]:
        poisoned = self.poisoned_routes.get((source, destination))
        if poisoned:
            return list(poisoned["path"])
        try:
            return nx.shortest_path(self._active_graph(), source, destination)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_cost(self, source: str, destination: str) -> int:
        poisoned = self.poisoned_routes.get((source, destination))
        if poisoned:
            return int(poisoned["cost"])
        path = self.get_path(source, destination)
        if not path:
            return 999
        return len(path) - 1

    def apply_link_failure(self, u: str, v: str) -> BGPRunResult:
        if not self.graph.has_edge(u, v):
            raise ValueError(f"Cannot fail missing link {u}-{v}")
        self.graph[u][v]["failed"] = True
        return self.converge()

    def update_link_metrics(self, u: str, v: str, **attrs: float) -> BGPRunResult:
        if not self.graph.has_edge(u, v):
            raise ValueError(f"Cannot update missing link {u}-{v}")
        for key, value in attrs.items():
            if key in self.graph[u][v]:
                self.graph[u][v][key] = value
        # BGP-style path selection ignores these intradomain link qualities.
        return BGPRunResult(convergence_time=0, converged=True, control_messages=0)

    def apply_fake_low_cost_advertisement(self, attacker: str, victim: str, destination: str, local_pref: int = 200) -> bool:
        if attacker not in self.graph.nodes or victim not in self.graph.nodes or destination not in self.graph.nodes:
            return False
        self.poisoned_routes[(victim, destination)] = {
            "path": [victim, attacker, destination],
            "cost": 1,
            "local_pref": local_pref,
        }
        return True
