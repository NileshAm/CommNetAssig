"""Run all ASHR routing simulation scenarios and generate outputs."""

from __future__ import annotations

from pathlib import Path

from src.simulation import run_full_simulation
from src.utils import path_to_string


def main() -> int:
    project_root = Path(__file__).resolve().parent
    output_dir = project_root / "outputs"
    result = run_full_simulation(output_dir)
    scenarios = result["scenarios"]

    print("ASHR simulation completed.")
    print(f"Outputs written to: {output_dir}")
    print("")
    print("Key result values:")
    print(f"- Scenario A RIP path: {path_to_string(scenarios['A']['rip_path'])} ({scenarios['A']['rip_hops']} hops)")
    print(f"- Scenario A OSPF-style path cost: {scenarios['A']['ospf_cost']:.4f}")
    print(f"- Scenario A IS-IS-style path metric: {scenarios['A']['isis_cost']:.4f}")
    print(f"- Scenario A BGP-style AS-path length: {scenarios['A']['bgp_cost']}")
    print(f"- Scenario A ASHR path: {path_to_string(scenarios['A']['ashr_path'])} (cost={scenarios['A']['ashr_cost']:.4f})")
    print(
        "- Scenario B recovery times: "
        f"RIP={scenarios['B']['rip_rounds']}, "
        f"OSPF={scenarios['B']['ospf_convergence_time']}, "
        f"IS-IS={scenarios['B']['isis_convergence_time']}, "
        f"BGP={scenarios['B']['bgp_convergence_time']}, "
        f"ASHR={scenarios['B']['ashr_recovery_time_units']}"
    )
    print(f"- Scenario B ASHR used backup: {scenarios['B']['ashr_used_backup']}")
    print(f"- Scenario C ASHR update triggered: {scenarios['C']['ashr_update_triggered']}")
    print(
        "- Scenario D fake update accepted by baselines: "
        f"RIP={scenarios['D']['rip_accepted']}, "
        f"OSPF={scenarios['D']['ospf_accepted']}, "
        f"IS-IS={scenarios['D']['isis_accepted']}, "
        f"BGP={scenarios['D']['bgp_accepted']}"
    )
    print(f"- Scenario D ASHR rejected fake low cost: {not scenarios['D']['ashr_low_cost_accepted']}")
    print(f"- Scenario E ASHR rejected replay: {not scenarios['E']['replay_accepted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
