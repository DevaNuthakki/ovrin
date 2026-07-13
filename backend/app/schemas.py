from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class DatasetCreate(BaseModel):
    name: str
    description: Optional[str] = None


class DatasetRead(BaseModel):
    id: int
    project_id: int
    name: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TestCaseRead(BaseModel):
    id: int
    dataset_id: int
    title: str
    audio_file_path: Optional[str]
    reference_file_path: Optional[str]
    reference_transcript: str
    created_at: datetime

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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
