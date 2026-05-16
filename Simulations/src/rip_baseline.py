"""Educational RIP-style distance-vector baseline."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


RIP_INFINITY = 16


@dataclass
class RIPRunResult:
    rounds: int
    converged: bool
    control_messages: int


class RIPBaseline:
    """Simplified hop-count distance-vector protocol.

    This intentionally omits authentication and advanced loop mitigation so
    that the simulation can compare ASHR against a vulnerable baseline.
    """

    def __init__(self, graph: nx.Graph, infinity: int = RIP_INFINITY):
        self.graph = graph
        self.infinity = infinity
        self.routers = sorted(graph.nodes())
        self.routing_table: dict[str, dict[str, dict[str, object]]] = {}
        self.reset_tables()

    def reset_tables(self) -> None:
        self.routing_table = {}
        for router in self.routers:
            self.routing_table[router] = {}
            for destination in self.routers:
                if router == destination:
                    self.routing_table[router][destination] = {"distance": 0, "next_hop": router}
                else:
                    self.routing_table[router][destination] = {"distance": self.infinity, "next_hop": None}
            for neighbor in self.active_neighbors(router):
                self.routing_table[router][neighbor] = {"distance": 1, "next_hop": neighbor}

    def active_neighbors(self, router: str) -> list[str]:
        return sorted(
            neighbor
            for neighbor in self.graph.neighbors(router)
            if not self.graph[router][neighbor].get("failed", False)
        )

    def active_directed_edge_count(self) -> int:
        return sum(2 for _, _, data in self.graph.edges(data=True) if not data.get("failed", False))

    def run_until_converged(self, max_rounds: int = 50, reset: bool = False) -> RIPRunResult:
        if reset:
            self.reset_tables()

        control_messages = 0
        for round_number in range(1, max_rounds + 1):
            old = {
                router: {
                    destination: dict(route)
                    for destination, route in destinations.items()
                }
                for router, destinations in self.routing_table.items()
            }
            changed = False
            control_messages += self.active_directed_edge_count()

            for router in self.routers:
                for destination in self.routers:
                    if router == destination:
                        continue
                    best_distance = self.infinity
                    best_next_hop = None
                    for neighbor in self.active_neighbors(router):
                        neighbor_distance = int(old[neighbor][destination]["distance"])
                        candidate = min(self.infinity, 1 + neighbor_distance)
                        if candidate < best_distance:
                            best_distance = candidate
                            best_next_hop = neighbor
                    if best_distance != old[router][destination]["distance"] or best_next_hop != old[router][destination]["next_hop"]:
                        self.routing_table[router][destination] = {
                            "distance": best_distance,
                            "next_hop": best_next_hop,
                        }
                        changed = True

            if not changed:
                return RIPRunResult(rounds=round_number, converged=True, control_messages=control_messages)

        return RIPRunResult(rounds=max_rounds, converged=False, control_messages=control_messages)

    def get_path(self, source: str, destination: str) -> list[str]:
        if source == destination:
            return [source]
        path = [source]
        current = source
        visited = {source}
        while current != destination:
            route = self.routing_table[current][destination]
            next_hop = route["next_hop"]
            if next_hop is None or route["distance"] >= self.infinity:
                return []
            if str(next_hop) in visited:
                return []
            current = str(next_hop)
            path.append(current)
            visited.add(current)
            if len(path) > len(self.routers):
                return []
        return path

    def get_distance(self, source: str, destination: str) -> int:
        return int(self.routing_table[source][destination]["distance"])

    def apply_link_failure(self, u: str, v: str, max_rounds: int = 50) -> RIPRunResult:
        if not self.graph.has_edge(u, v):
            raise ValueError(f"Cannot fail missing link {u}-{v}")
        self.graph[u][v]["failed"] = True
        return self.run_until_converged(max_rounds=max_rounds, reset=False)

    def apply_fake_low_cost_advertisement(self, attacker: str, victim: str, destination: str, advertised_cost: int = 0) -> bool:
        """Accept a forged neighbor route advertisement.

        The victim trusts the update because the simplified baseline has no
        authentication or sequence validation.
        """
        if attacker not in self.graph.nodes or victim not in self.graph.nodes or destination not in self.graph.nodes:
            return False
        accepted_distance = min(self.infinity, 1 + int(advertised_cost))
        if accepted_distance < self.get_distance(victim, destination):
            self.routing_table[victim][destination] = {
                "distance": accepted_distance,
                "next_hop": attacker,
            }
            return True
        return False
