"""Run reproducible software-only swarm experiments and export raw evidence.

Example:
  python swarm_experiment_runner.py --sizes 5 10 20 50 --trials 20 \
    --seed 2026 --out experiment_outputs/swarm

This can be CPU-intensive at 50 members. Packet delays are virtual;
harness_wall_ms is host timing and never labelled network/radio latency.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from experiment_statistics import summarize_trials
from swarm_acoustic_experiments import beacon_trial, source_trials
from swarm_geometry_experiments import allocation_trial, formation_trial
from swarm_network_experiments import SCENARIOS, run_election_trial

FAMILIES = ("election", "formation", "allocation", "beacon_receiver", "acoustic_source")
FORMATIONS = ("line", "v", "circle", "grid")


def run_suite(sizes=(5, 10, 20, 50), trials=20, seed=2026,
              families=FAMILIES, network_scenarios=SCENARIOS,
              loss_rate=0.15, bootstrap_samples=1000):
    sizes = tuple(int(n) for n in sizes)
    families = tuple(families)
    network_scenarios = tuple(network_scenarios)
    if not sizes or any(n < 4 or n > 50 for n in sizes) or len(set(sizes)) != len(sizes):
        raise ValueError("Supply unique swarm sizes from 4 through 50")
    if not 1 <= trials <= 200 or not 0 <= loss_rate < 1:
        raise ValueError("Invalid repetitions or packet loss")
    if not families or any(name not in FAMILIES for name in families):
        raise ValueError("Unsupported experiment family")
    if any(name not in SCENARIOS for name in network_scenarios):
        raise ValueError("Unsupported network scenario")
    if bootstrap_samples < 50:
        raise ValueError("At least 50 bootstrap samples required")
    rows = []
    for n in sizes:
        for j in range(trials):
            base = int(seed) + 10007 * (j+1) + 101 * n
            if "election" in families:
                for idx, scenario in enumerate(network_scenarios):
                    row = run_election_trial(
                        n, base + 1000003 * idx, scenario, loss_rate=loss_rate)
                    rows.append({**row, "trial": j})
            if "formation" in families:
                for idx, pattern in enumerate(FORMATIONS):
                    row = formation_trial(n, base + 500003 * idx, pattern)
                    rows.append({**row, "trial": j})
            if "allocation" in families:
                for degraded in (False, True):
                    row = allocation_trial(n, base + 300003 * int(degraded), degraded)
                    rows.append({**row, "trial": j})
    if "beacon_receiver" in families:
        for j in range(trials):
            s = int(seed) + 20011*(j+1)
            for jitter in (0.0, 100.0, 350.0):
                rows.append({**beacon_trial(s, jitter), "trial": j})
            rows.append({**beacon_trial(s, 100.0, False), "trial": j})
    if "acoustic_source" in families:
        rows.extend(source_trials(trials, int(seed)+9371))
    if not rows:
        raise ValueError("No experiments selected")
    summary = summarize_trials(rows, confidence=0.95,
                               resamples=bootstrap_samples, seed=int(seed))
    return rows, summary


def _source_revision() -> str:
    environment = os.environ.get("GITHUB_SHA")
    if environment:
        return environment
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL,
            timeout=3, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _metric(entry: dict, key: str) -> str:
    stat = entry["metrics"].get(key)
    if not stat:
        return "n/a"
    value = stat.get("rate", stat.get("mean"))
    if value is None:
        return "n/a"
    lower, upper = stat.get("lower"), stat.get("upper")
    if lower is None or upper is None:
        return f"{value:.3f} (n={stat.get('observed', stat.get('n', '?'))})"
    return f"{value:.3f} [{lower:.3f}, {upper:.3f}]"


def _markdown_report(summary: list[dict], manifest: dict) -> str:
    lines = [
        "# Seeded Swarm Software-Experiment Results",
        "",
        "**Scope:** deterministic virtual-network / waypoint / known-reference",
        "acoustic experiments. NO physical UAV, radio, field-microphone,",
        "GPS-denied autonomous navigation or Byzantine consensus proof.",
        "",
        f"- Git commit: \x60{manifest['source_revision']}\x60",
        f"- Seed: {manifest['seed']}; repeats per setting: {manifest['trials']}",
        f"- Fleet sizes: {manifest['sizes']}",
        "- Intervals: 95% percentile bootstrap for continuous metrics;",
        "  95% Wilson for observed binary rates. With only one repeat,",
        "  uncertainty limits are unavailable. Conditional localization errors",
        "  exclude failed localizations and always report the missing count.",
        "- Virtual packet delay is not physical radio latency; host",
        "  wall time is not flight-control latency.",
        "",
        "| Family | Scenario | N | Trials | Main observed metric (95% interval) |",
        "|---|---|---:|---:|---|",
    ]
    priorities = {
        "election": "expected_outcome_met", "formation": "pair_violation_reduction",
        "allocation": "ineligible_assignment_reduction",
        "beacon_receiver": "position_error_m",
        "acoustic_source": "position_error_m",
    }
    for item in summary:
        key = priorities[item["family"]]
        lines.append(
            f"| {item['family']} | {item['scenario']} | {item['nodes']} "
            f"| {item['trials']} | {key}: {_metric(item, key)} |"
        )
    lines.extend([
        "",
        "## Interpretation limits",
        "",
        "The omniscient coordinator and naive task assignment are explanatory",
        "baselines, not energy-matched published reference algorithms.",
        "No p-values are inferred from bootstrap intervals. Clock precision,",
        "real acoustic multipath, physical vehicle dynamics, hardware safety,",
        "and cross-view Byzantine liveness require independent experiments.",
        "The complete per-trial CSV and JSON accompany this summary.",
        "",
    ])
    return "\n".join(lines)


def write_evidence(rows, summary, out, *, sizes, trials, seed, families,
                   network_scenarios, loss_rate, bootstrap_samples):
    path = Path(out)
    path.mkdir(parents=True, exist_ok=True)
    raw_payload = json.dumps(rows, indent=2, sort_keys=True,
                             allow_nan=False) + "\n"
    manifest = {
        "schema_version": 1,
        "trials_json_sha256": hashlib.sha256(raw_payload.encode("utf-8")).hexdigest(), "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": _source_revision(),
        "scope": "software_simulation_only",
        "real_uav_hardware": False, "radio_latency_measured": False,
        "full_byzantine_consensus_proven": False,
        "synthetic_acoustic_only": True, "gps_denied_autonomous_flight": False,
        "sizes": list(sizes), "trials": int(trials), "seed": int(seed),
        "families": list(families),
        "network_scenarios": list(network_scenarios),
        "packet_loss_fraction": float(loss_rate),
        "bootstrap_samples": int(bootstrap_samples),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "raw_rows": len(rows),
    }
    files = {
        "csv": path / "trials.csv",
        "json": path / "trials.json",
        "summary": path / "summary.json",
        "manifest": path / "manifest.json",
        "report": path / "REPORT.md",
    }
    keys = sorted({key for row in rows for key in row})
    with files["csv"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    files["json"].write_text(raw_payload, encoding="utf-8")
    files["summary"].write_text(json.dumps(summary, indent=2, sort_keys=True,
                                           allow_nan=False) + "\n", encoding="utf-8")
    files["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True)
                                 + "\n", encoding="utf-8")
    files["report"].write_text(_markdown_report(summary, manifest),
                               encoding="utf-8")
    return {key: str(value) for key, value in files.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[5, 10, 20, 50])
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--families", nargs="+", default=list(FAMILIES),
                        choices=FAMILIES)
    parser.add_argument("--network-scenarios", nargs="+", default=list(SCENARIOS),
                        choices=SCENARIOS)
    parser.add_argument("--loss-rate", type=float, default=0.15)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--out", default="experiment_outputs/swarm")
    args = parser.parse_args(argv)
    rows, summary = run_suite(args.sizes, args.trials, args.seed, args.families,
                              args.network_scenarios, args.loss_rate,
                              args.bootstrap_samples)
    files = write_evidence(rows, summary, args.out,
                           sizes=args.sizes, trials=args.trials,
                           seed=args.seed, families=args.families,
                           network_scenarios=args.network_scenarios,
                           loss_rate=args.loss_rate,
                           bootstrap_samples=args.bootstrap_samples)
    print(json.dumps({"trials_recorded": len(rows),
                      "experiment_settings": len(summary), "files": files},
                     sort_keys=True))


if __name__ == "__main__":
    main()
