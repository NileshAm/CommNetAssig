import subprocess
import sys
from pathlib import Path

from src.simulation import run_full_simulation


REQUIRED_OUTPUTS = {
    "results_summary.csv",
    "simulation_log.txt",
    "topology.png",
    "convergence_comparison.png",
    "control_overhead_comparison.png",
    "packet_loss_comparison.png",
    "path_cost_comparison.png",
    "congestion_before_after_path.png",
    "control_messages_vs_nodes.png",
    "scalable_topology_examples.png",
    "security_attack_comparison.png",
    "routing_tables_before_after.csv",
    "scalability_convergence_vs_nodes.csv",
    "scalability_convergence_vs_nodes.png",
}


def test_link_failure_scenario_generates_output_files(tmp_path):
    result = run_full_simulation(tmp_path)

    generated = {path.name for path in Path(tmp_path).iterdir()}
    assert REQUIRED_OUTPUTS.issubset(generated)
    assert result["scenarios"]["B"]["ashr_used_backup"]
    assert result["scenarios"]["B"]["rip_rounds"] > result["scenarios"]["B"]["ashr_recovery_time_units"]
    assert {"RIP", "OSPF", "IS-IS", "BGP", "ASHR"}.issubset(set(result["scalability"]["protocol"]))


def test_run_all_completes_without_crashing():
    project_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "run_all.py"],
        cwd=project_root,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "ASHR simulation completed." in completed.stdout
