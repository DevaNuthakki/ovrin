from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter()


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
    db: Session = Depends(get_db),
):
    db_run = db.query(models.EvaluationRun).filter(models.EvaluationRun.id == run_id).first()

    if db_run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required")

    if not reference_file.filename:
        raise HTTPException(status_code=400, detail="Reference transcript file is required")

    allowed_audio_extensions = {".wav", ".mp3", ".m4a"}
    audio_extension = Path(audio_file.filename).suffix.lower()
    reference_extension = Path(reference_file.filename).suffix.lower()

    if audio_extension not in allowed_audio_extensions:
        raise HTTPException(
            status_code=400,
            detail="Invalid audio file type. Allowed types: .wav, .mp3, .m4a",
        )

    if reference_extension != ".txt":
        raise HTTPException(
            status_code=400,
            detail="Reference transcript must be a .txt file",
        )

    run_upload_dir = Path("uploads") / "runs" / str(run_id)
    audio_dir = run_upload_dir / "audio"
    reference_dir = run_upload_dir / "reference"

    audio_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)

    audio_path = audio_dir / audio_file.filename
    reference_path = reference_dir / reference_file.filename

    audio_content = await audio_file.read()
    reference_content = await reference_file.read()

    if not audio_content:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    if not reference_content:
        raise HTTPException(status_code=400, detail="Reference transcript file is empty")

    audio_path.write_bytes(audio_content)

    try:
        reference_text = reference_content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Reference transcript must be valid UTF-8 text",
        )

    reference_text = reference_text.strip()

    if not reference_text:
        raise HTTPException(status_code=400, detail="Reference transcript text is empty")

    reference_path.write_text(reference_text, encoding="utf-8")

    db_run.audio_file_path = str(audio_path)
    db_run.reference_transcript = reference_text
    db_run.status = "uploaded"

    db.commit()
    db.refresh(db_run)

    return db_run
