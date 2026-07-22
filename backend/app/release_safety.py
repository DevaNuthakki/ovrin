from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


ReleaseStatus = Literal["pass", "warn", "fail"]
ReleaseSeverity = Literal["none", "low", "medium", "high", "critical"]


@dataclass(frozen=True)
class ReleasePolicyThresholds:
    warn_current_wer: float = 0.15
    fail_current_wer: float = 0.20

    warn_current_cer: float = 0.08
    fail_current_cer: float = 0.12

    warn_wer_delta: float = 0.01
    fail_wer_delta: float = 0.03

    warn_cer_delta: float = 0.005
    fail_cer_delta: float = 0.02

    def __post_init__(self) -> None:
        threshold_pairs = (
            (
                "current WER",
                self.warn_current_wer,
                self.fail_current_wer,
            ),
            (
                "current CER",
                self.warn_current_cer,
                self.fail_current_cer,
            ),
            (
                "WER delta",
                self.warn_wer_delta,
                self.fail_wer_delta,
            ),
            (
                "CER delta",
                self.warn_cer_delta,
                self.fail_cer_delta,
            ),
        )

        for metric_name, warn_threshold, fail_threshold in threshold_pairs:
            if not isfinite(warn_threshold) or not isfinite(fail_threshold):
                raise ValueError(
                    f"{metric_name} thresholds must be finite numbers"
                )

            if warn_threshold < 0 or fail_threshold < 0:
                raise ValueError(
                    f"{metric_name} thresholds cannot be negative"
                )

            if warn_threshold > fail_threshold:
                raise ValueError(
                    f"{metric_name} warning threshold cannot exceed "
                    "its failure threshold"
                )


@dataclass(frozen=True)
class ReleaseCheck:
    metric: str
    label: str
    observed_value: float
    warn_threshold: float
    fail_threshold: float
    status: ReleaseStatus
    message: str


@dataclass(frozen=True)
class ReleaseSafetyResult:
    status: ReleaseStatus
    severity: ReleaseSeverity
    checks: tuple[ReleaseCheck, ...]
    headline: str
    summary: str
    recommendation: str


def _build_release_check(
    *,
    metric: str,
    label: str,
    observed_value: float,
    warn_threshold: float,
    fail_threshold: float,
) -> ReleaseCheck:
    if observed_value >= fail_threshold:
        status: ReleaseStatus = "fail"
        message = (
            f"{label} is {observed_value:.3f}, which meets or exceeds "
            f"the failure threshold of {fail_threshold:.3f}."
        )
    elif observed_value >= warn_threshold:
        status = "warn"
        message = (
            f"{label} is {observed_value:.3f}, which meets or exceeds "
            f"the warning threshold of {warn_threshold:.3f}."
        )
    else:
        status = "pass"
        message = (
            f"{label} is {observed_value:.3f}, below the warning "
            f"threshold of {warn_threshold:.3f}."
        )

    return ReleaseCheck(
        metric=metric,
        label=label,
        observed_value=observed_value,
        warn_threshold=warn_threshold,
        fail_threshold=fail_threshold,
        status=status,
        message=message,
    )


def _build_release_severity(
    failed_check_count: int,
    warning_check_count: int,
) -> ReleaseSeverity:
    if failed_check_count >= 2:
        return "critical"

    if failed_check_count == 1:
        return "high"

    if warning_check_count >= 2:
        return "medium"

    if warning_check_count == 1:
        return "low"

    return "none"


def evaluate_release_safety(
    *,
    current_average_wer: float,
    current_average_cer: float,
    wer_delta: float,
    cer_delta: float,
    policy: ReleasePolicyThresholds | None = None,
) -> ReleaseSafetyResult:
    metric_values = {
        "current_average_wer": current_average_wer,
        "current_average_cer": current_average_cer,
        "wer_delta": wer_delta,
        "cer_delta": cer_delta,
    }

    for metric_name, metric_value in metric_values.items():
        if not isfinite(metric_value):
            raise ValueError(f"{metric_name} must be a finite number")

    if current_average_wer < 0:
        raise ValueError("current_average_wer cannot be negative")

    if current_average_cer < 0:
        raise ValueError("current_average_cer cannot be negative")

    active_policy = policy or ReleasePolicyThresholds()

    checks = (
        _build_release_check(
            metric="current_average_wer",
            label="Current average WER",
            observed_value=current_average_wer,
            warn_threshold=active_policy.warn_current_wer,
            fail_threshold=active_policy.fail_current_wer,
        ),
        _build_release_check(
            metric="current_average_cer",
            label="Current average CER",
            observed_value=current_average_cer,
            warn_threshold=active_policy.warn_current_cer,
            fail_threshold=active_policy.fail_current_cer,
        ),
        _build_release_check(
            metric="wer_delta",
            label="WER regression delta",
            observed_value=wer_delta,
            warn_threshold=active_policy.warn_wer_delta,
            fail_threshold=active_policy.fail_wer_delta,
        ),
        _build_release_check(
            metric="cer_delta",
            label="CER regression delta",
            observed_value=cer_delta,
            warn_threshold=active_policy.warn_cer_delta,
            fail_threshold=active_policy.fail_cer_delta,
        ),
    )

    passed_check_count = sum(check.status == "pass" for check in checks)
    warning_check_count = sum(check.status == "warn" for check in checks)
    failed_check_count = sum(check.status == "fail" for check in checks)

    if failed_check_count:
        overall_status: ReleaseStatus = "fail"
        headline = "Release blocked"
        recommendation = (
            "Review the failed checks and transcript differences, resolve "
            "the regression, and run a new comparison before release."
        )
    elif warning_check_count:
        overall_status = "warn"
        headline = "Release requires review"
        recommendation = (
            "Review the warning checks and affected transcripts before "
            "approving the release."
        )
    else:
        overall_status = "pass"
        headline = "Release checks passed"
        recommendation = (
            "The comparison is within the configured release thresholds."
        )

    severity = _build_release_severity(
        failed_check_count=failed_check_count,
        warning_check_count=warning_check_count,
    )

    summary = (
        f"{passed_check_count} checks passed, "
        f"{warning_check_count} checks warned, and "
        f"{failed_check_count} checks failed."
    )

    return ReleaseSafetyResult(
        status=overall_status,
        severity=severity,
        checks=checks,
        headline=headline,
        summary=summary,
        recommendation=recommendation,
    )
