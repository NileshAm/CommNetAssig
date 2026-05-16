# ASHR Protocol Design

## Background and Motivation

Intradomain routing protocols must find efficient paths while reacting quickly to failures and preventing false routing information from influencing forwarding decisions. Classic protocols each solve part of this problem, but none is ideal for this assignment objective when considered alone.

ASHR, the Adaptive Secure Hierarchical Routing Protocol, is designed as a simulation-level routing protocol that combines hierarchy, adaptive metrics, event-driven updates, fast backup next hops, and authenticated routing messages.

## Limitations of Existing Protocol Families

RIP:

- Uses hop count only, so it ignores latency, bandwidth, packet loss, and congestion.
- Has a small infinity value of 16 hops.
- Converges by repeated update rounds, which can be slow after failures.
- The simplified educational baseline in this project has no authentication and accepts fake low-cost route advertisements.

OSPF and IS-IS:

- Provide link-state routing and hierarchy, but their common cost models do not directly combine normalized latency, bandwidth, loss, and congestion in the way ASHR does.
- Standard operation can still create control overhead if metrics fluctuate frequently, so ASHR adds an explicit metric damping threshold.
- In this project, the OSPF-style and IS-IS-style baselines are static-metric models. They recompute after failures but do not adapt to congestion changes.

BGP:

- Designed for interdomain policy routing rather than intradomain shortest-path engineering.
- Convergence and policy decisions are not suitable as the main mechanism for this local hierarchical network.
- In this project, the BGP-style baseline models path-vector routing by AS-path length and intentionally ignores intradomain link quality.

## ASHR Design Goals

- Improve route quality using normalized adaptive link metrics.
- Improve fault tolerance through precomputed backup next hops.
- Reduce unnecessary control traffic through event-driven updates and metric damping.
- Improve scalability through areas and area summary messages.
- Improve trust in routing updates through HMAC authentication, sequence numbers, TTL checks, replay protection, and neighbor validation.

## Architecture

ASHR divides the network into:

- Area 1: `R1` to `R6`
- Backbone Area 0: `ABR1`, `ABR2`
- Area 2: `R7` to `R10`

Routers maintain local neighbor state, a link-state database, primary routing entries, and backup routing entries. Area border routers model summary advertisements between non-backbone areas and the backbone.

## Adaptive Metric

For each link `(i, j)`, ASHR computes:

```text
Cij = 0.20H' + 0.30L' + 0.25B' + 0.15P' + 0.10Q'
```

Where:

- `H'`: normalized hop/link contribution.
- `L'`: normalized latency.
- `B'`: normalized inverse-bandwidth penalty, so lower bandwidth produces higher cost.
- `P'`: normalized packet-loss contribution.
- `Q'`: normalized congestion contribution.

The implementation normalizes each component before weighting. Raw latency, bandwidth, and packet-loss values are not added directly.

## Metric Damping

ASHR triggers a link-state update only when:

```text
abs(new_cost - old_cost) > theta
```

The default threshold is:

```text
theta = 0.15
```

This avoids unnecessary routing updates for small metric fluctuations.

## Control Message Formats

Every ASHR routing message contains:

```text
message_type
sender_router_id
area_id
sequence_number
ttl
body
auth_tag
```

Message types:

- `ASHR_LSA`: Carries link-state information and normalized costs.
- `FAILURE_ALERT`: Announces local link failure events.
- `AREA_SUMMARY`: Summarizes reachable routers by area.
- `HELLO`: Modeled as neighbor detection events in the simulator.

## State Stored at Routers

Each router stores:

- Router ID.
- Area ID.
- Neighbor table.
- HELLO-detected neighbor table.
- Sequence number counter.
- Link-state database.
- Primary next-hop routing table.
- Backup next-hop routing table.

## Routing Algorithm Pseudocode

```text
for each router:
    discover active neighbors using HELLO model
    originate authenticated ASHR_LSA
    install valid LSAs into the link-state database

for each source router S:
    for each destination router D:
        primary_path = Dijkstra(S, D, weight=ASHR_cost)
        first_hop = primary_path[1]
        remove edge (S, first_hop)
        backup_path = Dijkstra(S, D, weight=ASHR_cost)
        store primary next hop and backup next hop
```

Failure handling:

```text
on link failure:
    emit FAILURE_ALERT
    if failed link is on current primary path and valid backup exists:
        switch to backup next hop immediately
    rebuild LSDB using event-driven ASHR_LSA messages
    recompute primary and backup tables
```

Metric-change handling:

```text
on measured link attribute change:
    old_cost = ASHR_cost(old attributes)
    new_cost = ASHR_cost(new attributes)
    if abs(new_cost - old_cost) > theta:
        emit ASHR_LSA
        recompute affected shortest paths
    else:
        suppress update
```

## Security Design

ASHR security checks are implemented in `src/security.py`.

Checks:

- Trusted neighbor validation: unrecognized senders are rejected.
- HMAC-SHA256: message payloads are authenticated using preconfigured shared keys.
- Sequence numbers: stale or repeated sequence numbers are rejected.
- TTL validation: messages with invalid TTL values are rejected.
- Replay protection: a previously accepted message cannot be accepted again.
- Spoofed update rejection: untrusted router IDs fail validation.
- Fake low-cost route rejection: cost advertisements below the valid minimum are rejected.

## Scalability Design

ASHR uses hierarchy to reduce the amount of topology information that must be considered across the whole domain. Area border routers model `AREA_SUMMARY` messages that describe reachability between areas. In a larger implementation, internal routers would primarily track detailed topology inside their own area and summarized reachability outside it.

The event-driven update model also improves efficiency because ASHR does not periodically flood full tables like RIP. It sends updates when a failure occurs or when the metric damping threshold is crossed.

## Limitations and Future Work

- The simulator does not implement real packet forwarding, sockets, or router daemons.
- LSA flooding is abstracted into deterministic control-message events.
- Packet loss is estimated from recovery time rather than generated by a packet-level simulator.
- Key exchange is static; a production protocol would need dynamic key management.
- Future work could add packet-level traffic simulation, larger random topologies, realistic queues, link utilization models, and route-flap experiments.
