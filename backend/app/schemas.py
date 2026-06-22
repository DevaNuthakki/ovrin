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


class DebugCaseRead(BaseModel):
    id: int
    project_id: int
    title: str
    status: str
    severity: str
    failure_type: str
    baseline_run_id: Optional[int]
    current_run_id: Optional[int]
    summary: Optional[str]
    engineer_notes: Optional[str]
    ai_suggestion: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
