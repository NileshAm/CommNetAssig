from src.rip_baseline import RIP_INFINITY, RIPBaseline
from src.topology import create_hierarchical_topology


def test_rip_converges_on_initial_topology():
    rip = RIPBaseline(create_hierarchical_topology())
    result = rip.run_until_converged(reset=True)
    path = rip.get_path("R1", "R10")

    assert result.converged
    assert result.rounds > 0
    assert path[0] == "R1"
    assert path[-1] == "R10"
    assert rip.get_distance("R1", "R10") < RIP_INFINITY
