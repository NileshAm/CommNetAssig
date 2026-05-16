"""Scenario runner for the ASHR assignment simulation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .ashr_protocol import ASHRProtocol
from .bgp_baseline import BGPBaseline
from .isis_baseline import ISISBaseline
from .metrics import compute_metric_ranges, path_cost
from .ospf_baseline import OSPFBaseline
from .plotting import plot_bar, plot_path_cost, plot_topology
from .rip_baseline import RIPBaseline
from .topology import create_hierarchical_topology
from .utils import ensure_dir, path_to_string, set_deterministic_seed, write_lines


PACKETS_PER_TIME_UNIT = 100


def _summary_row(scenario: str, protocol: str, metric: str, value: object, details: str = "") -> dict[str, object]:
    return {
        "scenario": scenario,
        "protocol": protocol,
        "metric": metric,
        "value": value,
        "details": details,
    }


def scenario_a_normal_routing(log: list[str]) -> dict[str, Any]:
    graph = create_hierarchical_topology()
    rip = RIPBaseline(graph.copy())
    rip_result = rip.run_until_converged(reset=True)
    ospf = OSPFBaseline(graph.copy())
    ospf_result = ospf.run_spf()
    isis = ISISBaseline(graph.copy())
    isis_result = isis.run_spf()
    bgp = BGPBaseline(graph.copy())
    bgp_result = bgp.converge()
    ashr = ASHRProtocol(graph.copy())
    ashr.generate_area_summaries()

    rip_path = rip.get_path("R1", "R10")
    ospf_path = ospf.get_path("R1", "R10")
    isis_path = isis.get_path("R1", "R10")
    bgp_path = bgp.get_path("R1", "R10")
    ashr_route = ashr.get_route("R1", "R10")

    log.append("Scenario A - Normal routing")
    log.append(f"RIP path: {path_to_string(rip_path)} (hops={rip.get_distance('R1', 'R10')})")
    log.append(f"OSPF-style path: {path_to_string(ospf_path)} (static cost={ospf.get_cost('R1', 'R10'):.4f})")
    log.append(f"IS-IS-style path: {path_to_string(isis_path)} (configured metric={isis.get_cost('R1', 'R10'):.4f})")
    log.append(f"BGP-style path: {path_to_string(bgp_path)} (AS-path length={bgp.get_cost('R1', 'R10')})")
    log.append(f"ASHR path: {path_to_string(ashr_route['path'])} (cost={ashr_route['cost']:.4f})")

    return {
        "graph": graph,
        "rip_path": rip_path,
        "rip_hops": rip.get_distance("R1", "R10"),
        "rip_rounds": rip_result.rounds,
        "rip_control_messages": rip_result.control_messages,
        "ospf_path": ospf_path,
        "ospf_cost": ospf.get_cost("R1", "R10"),
        "ospf_convergence_time": ospf_result.convergence_time,
        "ospf_control_messages": ospf_result.control_messages,
        "isis_path": isis_path,
        "isis_cost": isis.get_cost("R1", "R10"),
        "isis_convergence_time": isis_result.convergence_time,
        "isis_control_messages": isis_result.control_messages,
        "bgp_path": bgp_path,
        "bgp_cost": bgp.get_cost("R1", "R10"),
        "bgp_convergence_time": bgp_result.convergence_time,
        "bgp_control_messages": bgp_result.control_messages,
        "ashr_path": ashr_route["path"],
        "ashr_cost": ashr_route["cost"],
        "ashr_control_messages": ashr.message_count,
    }


def scenario_b_link_failure(log: list[str]) -> dict[str, Any]:
    graph_for_rip = create_hierarchical_topology()
    rip = RIPBaseline(graph_for_rip)
    rip.run_until_converged(reset=True)
    rip_before_path = rip.get_path("R1", "R10")
    rip_failure = rip.apply_link_failure("R3", "ABR1")
    rip_after_path = rip.get_path("R1", "R10")

    graph_for_ospf = create_hierarchical_topology()
    ospf = OSPFBaseline(graph_for_ospf)
    ospf_before_path = ospf.get_path("R1", "R10")
    ospf_before_cost = ospf.get_cost("R1", "R10")
    ospf_failure = ospf.apply_link_failure("R3", "ABR1")
    ospf_after_path = ospf.get_path("R1", "R10")
    ospf_after_cost = ospf.get_cost("R1", "R10")

    graph_for_isis = create_hierarchical_topology()
    isis = ISISBaseline(graph_for_isis)
    isis_before_path = isis.get_path("R1", "R10")
    isis_before_cost = isis.get_cost("R1", "R10")
    isis_failure = isis.apply_link_failure("R3", "ABR1")
    isis_after_path = isis.get_path("R1", "R10")
    isis_after_cost = isis.get_cost("R1", "R10")

    graph_for_bgp = create_hierarchical_topology()
    bgp = BGPBaseline(graph_for_bgp)
    bgp_before_path = bgp.get_path("R1", "R10")
    bgp_before_cost = bgp.get_cost("R1", "R10")
    bgp_failure = bgp.apply_link_failure("R3", "ABR1")
    bgp_after_path = bgp.get_path("R1", "R10")
    bgp_after_cost = bgp.get_cost("R1", "R10")

    graph_for_ashr = create_hierarchical_topology()
    ashr = ASHRProtocol(graph_for_ashr)
    ashr_before_route = dict(ashr.get_route("R1", "R10"))
    ashr_backup_route = dict(ashr.get_backup_route("R1", "R10"))
    ashr_failure = ashr.apply_link_failure("R3", "ABR1", "R1", "R10")

    rip_packet_loss = rip_failure.rounds * PACKETS_PER_TIME_UNIT
    ospf_packet_loss = ospf_failure.convergence_time * PACKETS_PER_TIME_UNIT
    isis_packet_loss = isis_failure.convergence_time * PACKETS_PER_TIME_UNIT
    bgp_packet_loss = bgp_failure.convergence_time * PACKETS_PER_TIME_UNIT
    ashr_packet_loss = ashr_failure["recovery_time_units"] * PACKETS_PER_TIME_UNIT

    log.append("")
    log.append("Scenario B - Link failure R3-ABR1")
    log.append(f"RIP before: {path_to_string(rip_before_path)}")
    log.append(f"RIP after: {path_to_string(rip_after_path)}; convergence rounds={rip_failure.rounds}")
    log.append(f"OSPF-style after: {path_to_string(ospf_after_path)}; convergence time={ospf_failure.convergence_time}")
    log.append(f"IS-IS-style after: {path_to_string(isis_after_path)}; convergence time={isis_failure.convergence_time}")
    log.append(f"BGP-style after: {path_to_string(bgp_after_path)}; convergence time={bgp_failure.convergence_time}")
    log.append(f"ASHR primary before: {path_to_string(ashr_before_route['path'])}")
    log.append(f"ASHR backup before: {path_to_string(ashr_backup_route['path'])}")
    log.append(
        f"ASHR after: {path_to_string(ashr_failure['new_path'])}; used_backup={ashr_failure['used_backup']}; "
        f"recovery_time_units={ashr_failure['recovery_time_units']}"
    )

    return {
        "rip_before_path": rip_before_path,
        "rip_after_path": rip_after_path,
        "rip_rounds": rip_failure.rounds,
        "rip_control_messages": rip_failure.control_messages,
        "rip_packet_loss": rip_packet_loss,
        "ospf_before_path": ospf_before_path,
        "ospf_after_path": ospf_after_path,
        "ospf_before_cost": ospf_before_cost,
        "ospf_after_cost": ospf_after_cost,
        "ospf_convergence_time": ospf_failure.convergence_time,
        "ospf_control_messages": ospf_failure.control_messages,
        "ospf_packet_loss": ospf_packet_loss,
        "isis_before_path": isis_before_path,
        "isis_after_path": isis_after_path,
        "isis_before_cost": isis_before_cost,
        "isis_after_cost": isis_after_cost,
        "isis_convergence_time": isis_failure.convergence_time,
        "isis_control_messages": isis_failure.control_messages,
        "isis_packet_loss": isis_packet_loss,
        "bgp_before_path": bgp_before_path,
        "bgp_after_path": bgp_after_path,
        "bgp_before_cost": bgp_before_cost,
        "bgp_after_cost": bgp_after_cost,
        "bgp_convergence_time": bgp_failure.convergence_time,
        "bgp_control_messages": bgp_failure.control_messages,
        "bgp_packet_loss": bgp_packet_loss,
        "ashr_before_path": ashr_before_route["path"],
        "ashr_before_cost": ashr_before_route["cost"],
        "ashr_backup_path": ashr_backup_route["path"],
        "ashr_backup_cost": ashr_backup_route["cost"],
        "ashr_after_path": ashr_failure["new_path"],
        "ashr_after_cost": ashr_failure["new_cost"],
        "ashr_used_backup": ashr_failure["used_backup"],
        "ashr_recovery_time_units": ashr_failure["recovery_time_units"],
        "ashr_control_messages": ashr_failure["control_messages"],
        "ashr_packet_loss": ashr_packet_loss,
    }


def scenario_c_congestion_change(log: list[str]) -> dict[str, Any]:
    rip_graph = create_hierarchical_topology()
    rip = RIPBaseline(rip_graph)
    rip.run_until_converged(reset=True)
    rip_before_path = rip.get_path("R1", "R10")
    rip_before_hops = rip.get_distance("R1", "R10")
    # RIP ignores all non-hop metrics, so the path remains unchanged.
    rip_graph["ABR1"]["ABR2"]["congestion"] = 0.95
    rip_graph["ABR1"]["ABR2"]["latency_ms"] = 55
    rip_after_path = rip.get_path("R1", "R10")
    rip_after_hops = rip.get_distance("R1", "R10")

    ospf_graph = create_hierarchical_topology()
    ospf = OSPFBaseline(ospf_graph)
    ospf_before_path = ospf.get_path("R1", "R10")
    ospf_before_cost = ospf.get_cost("R1", "R10")
    ospf_update = ospf.update_link_metrics("ABR1", "ABR2", congestion=0.95, latency_ms=55, packet_loss=0.015)
    ospf_after_path = ospf.get_path("R1", "R10")
    ospf_after_cost = ospf.get_cost("R1", "R10")

    isis_graph = create_hierarchical_topology()
    isis = ISISBaseline(isis_graph)
    isis_before_path = isis.get_path("R1", "R10")
    isis_before_cost = isis.get_cost("R1", "R10")
    isis_update = isis.update_link_metrics("ABR1", "ABR2", congestion=0.95, latency_ms=55, packet_loss=0.015)
    isis_after_path = isis.get_path("R1", "R10")
    isis_after_cost = isis.get_cost("R1", "R10")

    bgp_graph = create_hierarchical_topology()
    bgp = BGPBaseline(bgp_graph)
    bgp_before_path = bgp.get_path("R1", "R10")
    bgp_before_cost = bgp.get_cost("R1", "R10")
    bgp_update = bgp.update_link_metrics("ABR1", "ABR2", congestion=0.95, latency_ms=55, packet_loss=0.015)
    bgp_after_path = bgp.get_path("R1", "R10")
    bgp_after_cost = bgp.get_cost("R1", "R10")

    ashr_graph = create_hierarchical_topology()
    ashr = ASHRProtocol(ashr_graph)
    before_route = dict(ashr.get_route("R1", "R10"))
    update = ashr.update_link_metrics(
        "ABR1",
        "ABR2",
        congestion=0.95,
        latency_ms=55,
        packet_loss=0.015,
    )
    after_route = dict(ashr.get_route("R1", "R10"))

    ranges = compute_metric_ranges(ashr.graph)
    after_actual_cost = path_cost(ashr.graph, after_route["path"], ranges)

    log.append("")
    log.append("Scenario C - Congestion-driven metric change on ABR1-ABR2")
    log.append(f"RIP before/after path: {path_to_string(rip_before_path)} / {path_to_string(rip_after_path)}")
    log.append(f"OSPF-style before/after path: {path_to_string(ospf_before_path)} / {path_to_string(ospf_after_path)}")
    log.append(f"IS-IS-style before/after path: {path_to_string(isis_before_path)} / {path_to_string(isis_after_path)}")
    log.append(f"BGP-style before/after path: {path_to_string(bgp_before_path)} / {path_to_string(bgp_after_path)}")
    log.append(
        f"ASHR before: {path_to_string(before_route['path'])} cost={before_route['cost']:.4f}; "
        f"after: {path_to_string(after_route['path'])} cost={after_actual_cost:.4f}; "
        f"triggered_update={update['triggered_update']}"
    )

    return {
        "rip_before_path": rip_before_path,
        "rip_after_path": rip_after_path,
        "rip_before_hops": rip_before_hops,
        "rip_after_hops": rip_after_hops,
        "ospf_before_path": ospf_before_path,
        "ospf_after_path": ospf_after_path,
        "ospf_before_cost": ospf_before_cost,
        "ospf_after_cost": ospf_after_cost,
        "ospf_control_messages": ospf_update.control_messages,
        "isis_before_path": isis_before_path,
        "isis_after_path": isis_after_path,
        "isis_before_cost": isis_before_cost,
        "isis_after_cost": isis_after_cost,
        "isis_control_messages": isis_update.control_messages,
        "bgp_before_path": bgp_before_path,
        "bgp_after_path": bgp_after_path,
        "bgp_before_cost": bgp_before_cost,
        "bgp_after_cost": bgp_after_cost,
        "bgp_control_messages": bgp_update.control_messages,
        "ashr_before_path": before_route["path"],
        "ashr_before_cost": before_route["cost"],
        "ashr_after_path": after_route["path"],
        "ashr_after_cost": after_actual_cost,
        "ashr_update_triggered": update["triggered_update"],
        "metric_old_cost": update["old_cost"],
        "metric_new_cost": update["new_cost"],
        "ashr_control_messages": update["control_messages"],
    }


def scenario_d_fake_update_attack(log: list[str]) -> dict[str, Any]:
    rip_graph = create_hierarchical_topology()
    rip = RIPBaseline(rip_graph)
    rip.run_until_converged(reset=True)
    before_distance = rip.get_distance("R1", "R10")
    before_path = rip.get_path("R1", "R10")
    rip_accepted = rip.apply_fake_low_cost_advertisement("R2", "R1", "R10", advertised_cost=0)
    after_distance = rip.get_distance("R1", "R10")
    after_path = rip.get_path("R1", "R10")

    ospf = OSPFBaseline(create_hierarchical_topology())
    ospf_before_cost = ospf.get_cost("R1", "R10")
    ospf_accepted = ospf.apply_fake_low_cost_advertisement("R2", "R1", "R10", advertised_cost=0)
    ospf_after_cost = ospf.get_cost("R1", "R10")

    isis = ISISBaseline(create_hierarchical_topology())
    isis_before_cost = isis.get_cost("R1", "R10")
    isis_accepted = isis.apply_fake_low_cost_advertisement("R2", "R1", "R10", advertised_cost=0)
    isis_after_cost = isis.get_cost("R1", "R10")

    bgp = BGPBaseline(create_hierarchical_topology())
    bgp_before_cost = bgp.get_cost("R1", "R10")
    bgp_accepted = bgp.apply_fake_low_cost_advertisement("R2", "R1", "R10")
    bgp_after_cost = bgp.get_cost("R1", "R10")

    ashr = ASHRProtocol(create_hierarchical_topology())
    spoofed_result = ashr.simulate_spoofed_attack(receiver="R1", malicious_sender="MAL", destination="R10")
    low_cost_result = ashr.simulate_fake_low_cost_attack(receiver="R1", sender="R2", destination="R10")

    log.append("")
    log.append("Scenario D - Fake low-cost update attack")
    log.append(
        f"RIP accepted={rip_accepted}; before_distance={before_distance}; after_distance={after_distance}; "
        f"after_path={path_to_string(after_path)}"
    )
    log.append(f"OSPF-style accepted={ospf_accepted}; cost {ospf_before_cost:.4f} -> {ospf_after_cost:.4f}")
    log.append(f"IS-IS-style accepted={isis_accepted}; cost {isis_before_cost:.4f} -> {isis_after_cost:.4f}")
    log.append(f"BGP-style accepted={bgp_accepted}; path length {bgp_before_cost} -> {bgp_after_cost}")
    log.append(f"ASHR spoofed result: accepted={spoofed_result.accepted}, reason={spoofed_result.reason}")
    log.append(f"ASHR low-cost result: accepted={low_cost_result.accepted}, reason={low_cost_result.reason}")

    return {
        "rip_accepted": rip_accepted,
        "rip_before_distance": before_distance,
        "rip_after_distance": after_distance,
        "rip_before_path": before_path,
        "rip_after_path": after_path,
        "ospf_accepted": ospf_accepted,
        "ospf_before_cost": ospf_before_cost,
        "ospf_after_cost": ospf_after_cost,
        "isis_accepted": isis_accepted,
        "isis_before_cost": isis_before_cost,
        "isis_after_cost": isis_after_cost,
        "bgp_accepted": bgp_accepted,
        "bgp_before_cost": bgp_before_cost,
        "bgp_after_cost": bgp_after_cost,
        "ashr_spoofed_accepted": spoofed_result.accepted,
        "ashr_spoofed_reason": spoofed_result.reason,
        "ashr_low_cost_accepted": low_cost_result.accepted,
        "ashr_low_cost_reason": low_cost_result.reason,
    }


def scenario_e_replay_attack(log: list[str]) -> dict[str, Any]:
    ashr = ASHRProtocol(create_hierarchical_topology())
    first, replay = ashr.simulate_replay_attack(receiver="R1", sender="R2")
    log.append("")
    log.append("Scenario E - Replay attack")
    log.append(f"First ASHR message: accepted={first.accepted}, reason={first.reason}")
    log.append(f"Replayed ASHR message: accepted={replay.accepted}, reason={replay.reason}")
    return {
        "first_accepted": first.accepted,
        "first_reason": first.reason,
        "replay_accepted": replay.accepted,
        "replay_reason": replay.reason,
    }


def _write_results_summary(output_dir: Path, scenarios: dict[str, Any]) -> pd.DataFrame:
    rows = [
        _summary_row("A_Normal_Routing", "RIP", "path", path_to_string(scenarios["A"]["rip_path"])),
        _summary_row("A_Normal_Routing", "RIP", "hop_count", scenarios["A"]["rip_hops"]),
        _summary_row("A_Normal_Routing", "OSPF", "path", path_to_string(scenarios["A"]["ospf_path"])),
        _summary_row("A_Normal_Routing", "OSPF", "static_path_cost", round(scenarios["A"]["ospf_cost"], 6)),
        _summary_row("A_Normal_Routing", "IS-IS", "path", path_to_string(scenarios["A"]["isis_path"])),
        _summary_row("A_Normal_Routing", "IS-IS", "configured_path_metric", round(scenarios["A"]["isis_cost"], 6)),
        _summary_row("A_Normal_Routing", "BGP", "path", path_to_string(scenarios["A"]["bgp_path"])),
        _summary_row("A_Normal_Routing", "BGP", "as_path_length", scenarios["A"]["bgp_cost"]),
        _summary_row("A_Normal_Routing", "ASHR", "path", path_to_string(scenarios["A"]["ashr_path"])),
        _summary_row("A_Normal_Routing", "ASHR", "path_cost", round(scenarios["A"]["ashr_cost"], 6)),
        _summary_row("B_Link_Failure", "RIP", "convergence_rounds", scenarios["B"]["rip_rounds"]),
        _summary_row("B_Link_Failure", "RIP", "control_messages", scenarios["B"]["rip_control_messages"]),
        _summary_row("B_Link_Failure", "RIP", "estimated_packet_loss", scenarios["B"]["rip_packet_loss"]),
        _summary_row("B_Link_Failure", "OSPF", "convergence_time_units", scenarios["B"]["ospf_convergence_time"]),
        _summary_row("B_Link_Failure", "OSPF", "control_messages", scenarios["B"]["ospf_control_messages"]),
        _summary_row("B_Link_Failure", "OSPF", "estimated_packet_loss", scenarios["B"]["ospf_packet_loss"]),
        _summary_row("B_Link_Failure", "IS-IS", "convergence_time_units", scenarios["B"]["isis_convergence_time"]),
        _summary_row("B_Link_Failure", "IS-IS", "control_messages", scenarios["B"]["isis_control_messages"]),
        _summary_row("B_Link_Failure", "IS-IS", "estimated_packet_loss", scenarios["B"]["isis_packet_loss"]),
        _summary_row("B_Link_Failure", "BGP", "convergence_time_units", scenarios["B"]["bgp_convergence_time"]),
        _summary_row("B_Link_Failure", "BGP", "control_messages", scenarios["B"]["bgp_control_messages"]),
        _summary_row("B_Link_Failure", "BGP", "estimated_packet_loss", scenarios["B"]["bgp_packet_loss"]),
        _summary_row("B_Link_Failure", "ASHR", "recovery_time_units", scenarios["B"]["ashr_recovery_time_units"]),
        _summary_row("B_Link_Failure", "ASHR", "control_messages", scenarios["B"]["ashr_control_messages"]),
        _summary_row("B_Link_Failure", "ASHR", "estimated_packet_loss", scenarios["B"]["ashr_packet_loss"]),
        _summary_row("B_Link_Failure", "ASHR", "used_backup", scenarios["B"]["ashr_used_backup"]),
        _summary_row("C_Congestion_Change", "RIP", "path_changed", scenarios["C"]["rip_before_path"] != scenarios["C"]["rip_after_path"]),
        _summary_row("C_Congestion_Change", "OSPF", "path_changed", scenarios["C"]["ospf_before_path"] != scenarios["C"]["ospf_after_path"]),
        _summary_row("C_Congestion_Change", "IS-IS", "path_changed", scenarios["C"]["isis_before_path"] != scenarios["C"]["isis_after_path"]),
        _summary_row("C_Congestion_Change", "BGP", "path_changed", scenarios["C"]["bgp_before_path"] != scenarios["C"]["bgp_after_path"]),
        _summary_row("C_Congestion_Change", "ASHR", "metric_update_triggered", scenarios["C"]["ashr_update_triggered"]),
        _summary_row("C_Congestion_Change", "OSPF", "after_path_cost", round(scenarios["C"]["ospf_after_cost"], 6)),
        _summary_row("C_Congestion_Change", "IS-IS", "after_path_cost", round(scenarios["C"]["isis_after_cost"], 6)),
        _summary_row("C_Congestion_Change", "BGP", "after_path_cost", scenarios["C"]["bgp_after_cost"]),
        _summary_row("C_Congestion_Change", "ASHR", "before_path_cost", round(scenarios["C"]["ashr_before_cost"], 6)),
        _summary_row("C_Congestion_Change", "ASHR", "after_path_cost", round(scenarios["C"]["ashr_after_cost"], 6)),
        _summary_row("D_Fake_Update_Attack", "RIP", "attack_accepted", scenarios["D"]["rip_accepted"]),
        _summary_row("D_Fake_Update_Attack", "OSPF", "attack_accepted", scenarios["D"]["ospf_accepted"]),
        _summary_row("D_Fake_Update_Attack", "IS-IS", "attack_accepted", scenarios["D"]["isis_accepted"]),
        _summary_row("D_Fake_Update_Attack", "BGP", "attack_accepted", scenarios["D"]["bgp_accepted"]),
        _summary_row("D_Fake_Update_Attack", "ASHR", "spoofed_attack_accepted", scenarios["D"]["ashr_spoofed_accepted"], scenarios["D"]["ashr_spoofed_reason"]),
        _summary_row("D_Fake_Update_Attack", "ASHR", "fake_low_cost_accepted", scenarios["D"]["ashr_low_cost_accepted"], scenarios["D"]["ashr_low_cost_reason"]),
        _summary_row("E_Replay_Attack", "ASHR", "first_message_accepted", scenarios["E"]["first_accepted"], scenarios["E"]["first_reason"]),
        _summary_row("E_Replay_Attack", "ASHR", "replayed_message_accepted", scenarios["E"]["replay_accepted"], scenarios["E"]["replay_reason"]),
    ]
    df = pd.DataFrame(rows)
    df.to_csv(output_dir / "results_summary.csv", index=False)
    return df


def _write_routing_tables(output_dir: Path, scenarios: dict[str, Any]) -> pd.DataFrame:
    rows = []

    def add_row(scenario: str, protocol: str, before_path: list[str], after_path: list[str], before_cost: object, after_cost: object, backup_path: list[str] | None = None) -> None:
        rows.append(
            {
                "scenario": scenario,
                "protocol": protocol,
                "source": "R1",
                "destination": "R10",
                "before_path": path_to_string(before_path),
                "after_path": path_to_string(after_path),
                "backup_path": path_to_string(backup_path),
                "before_cost": before_cost,
                "after_cost": after_cost,
            }
        )

    add_row("B_Link_Failure", "RIP", scenarios["B"]["rip_before_path"], scenarios["B"]["rip_after_path"], scenarios["A"]["rip_hops"], "")
    add_row("B_Link_Failure", "OSPF", scenarios["B"]["ospf_before_path"], scenarios["B"]["ospf_after_path"], round(scenarios["B"]["ospf_before_cost"], 6), round(scenarios["B"]["ospf_after_cost"], 6))
    add_row("B_Link_Failure", "IS-IS", scenarios["B"]["isis_before_path"], scenarios["B"]["isis_after_path"], round(scenarios["B"]["isis_before_cost"], 6), round(scenarios["B"]["isis_after_cost"], 6))
    add_row("B_Link_Failure", "BGP", scenarios["B"]["bgp_before_path"], scenarios["B"]["bgp_after_path"], scenarios["B"]["bgp_before_cost"], scenarios["B"]["bgp_after_cost"])
    add_row(
        "B_Link_Failure",
        "ASHR",
        scenarios["B"]["ashr_before_path"],
        scenarios["B"]["ashr_after_path"],
        round(scenarios["B"]["ashr_before_cost"], 6),
        round(scenarios["B"]["ashr_after_cost"], 6),
        scenarios["B"]["ashr_backup_path"],
    )

    add_row("C_Congestion_Change", "RIP", scenarios["C"]["rip_before_path"], scenarios["C"]["rip_after_path"], scenarios["C"]["rip_before_hops"], scenarios["C"]["rip_after_hops"])
    add_row("C_Congestion_Change", "OSPF", scenarios["C"]["ospf_before_path"], scenarios["C"]["ospf_after_path"], round(scenarios["C"]["ospf_before_cost"], 6), round(scenarios["C"]["ospf_after_cost"], 6))
    add_row("C_Congestion_Change", "IS-IS", scenarios["C"]["isis_before_path"], scenarios["C"]["isis_after_path"], round(scenarios["C"]["isis_before_cost"], 6), round(scenarios["C"]["isis_after_cost"], 6))
    add_row("C_Congestion_Change", "BGP", scenarios["C"]["bgp_before_path"], scenarios["C"]["bgp_after_path"], scenarios["C"]["bgp_before_cost"], scenarios["C"]["bgp_after_cost"])
    add_row("C_Congestion_Change", "ASHR", scenarios["C"]["ashr_before_path"], scenarios["C"]["ashr_after_path"], round(scenarios["C"]["ashr_before_cost"], 6), round(scenarios["C"]["ashr_after_cost"], 6))

    df = pd.DataFrame(rows)
    df.to_csv(output_dir / "routing_tables_before_after.csv", index=False)
    return df


def _generate_plots(output_dir: Path, scenarios: dict[str, Any]) -> list[Path]:
    paths = [plot_topology(create_hierarchical_topology(), output_dir)]
    paths.append(
        plot_bar(
            [
                {"protocol": "RIP", "value": scenarios["B"]["rip_rounds"]},
                {"protocol": "OSPF", "value": scenarios["B"]["ospf_convergence_time"]},
                {"protocol": "IS-IS", "value": scenarios["B"]["isis_convergence_time"]},
                {"protocol": "BGP", "value": scenarios["B"]["bgp_convergence_time"]},
                {"protocol": "ASHR", "value": scenarios["B"]["ashr_recovery_time_units"]},
            ],
            x_key="protocol",
            y_key="value",
            title="Convergence and Recovery Comparison",
            ylabel="Time units / update rounds",
            output_dir=output_dir,
            filename="convergence_comparison.png",
        )
    )
    paths.append(
        plot_bar(
            [
                {"protocol": "RIP", "value": scenarios["B"]["rip_control_messages"]},
                {"protocol": "OSPF", "value": scenarios["B"]["ospf_control_messages"]},
                {"protocol": "IS-IS", "value": scenarios["B"]["isis_control_messages"]},
                {"protocol": "BGP", "value": scenarios["B"]["bgp_control_messages"]},
                {"protocol": "ASHR", "value": scenarios["B"]["ashr_control_messages"]},
            ],
            x_key="protocol",
            y_key="value",
            title="Control Message Overhead During Failure",
            ylabel="Control messages",
            output_dir=output_dir,
            filename="control_overhead_comparison.png",
        )
    )
    paths.append(
        plot_bar(
            [
                {"protocol": "RIP", "value": scenarios["B"]["rip_packet_loss"]},
                {"protocol": "OSPF", "value": scenarios["B"]["ospf_packet_loss"]},
                {"protocol": "IS-IS", "value": scenarios["B"]["isis_packet_loss"]},
                {"protocol": "BGP", "value": scenarios["B"]["bgp_packet_loss"]},
                {"protocol": "ASHR", "value": scenarios["B"]["ashr_packet_loss"]},
            ],
            x_key="protocol",
            y_key="value",
            title="Estimated Packet Loss During Failure",
            ylabel="Packets",
            output_dir=output_dir,
            filename="packet_loss_comparison.png",
        )
    )
    paths.append(
        plot_path_cost(
            [
                {"label": "RIP normal\n(hops)", "cost": scenarios["A"]["rip_hops"]},
                {"label": "OSPF normal\n(static)", "cost": scenarios["A"]["ospf_cost"]},
                {"label": "IS-IS normal\n(config)", "cost": scenarios["A"]["isis_cost"]},
                {"label": "BGP normal\n(path len)", "cost": scenarios["A"]["bgp_cost"]},
                {"label": "ASHR normal", "cost": scenarios["A"]["ashr_cost"]},
                {"label": "ASHR after\ncongestion", "cost": scenarios["C"]["ashr_after_cost"]},
            ],
            output_dir,
        )
    )
    paths.append(
        plot_bar(
            [
                {"check": "RIP fake\nroute", "value": int(scenarios["D"]["rip_accepted"])},
                {"check": "OSPF fake\nLSA", "value": int(scenarios["D"]["ospf_accepted"])},
                {"check": "IS-IS fake\nLSP", "value": int(scenarios["D"]["isis_accepted"])},
                {"check": "BGP fake\npath", "value": int(scenarios["D"]["bgp_accepted"])},
                {"check": "ASHR fake\nlow cost", "value": int(scenarios["D"]["ashr_low_cost_accepted"])},
                {"check": "ASHR spoofed\nupdate", "value": int(scenarios["D"]["ashr_spoofed_accepted"])},
                {"check": "ASHR replay\nmessage", "value": int(scenarios["E"]["replay_accepted"])},
            ],
            x_key="check",
            y_key="value",
            title="Security Attack Acceptance Comparison",
            ylabel="Accepted (1=yes, 0=no)",
            output_dir=output_dir,
            filename="security_attack_comparison.png",
        )
    )
    return paths


def run_full_simulation(output_dir: str | Path = "outputs") -> dict[str, Any]:
    set_deterministic_seed()
    output_dir = ensure_dir(output_dir)
    log: list[str] = ["ASHR Protocol Simulation Log", "Deterministic seed: 2150", ""]

    scenarios = {
        "A": scenario_a_normal_routing(log),
        "B": scenario_b_link_failure(log),
        "C": scenario_c_congestion_change(log),
        "D": scenario_d_fake_update_attack(log),
        "E": scenario_e_replay_attack(log),
    }

    results_df = _write_results_summary(output_dir, scenarios)
    routing_df = _write_routing_tables(output_dir, scenarios)
    plot_paths = _generate_plots(output_dir, scenarios)
    write_lines(output_dir / "simulation_log.txt", log)

    return {
        "output_dir": output_dir,
        "scenarios": scenarios,
        "results_summary": results_df,
        "routing_tables": routing_df,
        "plots": plot_paths,
        "log": log,
    }
