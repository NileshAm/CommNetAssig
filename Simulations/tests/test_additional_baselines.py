from src.bgp_baseline import BGPBaseline
from src.isis_baseline import ISISBaseline
from src.ospf_baseline import OSPFBaseline
from src.topology import create_hierarchical_topology


def test_ospf_style_baseline_finds_r1_to_r10_path():
    ospf = OSPFBaseline(create_hierarchical_topology())
    path = ospf.get_path("R1", "R10")

    assert path[0] == "R1"
    assert path[-1] == "R10"
    assert ospf.get_cost("R1", "R10") > 0


def test_isis_style_baseline_ignores_dynamic_congestion_metric():
    isis = ISISBaseline(create_hierarchical_topology())
    before_path = isis.get_path("R1", "R10")
    before_cost = isis.get_cost("R1", "R10")

    isis.update_link_metrics("ABR1", "ABR2", congestion=0.95, latency_ms=55, packet_loss=0.015)

    assert isis.get_path("R1", "R10") == before_path
    assert isis.get_cost("R1", "R10") == before_cost


def test_bgp_style_baseline_accepts_fake_path_vector_update():
    bgp = BGPBaseline(create_hierarchical_topology())

    accepted = bgp.apply_fake_low_cost_advertisement("R2", "R1", "R10")

    assert accepted
    assert bgp.get_cost("R1", "R10") == 1
