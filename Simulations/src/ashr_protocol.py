"""ASHR protocol simulation model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from .metrics import (
    DEFAULT_THETA,
    adaptive_link_cost,
    compute_metric_ranges,
    normalized_components,
    path_cost,
    should_trigger_update,
)
from .security import ASHRMessage, SecurityManager, ValidationResult
from .topology import fail_link, router_area


@dataclass
class RouterState:
    router_id: str
    area_id: int
    neighbors: set[str] = field(default_factory=set)
    hello_neighbors: set[str] = field(default_factory=set)
    sequence_number: int = 0
    link_state_database: dict[str, dict[str, Any]] = field(default_factory=dict)
    routing_table: dict[str, dict[str, Any]] = field(default_factory=dict)
    backup_table: dict[str, dict[str, Any]] = field(default_factory=dict)


class ASHRProtocol:
    """Adaptive Secure Hierarchical Routing simulation.

    The implementation models the behavior needed for an undergraduate
    routing-protocol evaluation: authenticated LSAs, event-driven updates,
    hierarchical area summaries, Dijkstra routing, and backup next hops.
    """

    def __init__(
        self,
        graph: nx.Graph,
        theta: float = DEFAULT_THETA,
        security: SecurityManager | None = None,
        detection_delay_units: int = 1,
        switch_delay_units: int = 1,
        backup_loss_factor: float = 0.0,
    ):
        self.graph = graph
        self.theta = theta
        self.routers = sorted(graph.nodes())
        self.router_states = {
            router: RouterState(router_id=router, area_id=router_area(graph, router))
            for router in self.routers
        }
        adjacency = {router: set(self.active_neighbors(router)) for router in self.routers}
        self.security = security or SecurityManager.from_topology(self.routers, adjacency)
        self.message_count = 0
        self.event_log: list[str] = []
        self.last_metric_ranges = compute_metric_ranges(self.graph)
        # Realistic timing/modeling parameters (in abstract time units)
        self.detection_delay_units = int(detection_delay_units)
        self.switch_delay_units = int(switch_delay_units)
        # Fraction of packets lost during a backup switch (informational)
        self.backup_loss_factor = float(backup_loss_factor)
        self.detect_neighbors()
        self.rebuild_link_state_database(reason="initialization")
        self.compute_all_routes()

    def active_neighbors(self, router: str) -> list[str]:
        return sorted(
            neighbor
            for neighbor in self.graph.neighbors(router)
            if not self.graph[router][neighbor].get("failed", False)
        )

    def detect_neighbors(self) -> None:
        """HELLO-style neighbor discovery model."""
        hello_messages = 0
        for router in self.routers:
            neighbors = set(self.active_neighbors(router))
            self.router_states[router].neighbors = neighbors
            self.router_states[router].hello_neighbors = set(neighbors)
            hello_messages += len(neighbors)
        self.message_count += hello_messages
        self.event_log.append(f"HELLO detection completed with {hello_messages} messages")

    def active_weighted_graph(self) -> nx.Graph:
        ranges = compute_metric_ranges(self.graph)
        weighted = nx.Graph()
        for node, attrs in self.graph.nodes(data=True):
            weighted.add_node(node, **attrs)
        for u, v, data in self.graph.edges(data=True):
            if data.get("failed", False):
                continue
            weighted.add_edge(u, v, weight=adaptive_link_cost(data, ranges), **data)
        return weighted

    def create_message(self, message_type: str, sender: str, body: dict[str, Any], ttl: int = 16) -> ASHRMessage:
        state = self.router_states[sender]
        state.sequence_number += 1
        message = ASHRMessage(
            message_type=message_type,
            sender_router_id=sender,
            area_id=state.area_id,
            sequence_number=state.sequence_number,
            ttl=ttl,
            body=body,
        )
        return self.security.sign_message(message)

    def create_lsa(self, router: str) -> ASHRMessage:
        ranges = compute_metric_ranges(self.graph)
        links = []
        for neighbor in self.active_neighbors(router):
            data = self.graph[router][neighbor]
            links.append(
                {
                    "neighbor": neighbor,
                    "cost": round(adaptive_link_cost(data, ranges), 6),
                    "latency_ms": data["latency_ms"],
                    "bandwidth_mbps": data["bandwidth_mbps"],
                    "packet_loss": data["packet_loss"],
                    "congestion": data["congestion"],
                    "error_rate": data.get("error_rate", 0.0),
                    "failed": data["failed"],
                }
            )
        return self.create_message("ASHR_LSA", router, {"links": links})

    def rebuild_link_state_database(self, reason: str) -> None:
        """Rebuild the LSDB from current topology and count event-driven LSAs."""
        lsa_messages = 0
        for router in self.routers:
            lsa = self.create_lsa(router)
            self.router_states[router].link_state_database[router] = lsa.body
            for receiver in self.active_neighbors(router):
                # In the simulation, neighbors validate the originated LSA
                # before it is considered floodable through the area/domain.
                validation = self.security.validate_message(receiver, lsa)
                if validation.accepted:
                    self.router_states[receiver].link_state_database[router] = lsa.body
                lsa_messages += 1
        self.message_count += lsa_messages
        self.last_metric_ranges = compute_metric_ranges(self.graph)
        self.event_log.append(f"LSDB rebuild for {reason}: {lsa_messages} ASHR-LSA transmissions")

    def generate_area_summaries(self) -> list[ASHRMessage]:
        summaries = []
        for abr in ["ABR1", "ABR2"]:
            if abr not in self.router_states:
                continue
            reachable_by_area: dict[int, list[str]] = {}
            for router in self.routers:
                reachable_by_area.setdefault(router_area(self.graph, router), []).append(router)
            message = self.create_message(
                "AREA_SUMMARY",
                abr,
                {"reachable_prefixes": {str(area): sorted(nodes) for area, nodes in reachable_by_area.items()}},
                ttl=16,
            )
            summaries.append(message)
        self.message_count += len(summaries)
        self.event_log.append(f"Generated {len(summaries)} AREA_SUMMARY messages")
        return summaries

    def compute_shortest_path(self, source: str, destination: str, graph: nx.Graph | None = None) -> tuple[list[str], float]:
        weighted = graph or self.active_weighted_graph()
        try:
            path = nx.shortest_path(weighted, source, destination, weight="weight")
            cost = float(nx.shortest_path_length(weighted, source, destination, weight="weight"))
            return path, cost
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return [], float("inf")

    def compute_backup_path(self, source: str, destination: str, primary_path: list[str]) -> tuple[list[str], float]:
        if len(primary_path) < 2:
            return [], float("inf")
        weighted = self.active_weighted_graph()
        first_hop = (primary_path[0], primary_path[1])
        if weighted.has_edge(*first_hop):
            weighted.remove_edge(*first_hop)
        return self.compute_shortest_path(source, destination, graph=weighted)

    def compute_all_routes(self) -> None:
        for source in self.routers:
            state = self.router_states[source]
            state.routing_table = {}
            state.backup_table = {}
            for destination in self.routers:
                if source == destination:
                    state.routing_table[destination] = {"path": [source], "next_hop": source, "cost": 0.0}
                    state.backup_table[destination] = {"path": [], "next_hop": None, "cost": float("inf")}
                    continue
                primary_path, primary_cost = self.compute_shortest_path(source, destination)
                backup_path, backup_cost = self.compute_backup_path(source, destination, primary_path)
                state.routing_table[destination] = {
                    "path": primary_path,
                    "next_hop": primary_path[1] if len(primary_path) > 1 else None,
                    "cost": primary_cost,
                }
                state.backup_table[destination] = {
                    "path": backup_path,
                    "next_hop": backup_path[1] if len(backup_path) > 1 else None,
                    "cost": backup_cost,
                }

    def get_route(self, source: str, destination: str) -> dict[str, Any]:
        return self.router_states[source].routing_table[destination]

    def get_backup_route(self, source: str, destination: str) -> dict[str, Any]:
        return self.router_states[source].backup_table[destination]

    def primary_path_uses_link(self, source: str, destination: str, u: str, v: str) -> bool:
        path = self.get_route(source, destination)["path"]
        link = {u, v}
        return any({a, b} == link for a, b in zip(path, path[1:]))

    def apply_link_failure(self, u: str, v: str, source: str = "R1", destination: str = "R10") -> dict[str, Any]:
        previous_route = dict(self.get_route(source, destination))
        previous_backup = dict(self.get_backup_route(source, destination))
        affected = self.primary_path_uses_link(source, destination, u, v)

        fail_link(self.graph, u, v)
        alert_messages = 2 if previous_route["path"] else 0
        self.message_count += alert_messages
        self.event_log.append(f"FAILURE_ALERT for {u}-{v}: {alert_messages} messages")

        backup_valid = bool(previous_backup["path"]) and not any(
            self.graph[a][b].get("failed", False)
            for a, b in zip(previous_backup["path"], previous_backup["path"][1:])
        )
        used_backup = affected and backup_valid

        # Model realistic delays: detection + FIB switch when backup used,
        # otherwise detection + control-plane recompute (modeled as 2 units).
        if used_backup:
            recovery_time_units = self.detection_delay_units + self.switch_delay_units
        else:
            recovery_time_units = self.detection_delay_units + 2

        self.detect_neighbors()
        self.rebuild_link_state_database(reason=f"failure {u}-{v}")
        self.compute_all_routes()
        recomputed_route = self.get_route(source, destination)

        if used_backup:
            final_path = previous_backup["path"]
            final_cost = previous_backup["cost"]
            final_next_hop = previous_backup["next_hop"]
        else:
            final_path = recomputed_route["path"]
            final_cost = recomputed_route["cost"]
            final_next_hop = recomputed_route["next_hop"]

        self.event_log.append(
            f"Failure {u}-{v}: affected={affected} used_backup={used_backup} recovery_time_units={recovery_time_units}"
        )

        return {
            "failed_link": f"{u}-{v}",
            "affected_primary": affected,
            "used_backup": used_backup,
            "previous_path": previous_route["path"],
            "backup_path": previous_backup["path"],
            "new_path": final_path,
            "new_next_hop": final_next_hop,
            "new_cost": final_cost,
            "recomputed_path": recomputed_route["path"],
            "recovery_time_units": recovery_time_units,
            "control_messages": alert_messages + sum(len(self.active_neighbors(router)) for router in self.routers),
        }

    def update_link_metrics(self, u: str, v: str, **attrs: float) -> dict[str, Any]:
        if not self.graph.has_edge(u, v):
            raise ValueError(f"Cannot update missing link {u}-{v}")

        old_data = dict(self.graph[u][v])
        for key, value in attrs.items():
            if key not in self.graph[u][v]:
                raise ValueError(f"Unknown link attribute {key}")
            self.graph[u][v][key] = value
        comparison_ranges = compute_metric_ranges(self.graph)
        old_cost = adaptive_link_cost(old_data, comparison_ranges)
        new_cost = adaptive_link_cost(self.graph[u][v], comparison_ranges)
        triggered = should_trigger_update(old_cost, new_cost, theta=self.theta)
        update_messages = 0
        if triggered:
            self.rebuild_link_state_database(reason=f"metric change {u}-{v}")
            self.compute_all_routes()
            update_messages = sum(len(self.active_neighbors(router)) for router in self.routers)
        self.event_log.append(
            f"Metric change {u}-{v}: old={old_cost:.4f} new={new_cost:.4f} triggered={triggered}"
        )
        return {
            "link": f"{u}-{v}",
            "old_cost": old_cost,
            "new_cost": new_cost,
            "old_components": normalized_components(old_data, comparison_ranges),
            "new_components": normalized_components(self.graph[u][v], comparison_ranges),
            "triggered_update": triggered,
            "control_messages": update_messages,
        }

    def update_ashr_costs(self, u: str, v: str, **attrs: float) -> dict[str, Any]:
        """Compatibility wrapper for updating ASHR adaptive link attributes."""
        return self.update_link_metrics(u, v, **attrs)

    def process_incoming_message(self, receiver: str, message: ASHRMessage) -> ValidationResult:
        validation = self.security.validate_message(receiver, message)
        if validation.accepted:
            self.message_count += 1
            if message.message_type in {"ASHR_LSA", "AREA_SUMMARY", "FAILURE_ALERT"}:
                self.router_states[receiver].link_state_database[message.sender_router_id] = message.body
        return validation

    def simulate_fake_low_cost_attack(self, receiver: str = "R1", sender: str = "R2", destination: str = "R10") -> ValidationResult:
        message = self.create_message(
            "ASHR_LSA",
            sender,
            {"destination": destination, "advertised_cost": 0},
            ttl=16,
        )
        return self.process_incoming_message(receiver, message)

    def simulate_spoofed_attack(self, receiver: str = "R1", malicious_sender: str = "MAL", destination: str = "R10") -> ValidationResult:
        message = ASHRMessage(
            message_type="ASHR_LSA",
            sender_router_id=malicious_sender,
            area_id=1,
            sequence_number=1,
            ttl=16,
            body={"destination": destination, "advertised_cost": 0},
            auth_tag="",
        )
        return self.process_incoming_message(receiver, message)

    def simulate_replay_attack(self, receiver: str = "R1", sender: str = "R2") -> tuple[ValidationResult, ValidationResult]:
        message = ASHRMessage(
            message_type="ASHR_LSA",
            sender_router_id=sender,
            area_id=router_area(self.graph, sender),
            sequence_number=999,
            ttl=16,
            body={"links": [{"neighbor": receiver, "cost": 0.2}]},
        )
        self.security.sign_message(message)
        first = self.process_incoming_message(receiver, message)
        replay = self.process_incoming_message(receiver, message)
        return first, replay

    def route_cost_from_current_graph(self, path: list[str]) -> float:
        return path_cost(self.graph, path, compute_metric_ranges(self.graph))
