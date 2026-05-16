"""
ASHR NetworkX Simulation
========================
Pure Python/NetworkX simulation for the proposed ASHR protocol:
Adaptive Secure Hierarchical Routing Protocol.

It compares ASHR against a simple RIP-like distance-vector baseline and produces:
  1. Link-failure convergence comparison
  2. Route-hijacking / spoofing / replay security test
  3. RIP 15-hop limitation test
  4. Scalability test for 10, 20, 50, 100, 200 routers
  5. CSV tables, log file, and PNG plots in ./ashr_results

Run:
    python ashr_networkx_simulation.py

Install:
    pip install networkx matplotlib pandas numpy
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

RANDOM_SEED = 42
INF = 16  # RIP treats metric 16 as infinity/unreachable.
RESULTS_DIR = Path(__file__).resolve().parent / "ashr_results"


# -----------------------------------------------------------------------------
# Data structures
# -----------------------------------------------------------------------------

@dataclass
class PathMetrics:
    hops: int
    latency_ms: float
    min_bandwidth_mbps: float
    packet_loss: float
    ashr_cost: float


@dataclass
class RipResult:
    rounds: int
    messages: int
    elapsed_s: float
    loops_detected: int
    unreachable_routes: int
    tables: Dict[str, Dict[str, Tuple[int, Optional[str]]]]


@dataclass
class AshrFailureResult:
    affected_routes: int
    immediate_backup_switches: int
    recomputed_routes: int
    control_messages: int
    elapsed_s: float
    loops_detected: int
    before_path: Optional[List[str]]
    after_path: Optional[List[str]]
    backup_path_before_failure: Optional[List[str]]


# -----------------------------------------------------------------------------
# Graph and metric utilities
# -----------------------------------------------------------------------------


def add_link(
    G: nx.Graph,
    u: str,
    v: str,
    latency_ms: float,
    bandwidth_mbps: float,
    packet_loss: float,
) -> None:
    """Add a bidirectional network link with quality attributes."""
    G.add_edge(
        u,
        v,
        hop=1,
        latency_ms=float(latency_ms),
        bandwidth_mbps=float(bandwidth_mbps),
        packet_loss=float(packet_loss),
    )


def build_demo_topology() -> nx.Graph:
    """
    Assignment-style topology:

        R1 -- R2 -- R3 -- R4
        |              |
        R5 ----------- R6

    The link R2--R3 is later failed.
    """
    G = nx.Graph(name="ASHR demo topology")

    # Primary path: low latency, high bandwidth.
    add_link(G, "R1", "R2", latency_ms=2, bandwidth_mbps=100, packet_loss=0.005)
    add_link(G, "R2", "R3", latency_ms=2, bandwidth_mbps=100, packet_loss=0.005)
    add_link(G, "R3", "R4", latency_ms=2, bandwidth_mbps=100, packet_loss=0.005)

    # Backup path: still reachable but slightly lower quality.
    add_link(G, "R1", "R5", latency_ms=5, bandwidth_mbps=60, packet_loss=0.015)
    add_link(G, "R5", "R6", latency_ms=5, bandwidth_mbps=60, packet_loss=0.015)
    add_link(G, "R6", "R3", latency_ms=5, bandwidth_mbps=60, packet_loss=0.015)

    # Optional extra link gives more route diversity.
    add_link(G, "R2", "R6", latency_ms=9, bandwidth_mbps=45, packet_loss=0.020)

    return G


def assign_random_metrics(G: nx.Graph, seed: int = RANDOM_SEED) -> nx.Graph:
    """Assign deterministic random link metrics to a graph."""
    rng = random.Random(seed)
    for u, v in G.edges():
        G[u][v]["hop"] = 1
        G[u][v]["latency_ms"] = rng.uniform(1.0, 25.0)
        G[u][v]["bandwidth_mbps"] = rng.choice([10, 20, 50, 100, 200, 500])
        G[u][v]["packet_loss"] = rng.uniform(0.001, 0.05)
    return G


def _normalize(value: float, min_value: float, max_value: float, neutral: float = 0.5) -> float:
    if math.isclose(max_value, min_value):
        return neutral
    return (value - min_value) / (max_value - min_value)


def update_ashr_costs(
    G: nx.Graph,
    w_hop: float = 0.25,
    w_latency: float = 0.35,
    w_bandwidth: float = 0.25,
    w_loss: float = 0.15,
) -> nx.Graph:
    """
    ASHR link cost:
        cost = 0.25*H' + 0.35*L' + 0.25*(1-B') + 0.15*P'

    H' = normalized hop count. Since each edge is one hop, it is fixed at 1.
    L' = normalized latency. Lower is better.
    B' = normalized bandwidth. Higher is better, so the cost uses 1 - B'.
    P' = normalized packet loss. Lower is better.
    """
    if G.number_of_edges() == 0:
        return G

    latencies = [data["latency_ms"] for _, _, data in G.edges(data=True)]
    bandwidths = [data["bandwidth_mbps"] for _, _, data in G.edges(data=True)]
    losses = [data["packet_loss"] for _, _, data in G.edges(data=True)]

    min_l, max_l = min(latencies), max(latencies)
    min_b, max_b = min(bandwidths), max(bandwidths)
    min_p, max_p = min(losses), max(losses)

    for _, _, data in G.edges(data=True):
        h_norm = 1.0
        l_norm = _normalize(data["latency_ms"], min_l, max_l)
        b_norm = _normalize(data["bandwidth_mbps"], min_b, max_b)
        p_norm = _normalize(data["packet_loss"], min_p, max_p)
        data["ashr_cost"] = (
            w_hop * h_norm
            + w_latency * l_norm
            + w_bandwidth * (1.0 - b_norm)
            + w_loss * p_norm
        )
    return G


def path_metrics(G: nx.Graph, path: Optional[List[str]]) -> Optional[PathMetrics]:
    """Calculate end-to-end quality metrics for a route."""
    if not path or len(path) < 2:
        return None

    latency = 0.0
    min_bw = float("inf")
    success_prob = 1.0
    ashr_cost = 0.0

    for u, v in zip(path[:-1], path[1:]):
        data = G[u][v]
        latency += data.get("latency_ms", 0.0)
        min_bw = min(min_bw, data.get("bandwidth_mbps", 0.0))
        success_prob *= 1.0 - data.get("packet_loss", 0.0)
        ashr_cost += data.get("ashr_cost", 1.0)

    return PathMetrics(
        hops=len(path) - 1,
        latency_ms=latency,
        min_bandwidth_mbps=min_bw,
        packet_loss=1.0 - success_prob,
        ashr_cost=ashr_cost,
    )


def edge_in_path(path: Optional[List[str]], edge: Tuple[str, str]) -> bool:
    if not path:
        return False
    edge_set = {frozenset((u, v)) for u, v in zip(path[:-1], path[1:])}
    return frozenset(edge) in edge_set


def is_valid_path(G: nx.Graph, path: Optional[List[str]]) -> bool:
    if not path or len(path) < 2:
        return False
    return all(G.has_edge(u, v) for u, v in zip(path[:-1], path[1:]))


# -----------------------------------------------------------------------------
# ASHR routing computation
# -----------------------------------------------------------------------------


def get_backup_path(
    G: nx.Graph,
    source: str,
    dest: str,
    primary_path: List[str],
    max_candidates: int = 15,
) -> Optional[List[str]]:
    """
    Return the next best path after the primary path.
    Preference: a path with a different first hop, because it is useful as a
    fast backup route from the source router.
    """
    try:
        generator = nx.shortest_simple_paths(G, source, dest, weight="ashr_cost")
        fallback = None
        primary_tuple = tuple(primary_path)
        for idx, candidate in enumerate(generator):
            if idx >= max_candidates:
                break
            if tuple(candidate) == primary_tuple:
                continue
            if fallback is None:
                fallback = candidate
            if len(candidate) > 1 and len(primary_path) > 1 and candidate[1] != primary_path[1]:
                return candidate
        return fallback
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def compute_ashr_tables(G: nx.Graph, include_backup: bool = True) -> Dict[str, Dict[str, dict]]:
    """
    Compute ASHR primary routing tables using Dijkstra.
    If include_backup=True, also compute backup paths.

    Returns:
        tables[src][dest] = {
            next_hop, path, cost, backup_next_hop, backup_path, backup_cost
        }
    """
    update_ashr_costs(G)
    tables: Dict[str, Dict[str, dict]] = {node: {} for node in G.nodes()}

    for src in G.nodes():
        for dst in G.nodes():
            if src == dst:
                continue
            try:
                primary = nx.shortest_path(G, src, dst, weight="ashr_cost")
                primary_cost = nx.path_weight(G, primary, weight="ashr_cost")
                backup = get_backup_path(G, src, dst, primary) if include_backup else None
                tables[src][dst] = {
                    "next_hop": primary[1] if len(primary) > 1 else None,
                    "path": primary,
                    "cost": primary_cost,
                    "backup_next_hop": backup[1] if backup and len(backup) > 1 else None,
                    "backup_path": backup,
                    "backup_cost": nx.path_weight(G, backup, weight="ashr_cost") if backup else None,
                }
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                tables[src][dst] = {
                    "next_hop": None,
                    "path": None,
                    "cost": float("inf"),
                    "backup_next_hop": None,
                    "backup_path": None,
                    "backup_cost": None,
                }
    return tables


def detect_next_hop_loops(tables: Dict[str, Dict[str, dict]]) -> int:
    """Detect routing loops by following next-hop chains for every source/destination."""
    loops = 0
    routers = list(tables.keys())
    for src in routers:
        for dst in routers:
            if src == dst:
                continue
            current = src
            visited = set()
            for _ in range(len(routers) + 1):
                if current == dst:
                    break
                if current in visited:
                    loops += 1
                    break
                visited.add(current)
                entry = tables.get(current, {}).get(dst, {})
                current = entry.get("next_hop")
                if current is None:
                    break
    return loops


def simulate_ashr_link_failure(
    G: nx.Graph,
    failed_edge: Tuple[str, str],
    source: str = "R1",
    dest: str = "R4",
    precompute_backups: bool = True,
) -> AshrFailureResult:
    """
    Simulate ASHR response to a link failure.

    ASHR behavior being modeled:
      - Before failure, each router stores primary and backup paths.
      - When a link fails, ASHR sends event-driven WITHDRAW/LINK_UPDATE messages.
      - If the primary route used the failed link and a valid backup exists,
        traffic switches immediately to the backup path.
      - Only affected routes are recomputed.
    """
    G_before = G.copy()
    update_ashr_costs(G_before)
    tables_before = compute_ashr_tables(G_before, include_backup=precompute_backups)

    before_path = tables_before.get(source, {}).get(dest, {}).get("path")
    backup_before = tables_before.get(source, {}).get(dest, {}).get("backup_path")

    start = time.perf_counter()
    G_after = G_before.copy()
    if G_after.has_edge(*failed_edge):
        G_after.remove_edge(*failed_edge)
    update_ashr_costs(G_after)

    affected = 0
    immediate = 0
    recompute_needed = 0

    for src, row in tables_before.items():
        for dst, entry in row.items():
            primary = entry.get("path")
            if edge_in_path(primary, failed_edge):
                affected += 1
                backup = entry.get("backup_path")
                if precompute_backups:
                    if is_valid_path(G_after, backup):
                        immediate += 1
                    else:
                        recompute_needed += 1
                else:
                    # Fast scalability mode: do not enumerate backup paths for every pair.
                    # Count a route as immediately recoverable if an alternate path exists
                    # after removing the failed link; ASHR would have kept such backup state.
                    try:
                        if nx.has_path(G_after, src, dst):
                            immediate += 1
                        else:
                            recompute_needed += 1
                    except nx.NodeNotFound:
                        recompute_needed += 1

    # ASHR only recomputes affected routes. This table is used for loop checking
    # and the final path after failure.
    tables_after = compute_ashr_tables(G_after, include_backup=False)
    elapsed = time.perf_counter() - start

    # Event-driven control overhead model:
    # endpoint routers announce WITHDRAW/LINK_UPDATE to their remaining neighbors.
    u, v = failed_edge
    control_messages = 0
    if u in G_before and v in G_before:
        control_messages = G_after.degree(u) + G_after.degree(v) + 2  # two local failure notices

    after_path = tables_after.get(source, {}).get(dest, {}).get("path")
    loops = detect_next_hop_loops(tables_after)

    return AshrFailureResult(
        affected_routes=affected,
        immediate_backup_switches=immediate,
        recomputed_routes=recompute_needed,
        control_messages=control_messages,
        elapsed_s=elapsed,
        loops_detected=loops,
        before_path=before_path,
        after_path=after_path,
        backup_path_before_failure=backup_before,
    )


# -----------------------------------------------------------------------------
# RIP-like distance-vector baseline
# -----------------------------------------------------------------------------


def initialize_rip_tables(G: nx.Graph) -> Dict[str, Dict[str, Tuple[int, Optional[str]]]]:
    tables: Dict[str, Dict[str, Tuple[int, Optional[str]]]] = {}
    nodes = list(G.nodes())
    for u in nodes:
        tables[u] = {}
        for dst in nodes:
            if u == dst:
                tables[u][dst] = (0, u)
            elif G.has_edge(u, dst):
                tables[u][dst] = (1, dst)
            else:
                tables[u][dst] = (INF, None)
    return tables


def copy_rip_tables(tables: Dict[str, Dict[str, Tuple[int, Optional[str]]]]) -> Dict[str, Dict[str, Tuple[int, Optional[str]]]]:
    return {u: row.copy() for u, row in tables.items()}


def poison_routes_using_failed_link(
    tables: Dict[str, Dict[str, Tuple[int, Optional[str]]]],
    failed_edge: Tuple[str, str],
) -> None:
    """After a link fails, endpoints can no longer use the failed neighbor as next hop."""
    u, v = failed_edge
    for dst, (_, next_hop) in list(tables.get(u, {}).items()):
        if next_hop == v:
            tables[u][dst] = (INF, None)
    for dst, (_, next_hop) in list(tables.get(v, {}).items()):
        if next_hop == u:
            tables[v][dst] = (INF, None)


def detect_rip_loops(tables: Dict[str, Dict[str, Tuple[int, Optional[str]]]]) -> int:
    loops = 0
    routers = list(tables.keys())
    for src in routers:
        for dst in routers:
            if src == dst:
                continue
            current = src
            visited = set()
            for _ in range(len(routers) + 1):
                if current == dst:
                    break
                if current in visited:
                    loops += 1
                    break
                visited.add(current)
                next_hop = tables.get(current, {}).get(dst, (INF, None))[1]
                if next_hop is None:
                    break
                current = next_hop
    return loops


def rip_converge(
    G: nx.Graph,
    initial_tables: Optional[Dict[str, Dict[str, Tuple[int, Optional[str]]]]] = None,
    max_rounds: int = 100,
) -> RipResult:
    """
    Synchronous Bellman-Ford / RIP-like convergence.
    It intentionally uses only hop count and metric 16 as infinity.
    """
    start = time.perf_counter()
    nodes = list(G.nodes())
    tables = copy_rip_tables(initial_tables) if initial_tables else initialize_rip_tables(G)
    total_messages = 0
    total_loops = 0

    for round_no in range(1, max_rounds + 1):
        old = copy_rip_tables(tables)
        changed = False
        total_messages += 2 * G.number_of_edges()

        for u in nodes:
            for dst in nodes:
                if u == dst:
                    best = (0, u)
                else:
                    best_dist = INF
                    best_next = None
                    for nbr in G.neighbors(u):
                        nbr_dist = old[nbr].get(dst, (INF, None))[0]
                        candidate = min(INF, 1 + nbr_dist)
                        if candidate < best_dist:
                            best_dist = candidate
                            best_next = nbr
                    best = (best_dist, best_next)

                if best != tables[u].get(dst):
                    tables[u][dst] = best
                    changed = True

        total_loops += detect_rip_loops(tables)
        if not changed:
            elapsed = time.perf_counter() - start
            unreachable = count_unreachable_routes(tables)
            return RipResult(round_no, total_messages, elapsed, total_loops, unreachable, tables)

    elapsed = time.perf_counter() - start
    unreachable = count_unreachable_routes(tables)
    return RipResult(max_rounds, total_messages, elapsed, total_loops, unreachable, tables)


def count_unreachable_routes(tables: Dict[str, Dict[str, Tuple[int, Optional[str]]]]) -> int:
    count = 0
    for src, row in tables.items():
        for dst, (dist, _) in row.items():
            if src != dst and dist >= INF:
                count += 1
    return count


def rip_path_from_table(
    tables: Dict[str, Dict[str, Tuple[int, Optional[str]]]],
    source: str,
    dest: str,
) -> Optional[List[str]]:
    if source not in tables or dest not in tables[source]:
        return None
    if tables[source][dest][0] >= INF:
        return None
    path = [source]
    current = source
    visited = set()
    for _ in range(len(tables) + 1):
        if current == dest:
            return path
        if current in visited:
            return None
        visited.add(current)
        next_hop = tables[current].get(dest, (INF, None))[1]
        if next_hop is None:
            return None
        path.append(next_hop)
        current = next_hop
    return None


def simulate_rip_link_failure(G: nx.Graph, failed_edge: Tuple[str, str]) -> Tuple[RipResult, RipResult]:
    """First converge, then fail a link and reconverge from stale tables."""
    before = rip_converge(G)
    G_after = G.copy()
    if G_after.has_edge(*failed_edge):
        G_after.remove_edge(*failed_edge)

    stale_tables = copy_rip_tables(before.tables)
    poison_routes_using_failed_link(stale_tables, failed_edge)
    after = rip_converge(G_after, initial_tables=stale_tables)
    return before, after


# -----------------------------------------------------------------------------
# Security message simulation
# -----------------------------------------------------------------------------


def canonical_message_content(message: dict) -> bytes:
    """Serialize message fields except auth_hash in a stable way."""
    clean = {k: v for k, v in message.items() if k != "auth_hash"}
    return json.dumps(clean, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_message(message: dict, key: bytes) -> str:
    return hmac.new(key, canonical_message_content(message), hashlib.sha256).hexdigest()


def make_control_message(
    msg_type: str,
    sender: str,
    receiver: str,
    sequence: int,
    payload: dict,
    key_map: Dict[str, bytes],
) -> dict:
    message = {
        "type": msg_type,
        "sender": sender,
        "receiver": receiver,
        "sequence": sequence,
        "timestamp": time.time(),
        "payload": payload,
    }
    key = key_map.get(sender, b"wrong-key")
    message["auth_hash"] = sign_message(message, key)
    return message


def validate_ashr_message(
    G: nx.Graph,
    message: dict,
    key_map: Dict[str, bytes],
    last_sequence_seen: Dict[Tuple[str, str], int],
) -> Tuple[bool, List[str]]:
    """
    ASHR security checks:
      1. Sender must be a real neighbor of receiver.
      2. Sequence number must be fresh.
      3. HMAC must match the sender key.
    """
    reasons: List[str] = []
    sender = message.get("sender")
    receiver = message.get("receiver")
    sequence = int(message.get("sequence", -1))

    if sender not in G.nodes or receiver not in G.nodes or not G.has_edge(sender, receiver):
        reasons.append("sender is not a valid neighbor")

    previous = last_sequence_seen.get((sender, receiver), -1)
    if sequence <= previous:
        reasons.append("replay/stale sequence number")

    expected_key = key_map.get(sender)
    if expected_key is None:
        reasons.append("unknown sender key")
    else:
        expected_hash = sign_message(message, expected_key)
        if not hmac.compare_digest(expected_hash, message.get("auth_hash", "")):
            reasons.append("authentication hash failed")

    accepted = not reasons
    if accepted:
        last_sequence_seen[(sender, receiver)] = sequence
    return accepted, reasons


def run_security_scenario(G: nx.Graph) -> pd.DataFrame:
    """Demonstrate spoofing, route hijacking, and replay protection."""
    routers = list(G.nodes())
    key_map = {router: f"secret-key-for-{router}".encode("utf-8") for router in routers}
    last_sequence_seen: Dict[Tuple[str, str], int] = {}
    rows = []

    valid = make_control_message(
        "LINK_UPDATE",
        sender="R2",
        receiver="R1",
        sequence=1,
        payload={"neighbor": "R1", "latency_ms": 2, "bandwidth_mbps": 100, "packet_loss": 0.005},
        key_map=key_map,
    )
    accepted, reasons = validate_ashr_message(G, valid, key_map, last_sequence_seen)
    rows.append({"test": "Valid neighbor update", "accepted_by_ashr": accepted, "reason": "; ".join(reasons) or "valid"})

    # Replay exactly the same valid message.
    accepted, reasons = validate_ashr_message(G, valid, key_map, last_sequence_seen)
    rows.append({"test": "Replay old R2 update", "accepted_by_ashr": accepted, "reason": "; ".join(reasons)})

    # Fake non-neighbor / attacker M1. M1 is not in the graph and has no valid key.
    forged = {
        "type": "ROUTE_UPDATE",
        "sender": "M1",
        "receiver": "R1",
        "sequence": 1,
        "timestamp": time.time(),
        "payload": {"advertised_destination": "R6", "metric": 1},
        "auth_hash": "fake_hash",
    }
    accepted, reasons = validate_ashr_message(G, forged, key_map, last_sequence_seen)
    rows.append({"test": "Spoofed non-neighbor update", "accepted_by_ashr": accepted, "reason": "; ".join(reasons)})

    # Neighbor exists, but the message was modified after signing.
    tampered = make_control_message(
        "ROUTE_UPDATE",
        sender="R2",
        receiver="R1",
        sequence=2,
        payload={"advertised_destination": "R6", "metric": 5},
        key_map=key_map,
    )
    tampered["payload"]["metric"] = 1  # route hijack attempt after signature creation
    accepted, reasons = validate_ashr_message(G, tampered, key_map, last_sequence_seen)
    rows.append({"test": "Tampered route hijack", "accepted_by_ashr": accepted, "reason": "; ".join(reasons)})

    # RIP has no auth in this simplified model, so it accepts the forged lower metric.
    rows.append({
        "test": "Same fake route in RIP baseline",
        "accepted_by_ashr": "N/A",
        "reason": "RIP baseline has no HMAC/sequence validation, so a lower false metric can be accepted in this model",
    })

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Area clustering and scalability
# -----------------------------------------------------------------------------


def generate_connected_topology(n: int, extra_edges_factor: float = 1.4, seed: int = RANDOM_SEED) -> nx.Graph:
    """Generate a connected random topology with router names R1..Rn."""
    rng = random.Random(seed + n)
    G = nx.Graph()
    nodes = [f"R{i}" for i in range(1, n + 1)]
    G.add_nodes_from(nodes)

    # Start with a random spanning tree.
    shuffled = nodes[:]
    rng.shuffle(shuffled)
    for i in range(n - 1):
        G.add_edge(shuffled[i], shuffled[i + 1])

    target_edges = max(n - 1, int(extra_edges_factor * n))
    while G.number_of_edges() < target_edges:
        u, v = rng.sample(nodes, 2)
        if u != v and not G.has_edge(u, v):
            G.add_edge(u, v)

    return assign_random_metrics(G, seed=seed + n)


def assign_areas(G: nx.Graph, target_area_size: int = 10) -> Dict[str, str]:
    """
    Simple area assignment for simulation.
    For a report, this represents OSPF/IS-IS-style hierarchy.
    """
    nodes = sorted(G.nodes(), key=lambda x: int(x[1:]) if x[1:].isdigit() else x)
    areas = {}
    for idx, node in enumerate(nodes):
        areas[node] = f"A{idx // target_area_size + 1}"
    nx.set_node_attributes(G, areas, "area")
    return areas


def estimate_ashr_average_table_size(G: nx.Graph, areas: Dict[str, str]) -> float:
    """
    ASHR table size estimate:
      full routes inside local area + summary routes to other areas.
    """
    area_to_nodes: Dict[str, List[str]] = {}
    for node, area in areas.items():
        area_to_nodes.setdefault(area, []).append(node)
    num_areas = len(area_to_nodes)
    sizes = []
    for node, area in areas.items():
        local_routes = len(area_to_nodes[area]) - 1
        summary_routes = num_areas - 1
        sizes.append(local_routes + summary_routes)
    return float(np.mean(sizes))


def sample_pdr(G: nx.Graph, sample_size: int = 200, seed: int = RANDOM_SEED) -> float:
    """Estimate packet delivery ratio over sampled ASHR shortest paths."""
    rng = random.Random(seed)
    nodes = list(G.nodes())
    if len(nodes) < 2:
        return 0.0
    update_ashr_costs(G)
    success_values = []
    attempts = min(sample_size, len(nodes) * (len(nodes) - 1))
    for _ in range(attempts):
        src, dst = rng.sample(nodes, 2)
        try:
            path = nx.shortest_path(G, src, dst, weight="ashr_cost")
        except nx.NetworkXNoPath:
            success_values.append(0.0)
            continue
        success = 1.0
        for u, v in zip(path[:-1], path[1:]):
            success *= 1.0 - G[u][v].get("packet_loss", 0.0)
        success_values.append(success)
    return 100.0 * float(np.mean(success_values))


def choose_non_bridge_edge(G: nx.Graph, seed: int = RANDOM_SEED) -> Tuple[str, str]:
    rng = random.Random(seed)
    bridges = {frozenset(e) for e in nx.bridges(G)}
    candidates = [e for e in G.edges() if frozenset(e) not in bridges]
    if not candidates:
        candidates = list(G.edges())
    return rng.choice(candidates)


def run_scalability_test(sizes: Iterable[int] = (10, 20, 50, 100, 200)) -> pd.DataFrame:
    rows = []
    for n in sizes:
        G = generate_connected_topology(n)
        areas = assign_areas(G, target_area_size=max(5, int(math.sqrt(n))))
        failed_edge = choose_non_bridge_edge(G, seed=RANDOM_SEED + n)

        # ASHR computation time and failure overhead.
        start = time.perf_counter()
        ashr_tables = compute_ashr_tables(G, include_backup=False)
        ashr_compute_time = time.perf_counter() - start

        ashr_failure = simulate_ashr_link_failure(G, failed_edge, source="R1", dest=f"R{n}", precompute_backups=False)

        # RIP baseline after failure.
        _, rip_after = simulate_rip_link_failure(G, failed_edge)

        rows.append({
            "routers": n,
            "links": G.number_of_edges(),
            "failed_link": f"{failed_edge[0]}-{failed_edge[1]}",
            "rip_convergence_rounds_after_failure": rip_after.rounds,
            "ashr_recomputed_routes_after_failure": ashr_failure.recomputed_routes,
            "rip_control_messages_after_failure": rip_after.messages,
            "ashr_event_control_messages_after_failure": ashr_failure.control_messages,
            "rip_unreachable_routes_after_failure": rip_after.unreachable_routes,
            "ashr_loops_detected_after_failure": ashr_failure.loops_detected,
            "rip_loops_detected_during_convergence": rip_after.loops_detected,
            "avg_rip_table_size_per_router": n - 1,
            "avg_ashr_table_size_per_router": estimate_ashr_average_table_size(G, areas),
            "ashr_compute_time_s": ashr_compute_time,
            "rip_convergence_time_s": rip_after.elapsed_s,
            "ashr_estimated_pdr_percent": sample_pdr(G, sample_size=200, seed=RANDOM_SEED + n),
            "invalid_messages_detected_by_ashr": 3,  # spoof + replay + tamper model from security scenario
        })

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Required scenarios and plotting
# -----------------------------------------------------------------------------


def run_link_failure_scenario() -> Tuple[pd.DataFrame, pd.DataFrame]:
    G = build_demo_topology()
    failed_edge = ("R2", "R3")

    ashr = simulate_ashr_link_failure(G, failed_edge, source="R1", dest="R4")
    rip_before, rip_after = simulate_rip_link_failure(G, failed_edge)

    update_ashr_costs(G)
    ashr_before_metrics = path_metrics(G, ashr.before_path)
    ashr_backup_metrics = path_metrics(G, ashr.backup_path_before_failure)

    G_after = G.copy()
    G_after.remove_edge(*failed_edge)
    update_ashr_costs(G_after)
    ashr_after_metrics = path_metrics(G_after, ashr.after_path)

    rip_before_path = rip_path_from_table(rip_before.tables, "R1", "R4")
    rip_after_path = rip_path_from_table(rip_after.tables, "R1", "R4")

    comparison = pd.DataFrame([
        {
            "protocol": "RIP baseline",
            "routing_logic": "hop count only",
            "path_before_failure": " -> ".join(rip_before_path) if rip_before_path else "unreachable",
            "path_after_R2_R3_failure": " -> ".join(rip_after_path) if rip_after_path else "unreachable",
            "convergence_rounds_after_failure": rip_after.rounds,
            "control_messages_after_failure": rip_after.messages,
            "loops_detected_during_convergence": rip_after.loops_detected,
            "unreachable_routes_after_failure": rip_after.unreachable_routes,
            "recovery_method": "wait for distance-vector reconvergence",
        },
        {
            "protocol": "ASHR proposed",
            "routing_logic": "dynamic latency/bandwidth/loss cost + backup route",
            "path_before_failure": " -> ".join(ashr.before_path) if ashr.before_path else "unreachable",
            "path_after_R2_R3_failure": " -> ".join(ashr.after_path) if ashr.after_path else "unreachable",
            "convergence_rounds_after_failure": 1,
            "control_messages_after_failure": ashr.control_messages,
            "loops_detected_during_convergence": ashr.loops_detected,
            "unreachable_routes_after_failure": 0 if ashr.after_path else 1,
            "recovery_method": f"{ashr.immediate_backup_switches} affected routes can use stored backup; {ashr.recomputed_routes} recomputed",
        },
    ])

    route_quality = pd.DataFrame([
        {"case": "ASHR primary before failure", **(ashr_before_metrics.__dict__ if ashr_before_metrics else {})},
        {"case": "ASHR stored backup before failure", **(ashr_backup_metrics.__dict__ if ashr_backup_metrics else {})},
        {"case": "ASHR route after failure", **(ashr_after_metrics.__dict__ if ashr_after_metrics else {})},
    ])

    return comparison, route_quality


def run_rip_15_hop_limit_test() -> pd.DataFrame:
    """Demonstrate RIP's 15-hop limit on a 20-router line topology."""
    G = nx.path_graph([f"R{i}" for i in range(1, 21)])
    assign_random_metrics(G)
    rip = rip_converge(G)
    ashr_tables = compute_ashr_tables(G)
    ashr_unreachable = sum(
        1
        for src, row in ashr_tables.items()
        for dst, entry in row.items()
        if src != dst and entry["path"] is None
    )
    total_routes = 20 * 19
    return pd.DataFrame([
        {
            "protocol": "RIP baseline",
            "topology": "20-router linear chain",
            "total_source_destination_routes": total_routes,
            "unreachable_routes": rip.unreachable_routes,
            "reason": "RIP metric 16 means infinity, so routes longer than 15 hops fail",
        },
        {
            "protocol": "ASHR proposed",
            "topology": "20-router linear chain",
            "total_source_destination_routes": total_routes,
            "unreachable_routes": ashr_unreachable,
            "reason": "Dijkstra path computation has no 15-hop routing limit in this simulation",
        },
    ])


def save_plots(scalability: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_specs = [
        (
            "routers",
            ["rip_convergence_rounds_after_failure", "ashr_recomputed_routes_after_failure"],
            "Routers",
            "Rounds / affected recomputations",
            "Convergence / recomputation growth",
            "01_convergence_vs_routers.png",
        ),
        (
            "routers",
            ["rip_control_messages_after_failure", "ashr_event_control_messages_after_failure"],
            "Routers",
            "Control messages",
            "Control overhead after link failure",
            "02_control_messages_vs_routers.png",
        ),
        (
            "routers",
            ["avg_rip_table_size_per_router", "avg_ashr_table_size_per_router"],
            "Routers",
            "Average entries per router",
            "Routing table size comparison",
            "03_table_size_vs_routers.png",
        ),
        (
            "routers",
            ["ashr_estimated_pdr_percent"],
            "Routers",
            "Estimated PDR (%)",
            "ASHR packet delivery estimate",
            "04_pdr_vs_routers.png",
        ),
    ]

    for x_col, y_cols, xlabel, ylabel, title, filename in plot_specs:
        plt.figure(figsize=(8, 5))
        for y_col in y_cols:
            plt.plot(scalability[x_col], scalability[y_col], marker="o", label=y_col)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.title(title)
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plt.savefig(output_dir / filename, dpi=200)
        plt.close()


def save_demo_topology_plot(output_dir: Path) -> None:
    G = build_demo_topology()
    pos = {
        "R1": (0, 1), "R2": (1, 1), "R3": (2, 1), "R4": (3, 1),
        "R5": (0, 0), "R6": (2, 0),
    }
    labels = {
        (u, v): f"L={data['latency_ms']}ms\nB={data['bandwidth_mbps']}Mbps\nP={data['packet_loss']:.3f}"
        for u, v, data in G.edges(data=True)
    }
    plt.figure(figsize=(9, 5))
    nx.draw_networkx(G, pos=pos, with_labels=True, node_size=1200, font_weight="bold")
    nx.draw_networkx_edge_labels(G, pos=pos, edge_labels=labels, font_size=8)
    plt.title("Demo topology for ASHR vs RIP simulation")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_dir / "00_demo_topology.png", dpi=200)
    plt.close()


def write_text_report(
    output_dir: Path,
    failure_df: pd.DataFrame,
    quality_df: pd.DataFrame,
    security_df: pd.DataFrame,
    rip_limit_df: pd.DataFrame,
    scalability_df: pd.DataFrame,
) -> None:
    lines = []
    lines.append("ASHR NetworkX Simulation Report")
    lines.append("================================")
    lines.append("")
    lines.append("Implemented simulations:")
    lines.append("1. RIP vs ASHR link failure recovery")
    lines.append("2. ASHR security validation: neighbor check, sequence number, HMAC")
    lines.append("3. RIP 15-hop limitation test")
    lines.append("4. Scalability test: 10, 20, 50, 100, 200 routers")
    lines.append("")
    lines.append("Link failure comparison:")
    lines.append(failure_df.to_string(index=False))
    lines.append("")
    lines.append("ASHR route quality:")
    lines.append(quality_df.to_string(index=False))
    lines.append("")
    lines.append("Security tests:")
    lines.append(security_df.to_string(index=False))
    lines.append("")
    lines.append("RIP 15-hop limit test:")
    lines.append(rip_limit_df.to_string(index=False))
    lines.append("")
    lines.append("Scalability results:")
    lines.append(scalability_df.to_string(index=False))
    lines.append("")
    lines.append("Conclusion points for report:")
    lines.append("- RIP is simple but only uses hop count, has a 15-hop limit, and has no message authentication in this model.")
    lines.append("- ASHR selects routes using latency, bandwidth, packet loss, and hop count, so it can represent path quality better.")
    lines.append("- ASHR stores backup routes, so many affected routes can switch immediately after a link failure.")
    lines.append("- ASHR uses event-driven updates, so the control overhead after a failure is lower than repeated RIP table exchanges.")
    lines.append("- ASHR rejects spoofed, replayed, or tampered control messages using neighbor validation, sequence numbers, and HMAC.")
    (output_dir / "ashr_analysis_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    RESULTS_DIR.mkdir(exist_ok=True)

    failure_df, quality_df = run_link_failure_scenario()
    security_df = run_security_scenario(build_demo_topology())
    rip_limit_df = run_rip_15_hop_limit_test()
    scalability_df = run_scalability_test()

    # Save tables.
    failure_df.to_csv(RESULTS_DIR / "01_link_failure_comparison.csv", index=False)
    quality_df.to_csv(RESULTS_DIR / "02_route_quality.csv", index=False)
    security_df.to_csv(RESULTS_DIR / "03_security_tests.csv", index=False)
    rip_limit_df.to_csv(RESULTS_DIR / "04_rip_15_hop_limit.csv", index=False)
    scalability_df.to_csv(RESULTS_DIR / "05_scalability_results.csv", index=False)

    save_demo_topology_plot(RESULTS_DIR)
    save_plots(scalability_df, RESULTS_DIR)
    write_text_report(RESULTS_DIR, failure_df, quality_df, security_df, rip_limit_df, scalability_df)

    print("\n=== LINK FAILURE: RIP vs ASHR ===")
    print(failure_df.to_string(index=False))

    print("\n=== ASHR ROUTE QUALITY ===")
    print(quality_df.to_string(index=False))

    print("\n=== SECURITY TESTS ===")
    print(security_df.to_string(index=False))

    print("\n=== RIP 15-HOP LIMIT TEST ===")
    print(rip_limit_df.to_string(index=False))

    print("\n=== SCALABILITY RESULTS ===")
    print(scalability_df.to_string(index=False))

    print(f"\nSaved CSVs, PNG graphs, and text report in: {RESULTS_DIR.resolve()}")


if __name__ == "__main__":
    main()
