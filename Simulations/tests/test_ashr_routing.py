from src.ashr_protocol import ASHRProtocol
from src.topology import create_hierarchical_topology


def test_ashr_finds_valid_r1_to_r10_path():
    ashr = ASHRProtocol(create_hierarchical_topology())
    route = ashr.get_route("R1", "R10")

    assert route["path"][0] == "R1"
    assert route["path"][-1] == "R10"
    assert route["next_hop"] == route["path"][1]
    assert route["cost"] > 0


def test_ashr_computes_backup_path_where_redundancy_exists():
    ashr = ASHRProtocol(create_hierarchical_topology())
    primary = ashr.get_route("R1", "R10")
    backup = ashr.get_backup_route("R1", "R10")

    assert backup["path"][0] == "R1"
    assert backup["path"][-1] == "R10"
    assert backup["next_hop"] is not None
    assert backup["path"][1] != primary["path"][1]


def test_ashr_uses_backup_after_primary_link_failure():
    ashr = ASHRProtocol(create_hierarchical_topology())
    result = ashr.apply_link_failure("R3", "ABR1", "R1", "R10")

    assert result["affected_primary"]
    assert result["used_backup"]
    assert result["new_path"][0] == "R1"
    assert result["new_path"][-1] == "R10"
