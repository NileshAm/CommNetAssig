import pytest
import networkx as nx

from src.ashr_protocol import ASHRProtocol
from src.security import SecurityManager
from src.topology import create_hierarchical_topology


def test_single_router_topology():
    G = nx.Graph()
    G.add_node("R1", area_id=1, role="internal")

    ashr = ASHRProtocol(G)
    route = ashr.get_route("R1", "R1")

    assert route["path"] == ["R1"]
    assert route["cost"] == 0.0


def test_isolated_node_no_path():
    G = create_hierarchical_topology()
    # Add an isolated router with required attributes
    G.add_node("RX", area_id=3, role="internal")

    ashr = ASHRProtocol(G)
    route = ashr.get_route("R1", "RX")

    assert route["path"] == []
    assert route["cost"] == float("inf")


def test_all_links_failed_results_in_no_routes():
    G = create_hierarchical_topology()
    for u, v in list(G.edges()):
        G[u][v]["failed"] = True

    ashr = ASHRProtocol(G)
    route = ashr.get_route("R1", "R10")

    assert route["path"] == []
    assert route["cost"] == float("inf")


def test_message_loss_prevents_lsdb_population():
    G = create_hierarchical_topology()
    # Build trusted neighbor map but provide no shared keys to simulate
    # signing/auth failures (simulates dropped/invalid control messages)
    trusted = {n: set(G.neighbors(n)) for n in G.nodes()}
    sec = SecurityManager(trusted_neighbors=trusted, shared_keys={})

    ashr = ASHRProtocol(G, security=sec)

    # If authentication fails, not every router should have every origin's LSDB
    some_receiver = next(iter(ashr.router_states.keys()))
    lsdb_size = len(ashr.router_states[some_receiver].link_state_database)
    assert lsdb_size < len(G.nodes())


def test_node_removal_invalidates_updates():
    G = create_hierarchical_topology()
    ashr = ASHRProtocol(G)

    # Remove a node and ensure updates referencing removed node error
    G.remove_node("R5")
    with pytest.raises(ValueError):
        ashr.update_link_metrics("R5", "R6", congestion=0.9)
