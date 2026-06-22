from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
