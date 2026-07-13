from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from jiwer import cer as calculate_cer
from jiwer import process_words
from sqlalchemy.orm import Session

from app import models, schemas
from app.speech import TranscriptionError, get_asr_provider
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


def get_optional_by_id(db: Session, model, object_id: int | None):
    if object_id is None:
        return None

    return db.query(model).filter(model.id == object_id).first()


def find_worst_debug_result_pair(
    db: Session,
    baseline_run_id: int,
    current_run_id: int,
) -> tuple[
    models.EvaluationResult | None,
    models.EvaluationResult | None,
    models.TestCase | None,
]:
    baseline_results = (
        db.query(models.EvaluationResult)
        .filter(models.EvaluationResult.run_id == baseline_run_id)
        .all()
    )
    current_results = (
        db.query(models.EvaluationResult)
        .filter(models.EvaluationResult.run_id == current_run_id)
        .all()
    )

    if not current_results:
        return None, None, None

    baseline_by_test_case_id = {
        result.test_case_id: result for result in baseline_results
    }

    def result_priority(current_result: models.EvaluationResult) -> tuple[float, float, float]:
        baseline_result = baseline_by_test_case_id.get(current_result.test_case_id)

        current_wer = current_result.wer if current_result.wer is not None else -1.0
        current_cer = current_result.cer if current_result.cer is not None else -1.0

        if baseline_result and baseline_result.wer is not None and current_result.wer is not None:
            wer_delta = current_result.wer - baseline_result.wer
        else:
            wer_delta = current_wer

        return wer_delta, current_wer, current_cer

    current_result = max(current_results, key=result_priority)
    baseline_result = baseline_by_test_case_id.get(current_result.test_case_id)
    test_case = (
        db.query(models.TestCase)
        .filter(models.TestCase.id == current_result.test_case_id)
        .first()
    )

    return baseline_result, current_result, test_case


def build_debug_case_ai_suggestion(
    test_case: models.TestCase | None,
    current_result: models.EvaluationResult | None,
) -> str:
    if current_result is None:
        return (
            "Review the linked regression comparison and identify the failing sample "
            "before debugging model or transcript quality."
        )

    test_case_label = test_case.title if test_case is not None else "the selected test case"
    wer_text = f"{current_result.wer:.3f}" if current_result.wer is not None else "unknown"
    cer_text = f"{current_result.cer:.3f}" if current_result.cer is not None else "unknown"

    return (
        f"Start with {test_case_label}. Current result WER={wer_text}, CER={cer_text}. "
        "Review the transcript difference, confirm whether the reference transcript is correct, "
        "then check whether the model output changed because of audio quality, decoding, or model behavior."
    )


def tokenize_transcript(transcript: str) -> list[str]:
    return transcript.strip().split()


def build_structured_transcript_diff(
    reference_text: str,
    generated_text: str,
    result_id: int,
    test_case_id: int,
    wer_score: float | None,
    cer_score: float | None,
) -> dict:
    reference_words = tokenize_transcript(reference_text)
    generated_words = tokenize_transcript(generated_text)

    row_count = len(reference_words) + 1
    column_count = len(generated_words) + 1

    costs = [[0 for _ in range(column_count)] for _ in range(row_count)]

    for row in range(row_count):
        costs[row][0] = row

    for column in range(column_count):
        costs[0][column] = column

    for row in range(1, row_count):
        for column in range(1, column_count):
            if reference_words[row - 1].lower() == generated_words[column - 1].lower():
                substitution_cost = 0
            else:
                substitution_cost = 1

            costs[row][column] = min(
                costs[row - 1][column] + 1,
                costs[row][column - 1] + 1,
                costs[row - 1][column - 1] + substitution_cost,
            )

    tokens = []
    substitutions = 0
    insertions = 0
    deletions = 0
    matches = 0

    row = len(reference_words)
    column = len(generated_words)

    while row > 0 or column > 0:
        if (
            row > 0
            and column > 0
            and reference_words[row - 1].lower() == generated_words[column - 1].lower()
            and costs[row][column] == costs[row - 1][column - 1]
        ):
            word = reference_words[row - 1]
            tokens.append(
                {
                    "operation": "match",
                    "reference_word": word,
                    "generated_word": generated_words[column - 1],
                    "display_text": word,
                }
            )
            matches += 1
            row -= 1
            column -= 1
            continue

        if (
            row > 0
            and column > 0
            and costs[row][column] == costs[row - 1][column - 1] + 1
        ):
            reference_word = reference_words[row - 1]
            generated_word = generated_words[column - 1]
            tokens.append(
                {
                    "operation": "substitution",
                    "reference_word": reference_word,
                    "generated_word": generated_word,
                    "display_text": f"{reference_word} → {generated_word}",
                }
            )
            substitutions += 1
            row -= 1
            column -= 1
            continue

        if column > 0 and costs[row][column] == costs[row][column - 1] + 1:
            generated_word = generated_words[column - 1]
            tokens.append(
                {
                    "operation": "insertion",
                    "reference_word": None,
                    "generated_word": generated_word,
                    "display_text": generated_word,
                }
            )
            insertions += 1
            column -= 1
            continue

        if row > 0:
            reference_word = reference_words[row - 1]
            tokens.append(
                {
                    "operation": "deletion",
                    "reference_word": reference_word,
                    "generated_word": None,
                    "display_text": reference_word,
                }
            )
            deletions += 1
            row -= 1

    tokens.reverse()

    return {
        "result_id": result_id,
        "test_case_id": test_case_id,
        "reference_transcript": reference_text,
        "generated_transcript": generated_text,
        "wer": wer_score,
        "cer": cer_score,
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "matches": matches,
        "tokens": tokens,
    }


def persist_evaluation_result(
    db: Session,
    db_run: models.EvaluationRun,
    db_test_case: models.TestCase,
    generated_text: str,
    generated_file_path: str | None = None,
) -> models.EvaluationResult:
    reference_text = db_test_case.reference_transcript

    wer_score, cer_score, error_summary = build_error_summary(
        reference_text=reference_text,
        generated_text=generated_text,
    )

    quality_label = build_quality_label(wer_score)

    db_result = models.EvaluationResult(
        run_id=db_run.id,
        test_case_id=db_test_case.id,
        generated_transcript=generated_text,
        generated_file_path=generated_file_path,
        wer=wer_score,
        cer=cer_score,
        quality_label=quality_label,
        error_summary=error_summary,
    )

    db.add(db_result)

    db_run.reference_transcript = reference_text
    db_run.generated_transcript = generated_text
    db_run.wer = wer_score
    db_run.cer = cer_score
    db_run.quality_label = quality_label
    db_run.error_summary = error_summary
    db_run.status = "evaluated"

    db.commit()
    db.refresh(db_result)

    return db_result


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


@router.get(
    "/projects/{project_id}/workflow-summary",
    response_model=schemas.ProjectWorkflowSummaryRead,
)
def get_project_workflow_summary(
    project_id: int,
    db: Session = Depends(get_db),
):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()

    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    dataset_count = (
        db.query(models.Dataset)
        .filter(models.Dataset.project_id == project_id)
        .count()
    )

    test_case_count = (
        db.query(models.TestCase)
        .join(models.Dataset)
        .filter(models.Dataset.project_id == project_id)
        .count()
    )

    run_query = db.query(models.EvaluationRun).filter(
        models.EvaluationRun.project_id == project_id
    )

    run_count = run_query.count()
    evaluated_run_count = run_query.filter(
        models.EvaluationRun.status == "evaluated"
    ).count()

    latest_run = (
        db.query(models.EvaluationRun)
        .filter(models.EvaluationRun.project_id == project_id)
        .order_by(models.EvaluationRun.created_at.desc())
        .first()
    )

    result_count = (
        db.query(models.EvaluationResult)
        .join(models.EvaluationRun)
        .filter(models.EvaluationRun.project_id == project_id)
        .count()
    )

    project_run_ids = [
        run.id
        for run in db.query(models.EvaluationRun.id)
        .filter(models.EvaluationRun.project_id == project_id)
        .all()
    ]

    if project_run_ids:
        comparison_query = (
            db.query(models.RunComparison)
            .filter(models.RunComparison.baseline_run_id.in_(project_run_ids))
            .filter(models.RunComparison.current_run_id.in_(project_run_ids))
        )

        comparison_count = comparison_query.count()
        latest_comparison = comparison_query.order_by(
            models.RunComparison.created_at.desc()
        ).first()
    else:
        comparison_count = 0
        latest_comparison = None

    debug_case_query = db.query(models.DebugCase).filter(
        models.DebugCase.project_id == project_id
    )

    debug_case_count = debug_case_query.count()
    open_debug_case_count = debug_case_query.filter(
        models.DebugCase.status != "closed"
    ).count()

    return {
        "project_id": project_id,
        "dataset_count": dataset_count,
        "test_case_count": test_case_count,
        "run_count": run_count,
        "evaluated_run_count": evaluated_run_count,
        "result_count": result_count,
        "comparison_count": comparison_count,
        "debug_case_count": debug_case_count,
        "open_debug_case_count": open_debug_case_count,
        "latest_run": latest_run,
        "latest_comparison": latest_comparison,
    }


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

    generated_path.write_text(generated_text, encoding="utf-8")

    return persist_evaluation_result(
        db=db,
        db_run=db_run,
        db_test_case=db_test_case,
        generated_text=generated_text,
        generated_file_path=str(generated_path),
    )


@router.post(
    "/runs/{run_id}/test-cases/{test_case_id}/transcribe-and-evaluate",
    response_model=schemas.TranscribeAndEvaluateRead,
)
def transcribe_and_evaluate_test_case_for_run(
    run_id: int,
    test_case_id: int,
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

    if not db_test_case.audio_file_path:
        raise HTTPException(
            status_code=400,
            detail="Test case does not have an audio file path",
        )

    try:
        asr_provider = get_asr_provider()
        transcription = asr_provider.transcribe(
            audio_path=db_test_case.audio_file_path,
            model_name=db_run.model_name,
        )
    except TranscriptionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    result_upload_dir = Path("uploads") / "runs" / str(run_id) / "results" / str(test_case_id)
    generated_dir = result_upload_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    generated_path = generated_dir / "generated-by-asr.txt"
    generated_path.write_text(transcription.transcript, encoding="utf-8")

    db_result = persist_evaluation_result(
        db=db,
        db_run=db_run,
        db_test_case=db_test_case,
        generated_text=transcription.transcript,
        generated_file_path=str(generated_path),
    )

    return {
        "result": db_result,
        "provider": transcription.provider,
        "model_name": transcription.model_name,
        "generated_transcript": transcription.transcript,
    }


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


@router.get(
    "/results/{result_id}/transcript-diff",
    response_model=schemas.TranscriptDiffRead,
)
def get_result_transcript_diff(
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

    db_test_case = (
        db.query(models.TestCase)
        .filter(models.TestCase.id == db_result.test_case_id)
        .first()
    )

    if db_test_case is None:
        raise HTTPException(status_code=404, detail="Linked test case not found")

    return build_structured_transcript_diff(
        reference_text=db_test_case.reference_transcript,
        generated_text=db_result.generated_transcript,
        result_id=db_result.id,
        test_case_id=db_result.test_case_id,
        wer_score=db_result.wer,
        cer_score=db_result.cer,
    )


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

    baseline_result, current_result, db_test_case = find_worst_debug_result_pair(
        db=db,
        baseline_run_id=baseline_run.id,
        current_run_id=current_run.id,
    )

    existing_debug_case = (
        db.query(models.DebugCase)
        .filter(models.DebugCase.baseline_run_id == baseline_run.id)
        .filter(models.DebugCase.current_run_id == current_run.id)
        .first()
    )

    if existing_debug_case is not None:
        updated_existing_case = False

        if existing_debug_case.test_case_id is None and db_test_case is not None:
            existing_debug_case.test_case_id = db_test_case.id
            updated_existing_case = True

        if existing_debug_case.baseline_result_id is None and baseline_result is not None:
            existing_debug_case.baseline_result_id = baseline_result.id
            updated_existing_case = True

        if existing_debug_case.current_result_id is None and current_result is not None:
            existing_debug_case.current_result_id = current_result.id
            updated_existing_case = True

        if existing_debug_case.ai_suggestion is None:
            existing_debug_case.ai_suggestion = build_debug_case_ai_suggestion(
                test_case=db_test_case,
                current_result=current_result,
            )
            updated_existing_case = True

        if updated_existing_case:
            db.commit()
            db.refresh(existing_debug_case)

        return existing_debug_case

    severity = build_debug_case_severity(
        comparison_status=db_comparison.comparison_status,
        wer_delta=db_comparison.wer_delta or 0.0,
    )

    if db_test_case is not None:
        title = f"Regression detected in {db_test_case.title}"
    else:
        title = f"Regression detected: {baseline_run.run_name} vs {current_run.run_name}"

    db_debug_case = models.DebugCase(
        project_id=baseline_run.project_id,
        title=title,
        status="open",
        severity=severity,
        failure_type="asr_regression",
        baseline_run_id=baseline_run.id,
        current_run_id=current_run.id,
        test_case_id=db_test_case.id if db_test_case is not None else None,
        baseline_result_id=baseline_result.id if baseline_result is not None else None,
        current_result_id=current_result.id if current_result is not None else None,
        summary=db_comparison.summary,
        engineer_notes=None,
        ai_suggestion=build_debug_case_ai_suggestion(
            test_case=db_test_case,
            current_result=current_result,
        ),
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


@router.get(
    "/debug-cases/{debug_case_id}/details",
    response_model=schemas.DebugCaseDetailRead,
)
def get_debug_case_details(
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

    baseline_run = get_optional_by_id(
        db=db,
        model=models.EvaluationRun,
        object_id=db_debug_case.baseline_run_id,
    )
    current_run = get_optional_by_id(
        db=db,
        model=models.EvaluationRun,
        object_id=db_debug_case.current_run_id,
    )

    baseline_result = get_optional_by_id(
        db=db,
        model=models.EvaluationResult,
        object_id=db_debug_case.baseline_result_id,
    )
    current_result = get_optional_by_id(
        db=db,
        model=models.EvaluationResult,
        object_id=db_debug_case.current_result_id,
    )

    test_case = get_optional_by_id(
        db=db,
        model=models.TestCase,
        object_id=db_debug_case.test_case_id,
    )

    if (
        (baseline_result is None or current_result is None or test_case is None)
        and db_debug_case.baseline_run_id is not None
        and db_debug_case.current_run_id is not None
    ):
        fallback_baseline_result, fallback_current_result, fallback_test_case = (
            find_worst_debug_result_pair(
                db=db,
                baseline_run_id=db_debug_case.baseline_run_id,
                current_run_id=db_debug_case.current_run_id,
            )
        )

        baseline_result = baseline_result or fallback_baseline_result
        current_result = current_result or fallback_current_result
        test_case = test_case or fallback_test_case

    return {
        "debug_case": db_debug_case,
        "test_case": test_case,
        "baseline_run": baseline_run,
        "current_run": current_run,
        "baseline_result": baseline_result,
        "current_result": current_result,
    }


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
