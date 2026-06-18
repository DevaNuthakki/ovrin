from fastapi import APIRouter, Depends, HTTPException
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
