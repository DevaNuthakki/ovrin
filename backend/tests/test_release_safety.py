import pytest

from app.release_safety import (
    ReleasePolicyThresholds,
    evaluate_release_safety,
)


def test_release_passes_when_all_metrics_are_below_warning_thresholds():
    result = evaluate_release_safety(
        current_average_wer=0.10,
        current_average_cer=0.05,
        wer_delta=0.005,
        cer_delta=0.002,
    )

    assert result.status == "pass"
    assert result.severity == "none"
    assert result.headline == "Release checks passed"
    assert all(check.status == "pass" for check in result.checks)


def test_single_warning_has_low_severity():
    result = evaluate_release_safety(
        current_average_wer=0.16,
        current_average_cer=0.05,
        wer_delta=0.005,
        cer_delta=0.002,
    )

    assert result.status == "warn"
    assert result.severity == "low"
    assert sum(check.status == "warn" for check in result.checks) == 1


def test_multiple_warnings_have_medium_severity():
    result = evaluate_release_safety(
        current_average_wer=0.16,
        current_average_cer=0.09,
        wer_delta=0.005,
        cer_delta=0.002,
    )

    assert result.status == "warn"
    assert result.severity == "medium"
    assert sum(check.status == "warn" for check in result.checks) == 2


def test_single_failure_has_high_severity():
    result = evaluate_release_safety(
        current_average_wer=0.10,
        current_average_cer=0.05,
        wer_delta=0.03,
        cer_delta=0.002,
    )

    assert result.status == "fail"
    assert result.severity == "high"
    assert sum(check.status == "fail" for check in result.checks) == 1


def test_multiple_failures_have_critical_severity():
    result = evaluate_release_safety(
        current_average_wer=0.21,
        current_average_cer=0.13,
        wer_delta=0.005,
        cer_delta=0.002,
    )

    assert result.status == "fail"
    assert result.severity == "critical"
    assert sum(check.status == "fail" for check in result.checks) == 2


def test_threshold_boundaries_are_inclusive():
    warning_result = evaluate_release_safety(
        current_average_wer=0.15,
        current_average_cer=0.05,
        wer_delta=0.005,
        cer_delta=0.002,
    )

    failure_result = evaluate_release_safety(
        current_average_wer=0.20,
        current_average_cer=0.05,
        wer_delta=0.005,
        cer_delta=0.002,
    )

    assert warning_result.status == "warn"
    assert failure_result.status == "fail"


def test_policy_rejects_warning_threshold_above_failure_threshold():
    with pytest.raises(ValueError):
        ReleasePolicyThresholds(
            warn_current_wer=0.25,
            fail_current_wer=0.20,
        )
