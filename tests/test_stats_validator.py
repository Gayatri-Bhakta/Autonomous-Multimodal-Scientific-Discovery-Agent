from src.utils.stats_validator import validate_experiment


def test_detects_significant_improvement():
    baseline = [10, 11, 9, 10, 12, 11, 9, 10]
    experiment = [15, 16, 14, 15, 17, 16, 14, 15]

    result = validate_experiment(baseline, experiment)

    assert result["is_significant"] is True
    assert result["p_value"] < 0.05
    assert result["confidence_interval_95"][0] > 0
    assert result["effect_size_cohens_d"] > 0


def test_detects_non_significant_results():
    baseline = [10, 11, 9, 10, 12, 11, 9, 10]
    experiment = [10, 10, 11, 9, 11, 10, 10, 11]

    result = validate_experiment(baseline, experiment)

    assert result["is_significant"] is False
    assert result["p_value"] >= 0.05
    assert result["confidence_interval_95"][0] <= 0
    assert result["confidence_interval_95"][1] >= 0