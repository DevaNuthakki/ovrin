from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from jiwer import cer as calculate_cer
from jiwer import process_words
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter()


def build_quality_label(wer_score: float) -> str:
    if wer_score <= 0.05:
        return "excellent"
    if wer_score <= 0.15:
        return "good"
    if wer_score <= 0.30:
        return "needs_review"
    return "regression"


def build_error_summary(reference_text: str, generated_text: str) -> tuple[float, float, str]:
    word_result = process_words(reference_text, generated_text)
    wer_score = float(word_result.wer)
    cer_score = float(calculate_cer(reference_text, generated_text))

    summary = (
        f"WER={wer_score:.3f}, CER={cer_score:.3f}. "
        f"Substitutions={word_result.substitutions}, "
        f"insertions={word_result.insertions}, "
        f"deletions={word_result.deletions}."
    )

    return wer_score, cer_score, summary


def build_comparison_status(wer_delta: float, cer_delta: float) -> str:
    if wer_delta >= 0.05 or cer_delta >= 0.03:
        return "regression"

    if wer_delta <= -0.05 or cer_delta <= -0.03:
        return "improvement"

    return "no_significant_change"


def build_comparison_summary(
    baseline_average_wer: float,
    current_average_wer: float,
    wer_delta: float,
    baseline_average_cer: float,
    current_average_cer: float,
    cer_delta: float,
    comparison_status: str,
) -> str:
    if comparison_status == "regression":
        opening = "Regression detected."
    elif comparison_status == "improvement":
        opening = "Improvement detected."
    else:
        opening = "No significant regression detected."

    return (
        f"{opening} "
        f"Baseline WER={baseline_average_wer:.3f}, current WER={current_average_wer:.3f}, "
        f"WER delta={wer_delta:.3f}. "
        f"Baseline CER={baseline_average_cer:.3f}, current CER={current_average_cer:.3f}, "
        f"CER delta={cer_delta:.3f}."
    )


def build_debug_case_severity(comparison_status: str, wer_delta: float) -> str:
    if comparison_status == "regression" and wer_delta >= 0.20:
        return "high"

    if comparison_status == "regression":
        return "medium"

    return "low"


def calculate_average_metric(results: list[models.EvaluationResult], metric_name: str) -> float:
    metric_values = [
        getattr(result, metric_name)
        for result in results
        if getattr(result, metric_name) is not None
    ]

    if not metric_values:
        raise HTTPException(
            status_code=400,
            detail=f"No {metric_name.upper()} values found for this run",
        )

    return sum(metric_values) / len(metric_values)


def validate_text_file_extension(file_name: str, label: str) -> None:
    extension = Path(file_name).suffix.lower()

    if extension != ".txt":
        raise HTTPException(
            status_code=400,
            detail=f"{label} transcript must be a .txt file",
        )


def decode_transcript_file(file_content: bytes, label: str) -> str:
    if not file_content:
        raise HTTPException(
            status_code=400,
            detail=f"{label} transcript file is empty",
        )

    try:
        transcript_text = file_content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail=f"{label} transcript must be valid UTF-8 text",
        )

    transcript_text = transcript_text.strip()

    if not transcript_text:
        raise HTTPException(
            status_code=400,
            detail=f"{label} transcript text is empty",
        )

    return transcript_text


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "ovrin-api",
    }


@router.post("/projects", response_model=schemas.ProjectRead)
def create_project(
    project: schemas.ProjectCreate,
    db: Session = Depends(get_db),
):
    db_project = models.Project(
        name=project.name,
        description=project.description,
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


@router.get("/projects", response_model=list[schemas.ProjectRead])
def list_projects(db: Session = Depends(get_db)):
    return db.query(models.Project).order_by(models.Project.created_at.desc()).all()


@router.get("/projects/{project_id}", response_model=schemas.ProjectRead)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()

    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return db_project


@router.post(
    "/projects/{project_id}/datasets",
    response_model=schemas.DatasetRead,
)
def create_dataset(
    project_id: int,
    dataset: schemas.DatasetCreate,
    db: Session = Depends(get_db),
):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()

    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    db_dataset = models.Dataset(
        project_id=project_id,
        name=dataset.name,
        description=dataset.description,
    )

    db.add(db_dataset)
    db.commit()
    db.refresh(db_dataset)

    return db_dataset


@router.get(
    "/projects/{project_id}/datasets",
    response_model=list[schemas.DatasetRead],
)
def list_project_datasets(
    project_id: int,
    db: Session = Depends(get_db),
):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()

    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return (
        db.query(models.Dataset)
        .filter(models.Dataset.project_id == project_id)
        .order_by(models.Dataset.created_at.desc())
        .all()
    )


@router.get(
    "/datasets/{dataset_id}",
    response_model=schemas.DatasetRead,
)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
):
    db_dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()

    if db_dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return db_dataset


@router.post(
    "/datasets/{dataset_id}/test-cases",
    response_model=schemas.TestCaseRead,
)
async def create_test_case(
    dataset_id: int,
    title: str = Form(...),
    audio_file: UploadFile = File(...),
    reference_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    db_dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()

    if db_dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not title.strip():
        raise HTTPException(status_code=400, detail="Test case title is required")

    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required")

    if not reference_file.filename:
        raise HTTPException(status_code=400, detail="Reference transcript file is required")

    allowed_audio_extensions = {".wav", ".mp3", ".m4a"}
    audio_file_name = Path(audio_file.filename).name
    reference_file_name = Path(reference_file.filename).name

    audio_extension = Path(audio_file_name).suffix.lower()

    if audio_extension not in allowed_audio_extensions:
        raise HTTPException(
            status_code=400,
            detail="Invalid audio file type. Allowed types: .wav, .mp3, .m4a",
        )

    validate_text_file_extension(reference_file_name, "Reference")

    test_case_upload_dir = Path("uploads") / "datasets" / str(dataset_id) / "test-cases"
    audio_dir = test_case_upload_dir / "audio"
    reference_dir = test_case_upload_dir / "reference"

    audio_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)

    audio_path = audio_dir / audio_file_name
    reference_path = reference_dir / reference_file_name

    audio_content = await audio_file.read()
    reference_content = await reference_file.read()

    if not audio_content:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    reference_text = decode_transcript_file(reference_content, "Reference")

    audio_path.write_bytes(audio_content)
    reference_path.write_text(reference_text, encoding="utf-8")

    db_test_case = models.TestCase(
        dataset_id=dataset_id,
        title=title.strip(),
        audio_file_path=str(audio_path),
        reference_file_path=str(reference_path),
        reference_transcript=reference_text,
    )

    db.add(db_test_case)
    db.commit()
    db.refresh(db_test_case)

    return db_test_case


@router.get(
    "/datasets/{dataset_id}/test-cases",
    response_model=list[schemas.TestCaseRead],
)
def list_dataset_test_cases(
    dataset_id: int,
    db: Session = Depends(get_db),
):
    db_dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()

    if db_dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return (
        db.query(models.TestCase)
        .filter(models.TestCase.dataset_id == dataset_id)
        .order_by(models.TestCase.created_at.desc())
        .all()
    )


@router.get(
    "/test-cases/{test_case_id}",
    response_model=schemas.TestCaseRead,
)
def get_test_case(
    test_case_id: int,
    db: Session = Depends(get_db),
):
    db_test_case = db.query(models.TestCase).filter(models.TestCase.id == test_case_id).first()

    if db_test_case is None:
        raise HTTPException(status_code=404, detail="Test case not found")

    return db_test_case


@router.post(
    "/projects/{project_id}/runs",
    response_model=schemas.EvaluationRunRead,
)
def create_evaluation_run(
    project_id: int,
    run: schemas.EvaluationRunCreate,
    db: Session = Depends(get_db),
):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()

    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    db_run = models.EvaluationRun(
        project_id=project_id,
        run_name=run.run_name,
        model_name=run.model_name or "not_configured",
        status="created",
    )

    db.add(db_run)
    db.commit()
    db.refresh(db_run)

    return db_run


@router.get(
    "/projects/{project_id}/runs",
    response_model=list[schemas.EvaluationRunRead],
)
def list_project_runs(
    project_id: int,
    db: Session = Depends(get_db),
):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()

    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return (
        db.query(models.EvaluationRun)
        .filter(models.EvaluationRun.project_id == project_id)
        .order_by(models.EvaluationRun.created_at.desc())
        .all()
    )


@router.get(
    "/runs/{run_id}",
    response_model=schemas.EvaluationRunRead,
)
def get_evaluation_run(
    run_id: int,
    db: Session = Depends(get_db),
):
    db_run = db.query(models.EvaluationRun).filter(models.EvaluationRun.id == run_id).first()

    if db_run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    return db_run


@router.post(
    "/runs/{run_id}/test-cases/{test_case_id}/evaluate",
    response_model=schemas.EvaluationResultRead,
)
async def evaluate_test_case_for_run(
    run_id: int,
    test_case_id: int,
    generated_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    db_run = db.query(models.EvaluationRun).filter(models.EvaluationRun.id == run_id).first()

    if db_run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    db_test_case = db.query(models.TestCase).filter(models.TestCase.id == test_case_id).first()

    if db_test_case is None:
        raise HTTPException(status_code=404, detail="Test case not found")

    db_dataset = db.query(models.Dataset).filter(models.Dataset.id == db_test_case.dataset_id).first()

    if db_dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if db_dataset.project_id != db_run.project_id:
        raise HTTPException(
            status_code=400,
            detail="Test case dataset does not belong to the same project as this run",
        )

    if not generated_file.filename:
        raise HTTPException(status_code=400, detail="Generated transcript file is required")

    generated_file_name = Path(generated_file.filename).name
    validate_text_file_extension(generated_file_name, "Generated")

    result_upload_dir = Path("uploads") / "runs" / str(run_id) / "results" / str(test_case_id)
    generated_dir = result_upload_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    generated_path = generated_dir / generated_file_name

    generated_content = await generated_file.read()
    generated_text = decode_transcript_file(generated_content, "Generated")

    reference_text = db_test_case.reference_transcript

    wer_score, cer_score, error_summary = build_error_summary(
        reference_text=reference_text,
        generated_text=generated_text,
    )

    quality_label = build_quality_label(wer_score)

    generated_path.write_text(generated_text, encoding="utf-8")

    db_result = models.EvaluationResult(
        run_id=run_id,
        test_case_id=test_case_id,
        generated_transcript=generated_text,
        generated_file_path=str(generated_path),
        wer=wer_score,
        cer=cer_score,
        quality_label=quality_label,
        error_summary=error_summary,
    )

    db.add(db_result)

    db_run.generated_transcript = generated_text
    db_run.reference_transcript = reference_text
    db_run.wer = wer_score
    db_run.cer = cer_score
    db_run.quality_label = quality_label
    db_run.error_summary = error_summary
    db_run.status = "evaluated"

    db.commit()
    db.refresh(db_result)

    return db_result


@router.get(
    "/runs/{run_id}/results",
    response_model=list[schemas.EvaluationResultRead],
)
def list_run_results(
    run_id: int,
    db: Session = Depends(get_db),
):
    db_run = db.query(models.EvaluationRun).filter(models.EvaluationRun.id == run_id).first()

    if db_run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    return (
        db.query(models.EvaluationResult)
        .filter(models.EvaluationResult.run_id == run_id)
        .order_by(models.EvaluationResult.created_at.desc())
        .all()
    )


@router.get(
    "/results/{result_id}",
    response_model=schemas.EvaluationResultRead,
)
def get_evaluation_result(
    result_id: int,
    db: Session = Depends(get_db),
):
    db_result = (
        db.query(models.EvaluationResult)
        .filter(models.EvaluationResult.id == result_id)
        .first()
    )

    if db_result is None:
        raise HTTPException(status_code=404, detail="Evaluation result not found")

    return db_result


@router.post(
    "/runs/compare",
    response_model=schemas.RunComparisonRead,
)
def compare_runs(
    comparison: schemas.RunComparisonCreate,
    db: Session = Depends(get_db),
):
    baseline_run = (
        db.query(models.EvaluationRun)
        .filter(models.EvaluationRun.id == comparison.baseline_run_id)
        .first()
    )
    current_run = (
        db.query(models.EvaluationRun)
        .filter(models.EvaluationRun.id == comparison.current_run_id)
        .first()
    )

    if baseline_run is None:
        raise HTTPException(status_code=404, detail="Baseline run not found")

    if current_run is None:
        raise HTTPException(status_code=404, detail="Current run not found")

    if baseline_run.project_id != current_run.project_id:
        raise HTTPException(
            status_code=400,
            detail="Runs must belong to the same project",
        )

    baseline_results = (
        db.query(models.EvaluationResult)
        .filter(models.EvaluationResult.run_id == baseline_run.id)
        .all()
    )
    current_results = (
        db.query(models.EvaluationResult)
        .filter(models.EvaluationResult.run_id == current_run.id)
        .all()
    )

    if not baseline_results:
        raise HTTPException(
            status_code=400,
            detail="Baseline run has no evaluation results",
        )

    if not current_results:
        raise HTTPException(
            status_code=400,
            detail="Current run has no evaluation results",
        )

    baseline_average_wer = calculate_average_metric(baseline_results, "wer")
    current_average_wer = calculate_average_metric(current_results, "wer")
    wer_delta = current_average_wer - baseline_average_wer

    baseline_average_cer = calculate_average_metric(baseline_results, "cer")
    current_average_cer = calculate_average_metric(current_results, "cer")
    cer_delta = current_average_cer - baseline_average_cer

    comparison_status = build_comparison_status(
        wer_delta=wer_delta,
        cer_delta=cer_delta,
    )

    summary = build_comparison_summary(
        baseline_average_wer=baseline_average_wer,
        current_average_wer=current_average_wer,
        wer_delta=wer_delta,
        baseline_average_cer=baseline_average_cer,
        current_average_cer=current_average_cer,
        cer_delta=cer_delta,
        comparison_status=comparison_status,
    )

    db_comparison = models.RunComparison(
        baseline_run_id=baseline_run.id,
        current_run_id=current_run.id,
        baseline_average_wer=baseline_average_wer,
        current_average_wer=current_average_wer,
        wer_delta=wer_delta,
        baseline_average_cer=baseline_average_cer,
        current_average_cer=current_average_cer,
        cer_delta=cer_delta,
        comparison_status=comparison_status,
        summary=summary,
    )

    db.add(db_comparison)
    db.commit()
    db.refresh(db_comparison)

    return db_comparison


@router.get(
    "/comparisons/{comparison_id}",
    response_model=schemas.RunComparisonRead,
)
def get_run_comparison(
    comparison_id: int,
    db: Session = Depends(get_db),
):
    db_comparison = (
        db.query(models.RunComparison)
        .filter(models.RunComparison.id == comparison_id)
        .first()
    )

    if db_comparison is None:
        raise HTTPException(status_code=404, detail="Run comparison not found")

    return db_comparison


@router.get(
    "/projects/{project_id}/comparisons",
    response_model=list[schemas.RunComparisonRead],
)
def list_project_comparisons(
    project_id: int,
    db: Session = Depends(get_db),
):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()

    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_run_ids = [
        run.id
        for run in db.query(models.EvaluationRun)
        .filter(models.EvaluationRun.project_id == project_id)
        .all()
    ]

    if not project_run_ids:
        return []

    return (
        db.query(models.RunComparison)
        .filter(models.RunComparison.baseline_run_id.in_(project_run_ids))
        .filter(models.RunComparison.current_run_id.in_(project_run_ids))
        .order_by(models.RunComparison.created_at.desc())
        .all()
    )


@router.post(
    "/comparisons/{comparison_id}/debug-case",
    response_model=schemas.DebugCaseRead,
)
def create_debug_case_from_comparison(
    comparison_id: int,
    db: Session = Depends(get_db),
):
    db_comparison = (
        db.query(models.RunComparison)
        .filter(models.RunComparison.id == comparison_id)
        .first()
    )

    if db_comparison is None:
        raise HTTPException(status_code=404, detail="Run comparison not found")

    baseline_run = (
        db.query(models.EvaluationRun)
        .filter(models.EvaluationRun.id == db_comparison.baseline_run_id)
        .first()
    )
    current_run = (
        db.query(models.EvaluationRun)
        .filter(models.EvaluationRun.id == db_comparison.current_run_id)
        .first()
    )

    if baseline_run is None:
        raise HTTPException(status_code=404, detail="Baseline run not found")

    if current_run is None:
        raise HTTPException(status_code=404, detail="Current run not found")

    if db_comparison.comparison_status != "regression":
        raise HTTPException(
            status_code=400,
            detail="Debug case can only be created for regression comparisons",
        )

    existing_debug_case = (
        db.query(models.DebugCase)
        .filter(models.DebugCase.baseline_run_id == baseline_run.id)
        .filter(models.DebugCase.current_run_id == current_run.id)
        .first()
    )

    if existing_debug_case is not None:
        return existing_debug_case

    severity = build_debug_case_severity(
        comparison_status=db_comparison.comparison_status,
        wer_delta=db_comparison.wer_delta or 0.0,
    )

    title = f"Regression detected: {baseline_run.run_name} vs {current_run.run_name}"

    db_debug_case = models.DebugCase(
        project_id=baseline_run.project_id,
        title=title,
        status="open",
        severity=severity,
        failure_type="asr_regression",
        baseline_run_id=baseline_run.id,
        current_run_id=current_run.id,
        summary=db_comparison.summary,
        engineer_notes=None,
        ai_suggestion=None,
    )

    db.add(db_debug_case)
    db.commit()
    db.refresh(db_debug_case)

    return db_debug_case


@router.get(
    "/projects/{project_id}/debug-cases",
    response_model=list[schemas.DebugCaseRead],
)
def list_project_debug_cases(
    project_id: int,
    db: Session = Depends(get_db),
):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()

    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return (
        db.query(models.DebugCase)
        .filter(models.DebugCase.project_id == project_id)
        .order_by(models.DebugCase.created_at.desc())
        .all()
    )


@router.get(
    "/debug-cases/{debug_case_id}",
    response_model=schemas.DebugCaseRead,
)
def get_debug_case(
    debug_case_id: int,
    db: Session = Depends(get_db),
):
    db_debug_case = (
        db.query(models.DebugCase)
        .filter(models.DebugCase.id == debug_case_id)
        .first()
    )

    if db_debug_case is None:
        raise HTTPException(status_code=404, detail="Debug case not found")

    return db_debug_case


@router.post(
    "/runs/{run_id}/upload",
    response_model=schemas.EvaluationRunRead,
)
async def upload_run_artifacts(
    run_id: int,
    audio_file: UploadFile = File(...),
    reference_file: UploadFile = File(...),
    generated_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    db_run = db.query(models.EvaluationRun).filter(models.EvaluationRun.id == run_id).first()

    if db_run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required")

    if not reference_file.filename:
        raise HTTPException(status_code=400, detail="Reference transcript file is required")

    if not generated_file.filename:
        raise HTTPException(status_code=400, detail="Generated transcript file is required")

    allowed_audio_extensions = {".wav", ".mp3", ".m4a"}
    audio_file_name = Path(audio_file.filename).name
    reference_file_name = Path(reference_file.filename).name
    generated_file_name = Path(generated_file.filename).name

    audio_extension = Path(audio_file_name).suffix.lower()

    if audio_extension not in allowed_audio_extensions:
        raise HTTPException(
            status_code=400,
            detail="Invalid audio file type. Allowed types: .wav, .mp3, .m4a",
        )

    validate_text_file_extension(reference_file_name, "Reference")
    validate_text_file_extension(generated_file_name, "Generated")

    run_upload_dir = Path("uploads") / "runs" / str(run_id)
    audio_dir = run_upload_dir / "audio"
    reference_dir = run_upload_dir / "reference"
    generated_dir = run_upload_dir / "generated"

    audio_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)

    audio_path = audio_dir / audio_file_name
    reference_path = reference_dir / reference_file_name
    generated_path = generated_dir / generated_file_name

    audio_content = await audio_file.read()
    reference_content = await reference_file.read()
    generated_content = await generated_file.read()

    if not audio_content:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    reference_text = decode_transcript_file(reference_content, "Reference")
    generated_text = decode_transcript_file(generated_content, "Generated")

    wer_score, cer_score, error_summary = build_error_summary(
        reference_text=reference_text,
        generated_text=generated_text,
    )

    quality_label = build_quality_label(wer_score)

    audio_path.write_bytes(audio_content)
    reference_path.write_text(reference_text, encoding="utf-8")
    generated_path.write_text(generated_text, encoding="utf-8")

    db_run.audio_file_path = str(audio_path)
    db_run.reference_transcript = reference_text
    db_run.generated_transcript = generated_text
    db_run.wer = wer_score
    db_run.cer = cer_score
    db_run.quality_label = quality_label
    db_run.error_summary = error_summary
    db_run.status = "evaluated"

    db.commit()
    db.refresh(db_run)

    return db_run
