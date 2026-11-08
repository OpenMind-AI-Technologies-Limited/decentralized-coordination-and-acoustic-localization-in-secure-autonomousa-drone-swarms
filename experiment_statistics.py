"""Transparent, deterministic uncertainty summaries for synthetic experiments.

A 95% bootstrap percentile interval describes variation across repeated seeded
trials, not evidence of real-world generalization or statistical significance.
All observations must come from actual harness runs, never synthetic placeholders.
"""
from __future__ import annotations

import math
import random
from statistics import mean, median
from typing import Mapping, Sequence


def bootstrap_interval(values: Sequence[float], *, confidence: float = 0.95,
                       resamples: int = 1000, seed: int = 2026) -> dict:
    data = [float(value) for value in values]
    if not data or any(not math.isfinite(value) for value in data):
        raise ValueError("Expected one or more finite trial observations")
    if not (0 < confidence < 1) or resamples < 50:
        raise ValueError("Invalid confidence level or bootstrap count")
    observed = mean(data)
    if len(data) == 1:
        return {"mean": observed, "lower": None, "upper": None,
                "method": "insufficient_repeats", "n": 1}
    rng = random.Random(seed)
    n = len(data)
    means = sorted(mean(data[rng.randrange(n)] for _ in range(n)) for _ in range(resamples))
    alpha = (1.0 - confidence) / 2.0

    def percentile(p: float) -> float:
        x = (len(means) - 1) * p
        low, high = math.floor(x), math.ceil(x)
        return means[low] * (high - x) + means[high] * (x - low) if low != high else means[low]

    return {"mean": observed, "lower": percentile(alpha),
            "upper": percentile(1 - alpha), "method": "bootstrap_percentile",
            "n": n, "confidence": confidence, "resamples": resamples}


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> dict:
    """95% Wilson binomial confidence interval with no normal approximation at 0/1."""
    if not 0 <= successes <= trials or trials < 1:
        raise ValueError("Require 0 <= successes <= trials and trials >= 1")
    proportion = successes / trials
    denom = 1 + z*z/trials
    center = (proportion + z*z/(2*trials)) / denom
    half = z * math.sqrt(proportion*(1-proportion)/trials + z*z/(4*trials*trials)) / denom
    return {"successes": successes, "trials": trials, "rate": proportion,
            "lower": max(0.0, center - half), "upper": min(1.0, center + half),
            "method": "wilson_95"}


def summarize_trials(rows: Sequence[Mapping[str, object]],
                     *, confidence: float = 0.95, resamples: int = 1000,
                     seed: int = 2026) -> list[dict]:
    if not rows:
        raise ValueError("No recorded trials")
    buckets: dict[tuple[str, str, int], list[Mapping[str, object]]] = {}
    for item in rows:
        key = (str(item["family"]), str(item["scenario"]), int(item["nodes"]))
        buckets.setdefault(key, []).append(item)
    results = []
    for (family, scenario, nodes), items in sorted(buckets.items()):
        names = sorted(set.intersection(*(set(row.keys()) for row in items)) - {
            "family", "scenario", "nodes", "seed", "trial", "baseline", "notes",
        })
        aggregated = {"family": family, "scenario": scenario,
                      "nodes": nodes, "trials": len(items), "metrics": {}}
        for metric in names:
            if any(isinstance(row[metric], bool) for row in items):
                count = sum(bool(row[metric]) for row in items)
                aggregated["metrics"][metric] = wilson_interval(count, len(items))
                continue
            try:
                numbers = [float(row[metric]) for row in items]
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(x) for x in numbers):
                raise ValueError(f"Non-finite metric {metric}")
            aggregated["metrics"][metric] = {
                "median": median(numbers),
                **bootstrap_interval(numbers, confidence=confidence,
                                     resamples=resamples,
                                     seed=seed + nodes + len(metric)),
            }
        results.append(aggregated)
    return results
