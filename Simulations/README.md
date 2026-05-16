# ASHR Protocol - Adaptive Secure Hierarchical Routing Protocol

ASHR is an undergraduate Communication Network Engineering simulation project for EN2150. It designs and evaluates an intradomain hierarchical link-state routing protocol inspired by OSPF and IS-IS, then compares it with simplified educational baselines for RIP, OSPF, IS-IS, and BGP.

This is not a real router implementation. It is a deterministic academic simulator that demonstrates protocol design ideas, failure recovery, metric adaptation, and routing-message security checks.

## Protocol Summary

ASHR combines four main ideas:

- Hierarchical routing using Area 1, Backbone Area 0, and Area 2.
- A normalized adaptive composite metric:

```text
Cij = 0.20H' + 0.30L' + 0.25B' + 0.15P' + 0.10Q'
```

- Event-driven link-state updates with damping, where updates trigger only when the cost change exceeds `theta = 0.15`.
- Security checks for ASHR messages using trusted neighbors, HMAC-SHA256 tags, TTL validation, sequence numbers, replay protection, and fake low-cost route rejection.

## Assignment Relevance

The project addresses limitations of classic routing protocols:

- RIP uses only hop count, converges slowly after failures, and has no built-in message authentication in this simplified baseline.
- OSPF-style static link-state routing reacts faster than RIP but uses a static bandwidth-derived cost and does not respond to congestion, loss, or replay attacks in this simulation.
- IS-IS-style hierarchical link-state routing models configured metrics and summaries but does not adapt to transient congestion.
- BGP-style path-vector routing models AS-path length and slower withdrawals, showing why BGP is not a good intradomain traffic-engineering mechanism.

## Project Structure

```text
ashr-routing-simulation/
├── README.md
├── requirements.txt
├── run_all.py
├── src/
│   ├── __init__.py
│   ├── topology.py
│   ├── metrics.py
│   ├── rip_baseline.py
│   ├── ospf_baseline.py
│   ├── isis_baseline.py
│   ├── bgp_baseline.py
│   ├── ashr_protocol.py
│   ├── security.py
│   ├── simulation.py
│   ├── plotting.py
│   └── utils.py
├── tests/
├── outputs/
└── docs/
```

## Installation

Use Python 3.10 or newer.

```bash
cd ashr-routing-simulation
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

If Python is already configured globally, `pip install -r requirements.txt` also works.

## Run the Simulation

```bash
python run_all.py
```

or with a virtual environment:

```bash
.venv\Scripts\python run_all.py
```

The runner generates all CSV, log, and graph outputs in `outputs/`.

## Run Tests

```bash
pytest -q
```

or:

```bash
.venv\Scripts\python -m pytest -q
```

## Simulation Scenarios

Scenario A: Normal routing

- Computes an R1 to R10 path using RIP hop count.
- Computes an R1 to R10 path using OSPF-style static bandwidth cost.
- Computes an R1 to R10 path using IS-IS-style configured metrics.
- Computes an R1 to R10 path using BGP-style AS-path length.
- Computes an R1 to R10 path using ASHR adaptive cost.
- Saves the selected paths and costs.

Scenario B: Link failure

- Fails the primary-path link `R3-ABR1`.
- Measures RIP convergence rounds.
- Measures OSPF-style, IS-IS-style, and BGP-style recovery time.
- Measures ASHR immediate backup next-hop recovery.
- Estimates packet loss using `100 packets/time unit`.
- Counts control-message overhead.

Scenario C: Congestion change

- Raises congestion, latency, and packet loss on `ABR1-ABR2` to model a congested backbone link.
- RIP, OSPF-style, IS-IS-style, and BGP-style baselines keep the same route because their simplified metrics ignore dynamic congestion.
- ASHR triggers an event-driven update and chooses a lower adaptive-cost route.

Scenario D: Fake routing update attack

- A malicious update advertises fake cost `0` to R10.
- The simplified RIP, OSPF-style, IS-IS-style, and BGP-style baselines accept the forged low-cost route/path update.
- ASHR rejects spoofed or fake low-cost messages.

Scenario E: Replay attack

- A previously valid ASHR LSA is resent.
- ASHR rejects the replayed message because the sequence number is stale.

Scalability benchmark: Convergence time vs nodes

- Generates deterministic hierarchical topologies with 12, 20, 40, and 60 routers.
- Fails ASHR's current primary first-hop link for each topology size.
- Records modeled convergence/recovery time for RIP, OSPF-style, IS-IS-style, BGP-style, and ASHR.
- Also records control messages, estimated packet loss, failed link, and ASHR control-plane rebuild units.

## Output Files

- `outputs/results_summary.csv`: Main quantitative scenario results.
- `outputs/simulation_log.txt`: Human-readable scenario log.
- `outputs/topology.png`: Hierarchical topology diagram with link labels.
- `outputs/convergence_comparison.png`: RIP, OSPF-style, IS-IS-style, BGP-style, and ASHR recovery comparison.
- `outputs/control_overhead_comparison.png`: Control messages during failure handling across all protocols.
- `outputs/packet_loss_comparison.png`: Estimated packet loss during failure across all protocols.
- `outputs/path_cost_comparison.png`: Protocol-specific path cost comparison.
- `outputs/security_attack_comparison.png`: Whether each attack was accepted.
- `outputs/routing_tables_before_after.csv`: Before/after paths for failure and congestion scenarios.
- `outputs/scalability_convergence_vs_nodes.csv`: Convergence/recovery benchmark as node count grows.
- `outputs/scalability_convergence_vs_nodes.png`: Scalability graph plotting convergence/recovery time against router count.

## Current Generated Results

From the latest run:

- Normal RIP path: `R1 -> R2 -> R3 -> ABR1 -> ABR2 -> R8 -> R10`, 6 hops.
- Normal OSPF-style path cost: `27.805556`.
- Normal IS-IS-style path metric: `8.700000`.
- Normal BGP-style AS-path length: `6`.
- Normal ASHR path: `R1 -> R2 -> R3 -> ABR1 -> ABR2 -> R8 -> R10`, cost `2.229737`.
- Link failure recovery time: RIP `5`, OSPF-style `2`, IS-IS-style `2`, BGP-style `6`, ASHR `0`.
- Estimated packet loss during failure: RIP `500`, OSPF-style `200`, IS-IS-style `200`, BGP-style `600`, ASHR `0`.
- Congestion change: RIP, OSPF-style, IS-IS-style, and BGP-style paths did not change; ASHR triggered a metric update.
- Fake update attack: RIP, OSPF-style, IS-IS-style, and BGP-style baselines accepted it; ASHR rejected spoofed and fake low-cost updates.
- Replay attack: ASHR rejected the replayed message.
- Scalability at 60 routers: RIP `16`, OSPF-style `8`, IS-IS-style `6`, BGP-style `9`, ASHR `0` modeled recovery time units. ASHR's control-plane rebuild continues in the background with `4` modeled units.

## Code Mapping to Requirements

- `src/topology.py`: Builds the hierarchical topology and link attributes.
- `src/metrics.py`: Implements normalized ASHR composite cost and damping.
- `src/rip_baseline.py`: Implements the simplified RIP-style baseline.
- `src/ospf_baseline.py`: Implements the simplified OSPF-style static bandwidth link-state baseline.
- `src/isis_baseline.py`: Implements the simplified IS-IS-style hierarchical static-metric baseline.
- `src/bgp_baseline.py`: Implements the simplified BGP-style path-vector baseline.
- `src/ashr_protocol.py`: Implements LSDB, areas, messages, Dijkstra routing, event updates, and backups.
- `src/security.py`: Implements HMAC, TTL, sequence, replay, neighbor, spoofing, and fake-cost checks.
- `src/simulation.py`: Runs Scenarios A-E and writes quantitative outputs.
- `src/plotting.py`: Generates required graphs.
- `tests/`: Verifies metrics, routing, security, output generation, and `run_all.py`.

## Limitations

- ASHR is a simulation-level protocol design, not a packet-forwarding daemon.
- HELLO, LSA flooding, and area summaries are modeled as deterministic control events rather than real network sockets.
- Packet loss is estimated from convergence/recovery time, not from a packet-level queue simulator.
- The RIP, OSPF, IS-IS, and BGP baselines are intentionally simplified educational models; they are not full RFC implementations.
- Security uses preconfigured shared keys and trusted-neighbor tables rather than a real key-management protocol.
