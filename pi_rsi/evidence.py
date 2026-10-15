"""Measurement comparisons, kept separate from model interpretations and causal claims."""
from __future__ import annotations

import math


def bootstrap_noise(a: dict, b: dict) -> tuple[float, int] | None:
    """Paired bootstrap spread: bootstrap draws are not independent observations."""
    if not a.get("bootstrap_protocol") or a.get("bootstrap_protocol") != b.get("bootstrap_protocol"):
        return None
    if any(a.get(k) != b.get(k) for k in ("protocol_id", "seedset", "n_studies")):
        return None
    try:
        xs, ys = a.get("bootstrap_samples", []), b.get("bootstrap_samples", [])
        da = {x["id"]: float(x["value"]) for x in xs}
        db = {x["id"]: float(x["value"]) for x in ys}
        if len(da) != len(xs) or len(db) != len(ys) or set(da) != set(db) or len(da) < 100:
            return None
        differences = [da[i] - db[i] for i in da]
        if not all(math.isfinite(d) for d in differences):
            return None
        mean = sum(differences) / len(differences)
        spread = (sum((d - mean) ** 2 for d in differences) / (len(differences) - 1)) ** .5
        return 2 * spread, len(differences)
    except (KeyError, TypeError, ValueError):
        return None


def paired_noise(a: dict, b: dict) -> tuple[float, int] | None:
    """Two empirical SEMs of paired item differences, only for compatible complete item sets.

    This is a descriptive noise diagnostic on selection data, not a significance test
    after adaptive search or proof that the items are statistically independent.
    """
    if a.get("score_transform") != b.get("score_transform"):
        return None
    if a.get("score_transform") not in (None, "mean", "sqrt_mean"):
        return None
    for key in ("protocol_id", "split_id", "seedset"):
        if a.get(key) != b.get(key):
            return None
    try:
        xs, ys = a.get("per_item") or [], b.get("per_item") or []
        da = {x["id"]: float(x["value"]) for x in xs}
        db = {x["id"]: float(x["value"]) for x in ys}
        if len(da) != len(xs) or len(db) != len(ys) or set(da) != set(db) or len(da) < 4:
            return None
        if not all(math.isfinite(x) for x in (*da.values(), *db.values())):
            return None
        diffs = [da[i] - db[i] for i in da]
        n = len(diffs)
        mean = sum(diffs) / n
        sem = (sum((d - mean) ** 2 for d in diffs) / (n - 1) / n) ** 0.5
        if a.get("score_transform") == "sqrt_mean":
            score = float(a.get("score", 0))
            if not math.isfinite(score) or score <= 0:
                return None
            sem /= 2 * score
        return 2 * sem, n
    except (TypeError, ValueError, KeyError):
        return None


VERDICTS = {"above_threshold_gain": "improved", "above_threshold_regression": "worse",
            "within_threshold": "no_change"}


def comparison(metrics: dict, parent: dict, *, score: float, parent_score: float | None,
               higher_is_better: bool, fallback: float, calibration: dict | None = None,
               practical_delta: float = 0.0) -> dict:
    """The harness judgement of one result: the only place that decides improved / no change / worse.

    Noise comes from the best available measurement (paired bootstrap, paired items, reported SEMs,
    then the setup's baseline repeats). The threshold is the larger of that noise band and the
    practical minimum the human set during setup. Without a measured band the verdict is uncertain."""
    delta = None if parent_score is None else (score - parent_score) * (1 if higher_is_better else -1)
    paired = paired_noise(metrics, parent)
    bootstrap = bootstrap_noise(metrics, parent)
    band, count = paired if paired is not None else (fallback, 0)
    method = "paired_item_differences" if paired is not None else "heuristic_only"
    if bootstrap is not None:
        band, count = bootstrap
        method = "paired_study_bootstrap"
    elif paired is None:
        sems = [m.get("score_sem") for m in (metrics, parent)]
        if all(isinstance(s, (int, float)) and math.isfinite(s) and s >= 0 for s in sems):
            band = 2 * sum(s * s for s in sems) ** .5
            method = "reported_unpaired_sem"
        elif calibration and isinstance(calibration.get("band"), (int, float)) and math.isfinite(calibration["band"]):
            band, count = float(calibration["band"]), int(calibration.get("runs", 0))
            method = "baseline_repeats"
    practical = float(practical_delta or 0.0)
    threshold = None if method == "heuristic_only" else max(band, practical)
    classification = "uncertain"
    if delta is not None and threshold is not None:
        classification = "above_threshold_gain" if delta > threshold else (
            "above_threshold_regression" if delta < -threshold else "within_threshold")
    return {"signed_delta": delta, "noise_band": band, "method": method,
            "practical_delta": practical, "threshold": threshold,
            "paired_items": metrics.get("n_studies", 0) if bootstrap else count,
            "bootstrap_draws": count if bootstrap else 0, "classification": classification,
            "verdict": VERDICTS.get(classification, "uncertain"),
            "scope": "Current official selection protocol and evaluated items only.",
            "limitations": "Empirical diagnostic; repeated folds/items may be correlated. Baseline repeats "
                           "measure run-to-run noise only, not seed or sampling variation. Adaptive selection, "
                           "replication and mechanism need separate assessment. A heuristic band cannot "
                           "establish a finding."}
