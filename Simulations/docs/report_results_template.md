# Report Results Template

## Quantitative Results

The following values come from the generated `outputs/results_summary.csv`.

| Scenario | Protocol | Metric | Value |
|---|---:|---:|---:|
| Normal routing | RIP | Path | R1 -> R2 -> R3 -> ABR1 -> ABR2 -> R8 -> R10 |
| Normal routing | RIP | Hop count | 6 |
| Normal routing | OSPF-style | Static path cost | 27.805556 |
| Normal routing | IS-IS-style | Configured path metric | 8.700000 |
| Normal routing | BGP-style | AS-path length | 6 |
| Normal routing | ASHR | Path | R1 -> R2 -> R3 -> ABR1 -> ABR2 -> R8 -> R10 |
| Normal routing | ASHR | Path cost | 2.229737 |
| Link failure | RIP | Convergence rounds | 5 |
| Link failure | RIP | Estimated packet loss | 500 |
| Link failure | OSPF-style | Convergence time units | 2 |
| Link failure | OSPF-style | Estimated packet loss | 200 |
| Link failure | IS-IS-style | Convergence time units | 2 |
| Link failure | IS-IS-style | Estimated packet loss | 200 |
| Link failure | BGP-style | Convergence time units | 6 |
| Link failure | BGP-style | Estimated packet loss | 600 |
| Link failure | ASHR | Recovery time units | 0 |
| Link failure | ASHR | Estimated packet loss | 0 |
| Link failure | ASHR | Used backup route | True |
| Congestion change | RIP | Path changed | False |
| Congestion change | OSPF-style | Path changed | False |
| Congestion change | IS-IS-style | Path changed | False |
| Congestion change | BGP-style | Path changed | False |
| Congestion change | ASHR | Metric update triggered | True |
| Congestion change | ASHR | Before path cost | 2.229737 |
| Congestion change | ASHR | After path cost | 2.103137 |
| Fake update attack | RIP | Attack accepted | True |
| Fake update attack | OSPF-style | Attack accepted | True |
| Fake update attack | IS-IS-style | Attack accepted | True |
| Fake update attack | BGP-style | Attack accepted | True |
| Fake update attack | ASHR | Spoofed attack accepted | False |
| Fake update attack | ASHR | Fake low-cost accepted | False |
| Replay attack | ASHR | First message accepted | True |
| Replay attack | ASHR | Replayed message accepted | False |

## Scalability Benchmark

The scalability benchmark generated hierarchical topologies with 12, 20, 40, and 60 routers and failed the primary first-hop link for the tested source-destination pair. The largest generated topology had 60 routers and 76 links. At 60 routers, the modeled convergence/recovery times were RIP 16, OSPF-style 8, IS-IS-style 6, BGP-style 9, and ASHR 0 time units. ASHR also recorded a separate control-plane rebuild estimate of 4 time units, meaning forwarding recovered immediately through the backup next hop while link-state database repair continued in the background.

## Link Failure Result

When the primary-path link `R3-ABR1` failed, the RIP-style baseline required 5 update rounds to converge, while the OSPF-style and IS-IS-style baselines recovered in 2 modeled time units. The BGP-style baseline required 6 time units because path-vector withdrawals and re-advertisements are modeled as slower. With the packet-loss estimate of 100 packets per time unit, the estimated losses were RIP 500 packets, OSPF-style 200 packets, IS-IS-style 200 packets, BGP-style 600 packets, and ASHR 0 packets. ASHR had already computed a backup path from R1 to R10, so it switched immediately to `R1 -> R4 -> R5 -> R6 -> ABR2 -> R8 -> R10`.

## Congestion Result

The congestion experiment increased the cost of the backbone link `ABR1-ABR2`. RIP continued using the same route because its metric only considers hop count. The OSPF-style baseline also kept the same route because its simplified cost uses bandwidth only, the IS-IS-style baseline kept the same configured-metric route, and the BGP-style baseline kept the same AS-path-length route. ASHR detected that the normalized composite link cost changed beyond the damping threshold and recomputed the path. After the update, ASHR selected `R1 -> R2 -> R3 -> R6 -> ABR2 -> R8 -> R10`, reducing the current normalized path cost to 2.103137 under the updated metric state.

## Security Attack Result

The fake routing update experiment showed the weakness of unauthenticated baseline routing-message models. The RIP, OSPF-style, IS-IS-style, and BGP-style baselines accepted forged low-cost route or path information. ASHR rejected a spoofed update because the sender was not a trusted neighbor, rejected a fake low-cost update even when the sender had a valid HMAC, and rejected a replayed LSA because the sequence number was stale.

## Final Conclusion

The simulation demonstrates that ASHR improves routing behavior over the simplified RIP, OSPF-style, IS-IS-style, and BGP-style baselines in four areas. First, backup next-hop selection improves fault tolerance by allowing immediate recovery after a primary-link failure. Second, normalized adaptive metrics allow ASHR to react to congestion and quality changes that static or path-length metrics ignore. Third, event-driven updates reduce unnecessary periodic update behavior. Fourth, authenticated routing messages and replay protection prevent attacks that the simplified baselines accept.
