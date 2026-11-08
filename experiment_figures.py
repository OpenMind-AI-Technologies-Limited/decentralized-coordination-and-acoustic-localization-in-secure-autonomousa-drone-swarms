"""Generate scientific figures from observed trial summaries only.

Charts use the actual JSON summary, never invented smooth curves or interpolated
unmeasured observations. PNG/SVG support paper preparation without claiming
hardware performance.
"""
from __future__ import annotations

import math
from pathlib import Path


def plot_evidence(summary: list[dict], directory) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    paths = []

    def save(fig, basename):
        fig.tight_layout()
        for extension in ("png", "svg"):
            path = out / (basename + "." + extension)
            fig.savefig(path, dpi=170, bbox_inches="tight")
            paths.append(str(path))
        plt.close(fig)

    # Election availability is separate from safe non-election during partition.
    elections = [row for row in summary if row["family"] == "election"]
    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    for scenario in ("healthy", "packet_loss", "byzantine_withholding",
                     "leader_failure", "minority_partition"):
        items = sorted((row for row in elections if row["scenario"] == scenario),
                       key=lambda row: row["nodes"])
        if not items:
            continue
        x, y, low, high = [], [], [], []
        for item in items:
            value = item["metrics"].get("converged", {})
            if "rate" not in value:
                continue
            x.append(item["nodes"])
            y.append(value["rate"])
            low.append(value["rate"] - value["lower"])
            high.append(value["upper"] - value["rate"])
        if x:
            ax.errorbar(x, y, yerr=[low, high], marker="o", capsize=3,
                        label=scenario.replace("_", " "))
    ax.set_xlabel("Registered fleet members (N)")
    ax.set_ylabel("Certified convergence rate (95% Wilson interval)")
    ax.set_title("Synthetic signed-mesh elections — not real RF links")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(alpha=0.2)
    ax.legend(loc="best", fontsize=9)
    save(fig, "election_convergence")

    v_rows = sorted(
        (row for row in summary if row["family"] == "formation" and row["scenario"] == "v"),
        key=lambda row: row["nodes"],
    )
    if v_rows:
        fig, ax = plt.subplots(figsize=(8.8, 5.0))
        xs = list(range(len(v_rows)))
        before = [row["metrics"]["baseline_pair_violations"]["mean"] for row in v_rows]
        after = [row["metrics"]["adjusted_waypoint_violations"]["mean"] for row in v_rows]
        ax.bar([x-0.19 for x in xs], before, 0.38, label="Sampled uncorrected waypoints")
        ax.bar([x+0.19 for x in xs], after, 0.38, label="Adjusted suggested waypoints")
        ax.set_xticks(xs, [str(row["nodes"]) for row in v_rows])
        ax.set_xlabel("Fleet members (N)")
        ax.set_ylabel("Mean hypothetical pair-distance violations")
        ax.set_title("V geometry: proposed waypoints only (no flight dynamics)")
        ax.grid(axis="y", alpha=0.2)
        ax.legend()
        save(fig, "v_formation_spacing")

    allocations = sorted(
        (row for row in summary if row["family"] == "allocation"
         and row["scenario"] == "degraded"),
        key=lambda row: row["nodes"],
    )
    if allocations:
        fig, ax = plt.subplots(figsize=(8.8, 5.0))
        xs = list(range(len(allocations)))
        before = [row["metrics"]["baseline_ineligible_assignments"]["mean"]
                  for row in allocations]
        after = [row["metrics"]["ineligible_assignments"]["mean"]
                 for row in allocations]
        ax.bar([x-0.19 for x in xs], before, 0.38, label="Naive node-ID baseline")
        ax.bar([x+0.19 for x in xs], after, 0.38, label="Health-aware allocation")
        ax.set_xticks(xs, [str(row["nodes"]) for row in allocations])
        ax.set_xlabel("Fleet members (N)")
        ax.set_ylabel("Mean assignments to ineligible nodes")
        ax.set_title("Synthetic task eligibility — no energy measurements")
        ax.grid(axis="y", alpha=0.2)
        ax.legend()
        save(fig, "task_eligibility_comparison")

    acoustic = [
        row for row in summary
        if row["family"] in ("beacon_receiver", "acoustic_source")
        and row["metrics"].get("position_error_m", {}).get("mean") is not None
    ]
    if acoustic:
        fig, ax = plt.subplots(figsize=(9.5, 5.0))
        for family in ("beacon_receiver", "acoustic_source"):
            rows = [row for row in acoustic if row["family"] == family]
            if not rows:
                continue
            xs, ys, intervals = [], [], []
            for row in rows:
                metric = row["metrics"]["position_error_m"]
                # Axis is a category, because source intensity and beacon
                # jitter have incompatible units and cannot share an x-scale.
                xs.append(family.split("_")[0] + ": " + row["scenario"])
                ys.append(metric["mean"])
                intervals.append((metric["lower"], metric["upper"]))
            ax.scatter(xs, ys, label=family.replace("_", " "))
            # Preserve asymmetric bootstrap interval endpoints exactly.
            for name, (lower, upper) in zip(xs, intervals):
                if lower is not None and upper is not None and upper > lower:
                    ax.plot([name, name], [lower, upper], linewidth=1)
        ax.set_ylabel("Conditional mean position error (meters)")
        ax.set_title("Synthetic acoustic localization; only successful estimates")
        ax.tick_params(axis="x", rotation=25, labelsize=8)
        ax.grid(axis="y", alpha=0.2)
        ax.legend()
        save(fig, "synthetic_localization_error")

    return paths
