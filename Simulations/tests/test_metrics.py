from src.metrics import MetricRanges, adaptive_link_cost, compute_metric_ranges, normalized_components
from src.topology import active_edges, create_hierarchical_topology


def test_metric_normalization_produces_bounded_values():
    graph = create_hierarchical_topology()
    ranges = compute_metric_ranges(graph)

    for _, _, data in active_edges(graph):
        components = normalized_components(data, ranges)
        assert all(0.0 <= value <= 1.0 for value in components.values())
        assert 0.0 <= adaptive_link_cost(data, ranges) <= 1.0


def test_higher_latency_increases_cost():
    ranges = MetricRanges(
        max_hop=1,
        min_latency=0,
        max_latency=100,
        min_inverse_bandwidth=1 / 1000,
        max_inverse_bandwidth=1 / 10,
        min_packet_loss=0,
        max_packet_loss=0.1,
        min_congestion=0,
        max_congestion=1,
    )
    base = {"hop_cost": 1, "latency_ms": 10, "bandwidth_mbps": 100, "packet_loss": 0.01, "congestion": 0.1}
    slower = dict(base, latency_ms=60)

    assert adaptive_link_cost(slower, ranges) > adaptive_link_cost(base, ranges)


def test_lower_bandwidth_increases_cost():
    ranges = MetricRanges(
        max_hop=1,
        min_latency=0,
        max_latency=100,
        min_inverse_bandwidth=1 / 1000,
        max_inverse_bandwidth=1 / 10,
        min_packet_loss=0,
        max_packet_loss=0.1,
        min_congestion=0,
        max_congestion=1,
    )
    high_bandwidth = {
        "hop_cost": 1,
        "latency_ms": 10,
        "bandwidth_mbps": 1000,
        "packet_loss": 0.01,
        "congestion": 0.1,
    }
    low_bandwidth = dict(high_bandwidth, bandwidth_mbps=10)

    assert adaptive_link_cost(low_bandwidth, ranges) > adaptive_link_cost(high_bandwidth, ranges)
