from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.release_safety import ReleasePolicyThresholds


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetCreate(BaseModel):
    name: str
    description: Optional[str] = None


class DatasetRead(BaseModel):
    id: int
    project_id: int
    name: str
    description: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestCaseRead(BaseModel):
    id: int
    dataset_id: int
    title: str
    audio_file_path: Optional[str]
    reference_file_path: Optional[str]
    reference_transcript: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationRunCreate(BaseModel):
    run_name: str
    model_name: Optional[str] = "not_configured"


class EvaluationRunRead(BaseModel):
    id: int
    project_id: int
    run_name: str
    model_name: str
    status: str

    audio_file_path: Optional[str]
    reference_transcript: Optional[str]
    generated_transcript: Optional[str]

    wer: Optional[float]
    cer: Optional[float]
    quality_label: Optional[str]
    error_summary: Optional[str]

    latency_seconds: Optional[float]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationResultRead(BaseModel):
    id: int
    run_id: int
    test_case_id: int

    generated_transcript: str
    generated_file_path: Optional[str]

    wer: Optional[float]
    cer: Optional[float]
    quality_label: Optional[str]
    error_summary: Optional[str]

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunComparisonCreate(BaseModel):
    baseline_run_id: int
    current_run_id: int


class RunComparisonRead(BaseModel):
    id: int

    baseline_run_id: int
    current_run_id: int

    baseline_average_wer: Optional[float]
    current_average_wer: Optional[float]
    wer_delta: Optional[float]

    baseline_average_cer: Optional[float]
    current_average_cer: Optional[float]
    cer_delta: Optional[float]

    comparison_status: str
    summary: Optional[str]

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectWorkflowSummaryRead(BaseModel):
    project_id: int

    dataset_count: int
    test_case_count: int
    run_count: int
    evaluated_run_count: int
    result_count: int
    comparison_count: int
    debug_case_count: int
    open_debug_case_count: int

    latest_run: Optional[EvaluationRunRead] = None
    latest_comparison: Optional[RunComparisonRead] = None


class DebugCaseCreate(BaseModel):
    title: str
    severity: Optional[str] = "medium"
    failure_type: Optional[str] = "asr_regression"
    summary: Optional[str] = None
    engineer_notes: Optional[str] = None


class DebugCaseRead(BaseModel):
    id: int
    project_id: int
    title: str
    status: str
    severity: str
    failure_type: str
    baseline_run_id: Optional[int]
    current_run_id: Optional[int]
    test_case_id: Optional[int]
    baseline_result_id: Optional[int]
    current_result_id: Optional[int]
    summary: Optional[str]
    engineer_notes: Optional[str]
    ai_suggestion: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DebugCaseDetailRead(BaseModel):
    debug_case: DebugCaseRead
    test_case: Optional[TestCaseRead]
    baseline_run: Optional[EvaluationRunRead]
    current_run: Optional[EvaluationRunRead]
    baseline_result: Optional[EvaluationResultRead]
    current_result: Optional[EvaluationResultRead]


class TranscriptDiffTokenRead(BaseModel):
    operation: str
    reference_word: Optional[str]
    generated_word: Optional[str]
    display_text: str


class TranscriptDiffRead(BaseModel):
    result_id: int
    test_case_id: int
    reference_transcript: str
    generated_transcript: str
    wer: Optional[float]
    cer: Optional[float]
    substitutions: int
    insertions: int
    deletions: int
    matches: int
    tokens: list[TranscriptDiffTokenRead]


class TranscribeAndEvaluateRead(BaseModel):
    result: EvaluationResultRead
    provider: str
    model_name: str
    generated_transcript: str


ReleaseStatus = Literal["pass", "warn", "fail"]
ReleaseSeverity = Literal["none", "low", "medium", "high", "critical"]


class ReleasePolicyUpsert(BaseModel):
    name: str = Field(
        default="Default release policy",
        min_length=1,
        max_length=200,
    )

    warn_current_wer: float = 0.15
    fail_current_wer: float = 0.20

    warn_current_cer: float = 0.08
    fail_current_cer: float = 0.12

    warn_wer_delta: float = 0.01
    fail_wer_delta: float = 0.03

    warn_cer_delta: float = 0.005
    fail_cer_delta: float = 0.02

    @model_validator(mode="after")
    def validate_thresholds(self):
        ReleasePolicyThresholds(
            warn_current_wer=self.warn_current_wer,
            fail_current_wer=self.fail_current_wer,
            warn_current_cer=self.warn_current_cer,
            fail_current_cer=self.fail_current_cer,
            warn_wer_delta=self.warn_wer_delta,
            fail_wer_delta=self.fail_wer_delta,
            warn_cer_delta=self.warn_cer_delta,
            fail_cer_delta=self.fail_cer_delta,
        )
        return self


class ReleasePolicyRead(ReleasePolicyUpsert):
    id: int
    project_id: int
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReleaseCheckRead(BaseModel):
    metric: str
    label: str
    observed_value: float
    warn_threshold: float
    fail_threshold: float
    status: ReleaseStatus
    message: str


class ReleaseReportRead(BaseModel):
    id: int
    project_id: int
    comparison_id: int
    policy_id: Optional[int]

    status: ReleaseStatus
    severity: ReleaseSeverity

    headline: str
    summary: str
    recommendation: str

    policy_snapshot: dict[str, Any]
    checks: list[ReleaseCheckRead]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
