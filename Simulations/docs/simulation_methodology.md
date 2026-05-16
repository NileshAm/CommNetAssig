# Simulation Methodology

## Tool Justification

This project uses Python 3.10+ with:

- `networkx` for graph topology and shortest-path algorithms.
- `matplotlib` for output graphs.
- `pandas` for CSV result tables.
- `pytest` for automated tests.

Python is suitable because the assignment focuses on routing-protocol behavior and quantitative comparison, not real router deployment. External network simulators such as NS3, OMNeT++, and Mininet are not required.

## Topology

The topology is hierarchical:

- Area 1: `R1`, `R2`, `R3`, `R4`, `R5`, `R6`
- Backbone Area 0: `ABR1`, `ABR2`
- Area 2: `R7`, `R8`, `R9`, `R10`

Each link stores:

- `latency_ms`
- `bandwidth_mbps`
- `packet_loss`
- `congestion`
- `error_rate`
- `failed`
- `hop_cost`

The topology includes redundant R1-to-R10 corridors:

- Primary corridor: `R1 -> R2 -> R3 -> ABR1 -> ABR2 -> R8 -> R10`
- Backup corridor: `R1 -> R4 -> R5 -> R6 -> ABR2 -> R8 -> R10`

## Baseline Protocols

The project now benchmarks ASHR against four simplified educational baselines.

RIP-style distance vector:

- Hop-count metric only.
- Periodic full-table update rounds.
- Infinity value of 16.
- No authentication.
- Can recompute after link failure.
- Can accept a fake low-cost route advertisement.

OSPF-style link state:

- Dijkstra shortest path.
- Static bandwidth-derived link cost.
- Faster recomputation than RIP after link failure.
- No ASHR adaptive congestion metric.
- No ASHR HMAC, replay protection, or fake-cost rejection in this baseline.

IS-IS-style hierarchical link state:

- Dijkstra shortest path.
- Configured static link metric.
- Models area summaries with lower flooding overhead than a flat link-state baseline.
- Does not adapt to transient congestion.

BGP-style path vector:

- Chooses by AS-path length in the simplified topology.
- Models slower withdrawal and re-advertisement after failure.
- Ignores intradomain latency, loss, bandwidth, and congestion.

These baselines are intentionally educational rather than complete RFC implementations.

## ASHR Protocol Simulation

ASHR uses:

- HELLO-style neighbor discovery.
- ASHR-LSA messages.
- FAILURE_ALERT messages.
- AREA_SUMMARY messages.
- Link-state database rebuilds after significant events.
- Dijkstra shortest path using normalized ASHR cost.
- Primary and backup next-hop tables.
- HMAC and sequence-number security validation.

## Scenarios

Scenario A: Normal routing

- Compute R1-to-R10 paths using RIP, OSPF-style, IS-IS-style, BGP-style, and ASHR.
- Compare protocol-specific path costs.

Scenario B: Link failure

- Fail link `R3-ABR1`.
- Measure RIP convergence rounds.
- Measure OSPF-style, IS-IS-style, and BGP-style convergence time.
- Measure ASHR backup-route recovery time.
- Estimate packet loss using 100 packets per time unit.

Scenario C: Congestion change

- Increase congestion on `ABR1-ABR2`.
- Model congestion side effects by increasing latency, packet loss, and link error rate on the same link.
- Compare baseline path stability with ASHR adaptive recomputation.

Scenario D: Fake routing update attack

- Advertise fake cost 0 to R10.
- Check whether each protocol accepts the update.

Scenario E: Replay attack

- Resend an old ASHR LSA.
- Check sequence-number replay protection.

Scalability benchmark: Convergence time vs nodes

- Generate deterministic hierarchical topologies with 12, 20, 40, and 60 routers.
- Compute the ASHR primary path between the generated source and destination.
- Fail the primary first-hop link.
- Measure or model the recovery/convergence time for RIP, OSPF-style, IS-IS-style, BGP-style, and ASHR.
- Save the result in `outputs/scalability_convergence_vs_nodes.csv` and plot it in `outputs/scalability_convergence_vs_nodes.png`.

## Metrics Measured

Convergence time:

- RIP: number of update rounds until no routing table changes.
- OSPF-style, IS-IS-style, and BGP-style: modeled convergence time units.
- ASHR: recovery time units, where immediate backup switching is 0.

Packet loss estimate:

```text
estimated_packet_loss = convergence_or_recovery_time * 100
```

Control-message overhead:

- RIP: periodic update messages per convergence round.
- ASHR: event-driven HELLO, LSA, summary, and failure-alert messages.

Path cost:

- RIP: hop count.
- OSPF-style: static bandwidth-derived path cost.
- IS-IS-style: configured static path metric.
- BGP-style: AS-path length.
- ASHR: sum of normalized adaptive link costs, including hop cost, latency, inverse bandwidth, packet loss, congestion, and error rate.

Attack accepted/rejected:

- `1` means the attack was accepted.
- `0` means the attack was rejected.

Scalability convergence:

- RIP uses actual distance-vector update rounds from the simulator.
- OSPF-style uses a deterministic flood plus SPF work model based on node and edge count.
- IS-IS-style uses a deterministic hierarchical SPF work model based on node and edge count.
- BGP-style uses a deterministic path-vector withdrawal and re-advertisement model.
- ASHR reports immediate backup next-hop recovery time, while the CSV separately records control-plane rebuild units.

## Interpreting Results

Lower convergence/recovery time is better because it means less disruption after failure.

Lower packet loss estimate is better because the model assumes traffic is lost while the protocol has not recovered.

Lower control overhead is better when routing quality is preserved, because fewer control messages consume less network capacity.

Lower ASHR path cost means the selected path is better under the normalized composite metric. It should not be directly compared as the same physical unit as RIP hop count.

Security results should show the simplified baselines accepting fake low-cost route/path information and ASHR rejecting spoofed, fake-cost, and replayed messages.

The scalability graph should be interpreted as a protocol behavior model, not a CPU benchmarking graph. It shows how recovery/convergence behavior changes with topology size under the assumptions encoded in the simulator.
