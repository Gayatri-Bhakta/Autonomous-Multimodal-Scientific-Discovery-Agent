from typing import Any, Sequence

import numpy as np
from scipy import stats


def validate_experiment(
    baseline_values: Sequence[float],
    experiment_values: Sequence[float],
) -> dict[str, Any]:
    """Compare experiment results with a baseline using Welch's t-test."""
    baseline = np.asarray(baseline_values, dtype=float)
    experiment = np.asarray(experiment_values, dtype=float)

    if baseline.ndim != 1 or experiment.ndim != 1:
        raise ValueError("Both inputs must be one-dimensional lists of numbers.")
    if len(baseline) < 2 or len(experiment) < 2:
        raise ValueError("Each group must contain at least two values.")
    if not np.isfinite(baseline).all() or not np.isfinite(experiment).all():
        raise ValueError("Values must be finite numbers.")
    if np.var(baseline, ddof=1) == 0 and np.var(experiment, ddof=1) == 0:
        raise ValueError("At least one group must contain some variation.")

    baseline_variance = np.var(baseline, ddof=1)
    experiment_variance = np.var(experiment, ddof=1)
    baseline_mean_variance = baseline_variance / len(baseline)
    experiment_mean_variance = experiment_variance / len(experiment)

    test_result = stats.ttest_ind(
        experiment,
        baseline,
        equal_var=False,
    )
    p_value = float(test_result.pvalue)
    mean_difference = float(np.mean(experiment) - np.mean(baseline))

    # Welch's degrees of freedom for the confidence interval.
    df_numerator = (baseline_mean_variance + experiment_mean_variance) ** 2
    df_denominator = (
        baseline_mean_variance**2 / (len(baseline) - 1)
        + experiment_mean_variance**2 / (len(experiment) - 1)
    )
    degrees_of_freedom = df_numerator / df_denominator

    standard_error = np.sqrt(
        baseline_mean_variance + experiment_mean_variance
    )
    critical_value = stats.t.ppf(0.975, degrees_of_freedom)

    confidence_interval = [
        float(mean_difference - critical_value * standard_error),
        float(mean_difference + critical_value * standard_error),
    ]

    # Cohen's d uses the pooled standard deviation.
    pooled_variance = (
        (len(baseline) - 1) * baseline_variance
        + (len(experiment) - 1) * experiment_variance
    ) / (len(baseline) + len(experiment) - 2)
    effect_size = mean_difference / np.sqrt(pooled_variance)

    is_significant = p_value < 0.05
    if is_significant:
        summary = "The experiment shows a statistically significant difference from the baseline."
    else:
        summary = "The experiment does not show a statistically significant difference from the baseline."

    return {
        "p_value": p_value,
        "is_significant": is_significant,
        "confidence_interval_95": confidence_interval,
        "effect_size_cohens_d": float(effect_size),
        "mean_difference": mean_difference,
        "test_statistic": float(test_result.statistic),
        "summary": summary,`n        "n_baseline": int(len(baseline)),`n        "n_treatment": int(len(experiment)),
    }