"""Pre-specified two-arm binary experiments; no experiment inferred from GA4."""

from math import ceil, sqrt

import numpy as np
import pandas as pd
from scipy.stats import binomtest, chi2_contingency, fisher_exact, norm


def sample_size(baseline: float, mde: float, alpha=0.05, power=0.8) -> int:
    if not (0 < baseline < 1 and 0 < mde < 1 - baseline and 0 < alpha < 1 and 0 < power < 1):
        raise ValueError("Require baseline and baseline+MDE in (0,1); alpha/power in (0,1)")
    p1, p2 = baseline, baseline + mde
    avg = (p1 + p2) / 2
    return ceil(
        (
            (
                norm.ppf(1 - alpha / 2) * sqrt(2 * avg * (1 - avg))
                + norm.ppf(power) * sqrt(p1 * (1 - p1) + p2 * (1 - p2))
            )
            / mde
        )
        ** 2
    )


def analyze_experiment(frame: pd.DataFrame, alpha=0.05) -> dict:
    required = {"user_key", "variant", "converted"}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError("Need nonempty user_key, variant, converted columns")
    if frame[list(required)].isna().any().any() or frame.user_key.duplicated().any():
        raise ValueError("Exactly one non-null assignment/outcome per user is required")
    if set(frame.variant) != {"control", "treatment"} or not frame.converted.isin([0, 1]).all():
        raise ValueError("Both control/treatment and binary outcomes required")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0,1)")
    groups = frame.groupby("variant").converted.agg(["sum", "count"])
    c, t = groups.loc["control"], groups.loc["treatment"]
    pc, pt = c["sum"] / c["count"], t["sum"] / t["count"]
    table = np.array([[c["sum"], c["count"] - c["sum"]], [t["sum"], t["count"] - t["sum"]]])
    expected = np.outer(table.sum(1), table.sum(0)) / table.sum()
    if (expected < 5).any():
        p = float(fisher_exact(table).pvalue)
        method = "fisher_exact"
    else:
        p = float(chi2_contingency(table, correction=False).pvalue)
        method = "pearson_chi_square"
    # Newcombe interval: difference of independent Wilson score intervals.
    z = norm.ppf(1 - alpha / 2)

    def wilson(k, n):
        p = k / n
        center = (p + z * z / (2 * n)) / (1 + z * z / n)
        half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        return center - half, center + half

    lc, uc = wilson(c["sum"], c["count"])
    lt, ut = wilson(t["sum"], t["count"])
    delta = pt - pc
    srm_p = float(binomtest(int(t["count"]), int(c["count"] + t["count"]), 0.5).pvalue)
    return dict(
        control_n=int(c["count"]),
        treatment_n=int(t["count"]),
        control_rate=pc,
        treatment_rate=pt,
        absolute_lift=delta,
        relative_lift=delta / pc if pc else None,
        p_value=p,
        method=method,
        ci_low=delta - sqrt((pt - lt) ** 2 + (uc - pc) ** 2),
        ci_high=delta + sqrt((ut - pt) ** 2 + (pc - lc) ** 2),
        srm_p_value=srm_p,
        decision="invalid_srm"
        if srm_p < 0.001
        else ("significant" if p < alpha else "inconclusive"),
    )


def detect_anomalies(daily: pd.DataFrame) -> pd.DataFrame:
    result = daily.sort_values("event_date").copy()
    # Prior days only. Zero-variance baselines are unscored, not infinity.
    for metric in ["dau", "purchase_cvr"]:
        history = result[metric].shift(1).rolling(28, min_periods=14)
        result[f"{metric}_baseline"] = history.mean()
        result[f"{metric}_z"] = (result[metric] - history.mean()) / history.std(ddof=1).replace(
            0, np.nan
        )
        result[f"{metric}_alert"] = result[f"{metric}_z"].abs().gt(3)
    result.loc[result.dau < 100, "purchase_cvr_alert"] = False
    result["dau_wow"] = result.dau / result.dau.shift(7).replace(0, np.nan) - 1
    return result
