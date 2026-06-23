from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    datasets = relationship(
        "Dataset",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    runs = relationship(
        "EvaluationRun",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    debug_cases = relationship(
        "DebugCase",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="datasets")

    test_cases = relationship(
        "TestCase",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)

    title = Column(String(300), nullable=False)
    audio_file_path = Column(String(500), nullable=True)
    reference_file_path = Column(String(500), nullable=True)
    reference_transcript = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("Dataset", back_populates="test_cases")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    run_name = Column(String(200), nullable=False)
    model_name = Column(String(100), default="not_configured")
    status = Column(String(50), default="created")

    audio_file_path = Column(String(500), nullable=True)
    reference_transcript = Column(Text, nullable=True)
    generated_transcript = Column(Text, nullable=True)

    wer = Column(Float, nullable=True)
    cer = Column(Float, nullable=True)
    quality_label = Column(String(50), nullable=True)
    error_summary = Column(Text, nullable=True)

    latency_seconds = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="runs")


class DebugCase(Base):
    __tablename__ = "debug_cases"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    title = Column(String(300), nullable=False)
    status = Column(String(50), default="open")
    severity = Column(String(50), default="medium")
    failure_type = Column(String(100), default="asr_regression")

    baseline_run_id = Column(Integer, nullable=True)
    current_run_id = Column(Integer, nullable=True)

    summary = Column(Text, nullable=True)
    engineer_notes = Column(Text, nullable=True)
    ai_suggestion = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="debug_cases")
