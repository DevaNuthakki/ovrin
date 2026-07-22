from __future__ import annotations

import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.database import Base, SessionLocal, engine
from app.release_safety import (
    ReleasePolicyThresholds,
    evaluate_release_safety,
)


UPLOAD_ROOT = Path("uploads") / "phase-two-validation"


@dataclass(frozen=True)
class DemoSpec:
    project_name: str
    description: str
    expected_status: str
    expected_severity: str

    baseline_wer: float
    current_wer: float
    baseline_cer: float
    current_cer: float

    baseline_output: str
    current_output: str


DEMO_SPECS = (
    DemoSpec(
        project_name="Ovrin Phase 2 PASS Demo",
        description=(
            "Phase 2 validation project demonstrating a release candidate "
            "that passes every configured release-safety threshold."
        ),
        expected_status="pass",
        expected_severity="none",
        baseline_wer=0.17,
        current_wer=0.10,
        baseline_cer=0.10,
        current_cer=0.05,
        baseline_output=(
            "the customer requested an account balance and payment review"
        ),
        current_output=(
            "the customer requested an account balance and payment review"
        ),
    ),
    DemoSpec(
        project_name="Ovrin Phase 2 WARN Demo",
        description=(
            "Phase 2 validation project demonstrating a release candidate "
            "that requires review before approval."
        ),
        expected_status="warn",
        expected_severity="medium",
        baseline_wer=0.155,
        current_wer=0.160,
        baseline_cer=0.088,
        current_cer=0.090,
        baseline_output=(
            "the customer requested an account balance and payment review"
        ),
        current_output=(
            "the customer requested account balance and payment review"
        ),
    ),
    DemoSpec(
        project_name="Ovrin Phase 2 FAIL Demo",
        description=(
            "Phase 2 validation project demonstrating a release candidate "
            "that is blocked by critical ASR regressions."
        ),
        expected_status="fail",
        expected_severity="critical",
        baseline_wer=0.17,
        current_wer=0.21,
        baseline_cer=0.10,
        current_cer=0.13,
        baseline_output=(
            "the customer requested an account balance and payment review"
        ),
        current_output=(
            "the customer rejected the account policy and payment request"
        ),
    ),
)


REFERENCE_TRANSCRIPT = (
    "the customer requested an account balance and payment review "
    "before completing the support call"
)


def slugify(value: str) -> str:
    return (
        value.lower()
        .replace("/", "-")
        .replace(" ", "-")
        .replace("_", "-")
    )


def build_quality_label(wer_score: float) -> str:
    if wer_score <= 0.05:
        return "excellent"
    if wer_score <= 0.15:
        return "good"
    if wer_score <= 0.30:
        return "needs_review"
    return "regression"


def build_comparison_status(
    wer_delta: float,
    cer_delta: float,
) -> str:
    if wer_delta >= 0.05 or cer_delta >= 0.03:
        return "regression"

    if wer_delta <= -0.05 or cer_delta <= -0.03:
        return "improvement"

    return "no_significant_change"


def build_comparison_summary(
    *,
    baseline_wer: float,
    current_wer: float,
    wer_delta: float,
    baseline_cer: float,
    current_cer: float,
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
        f"Baseline WER={baseline_wer:.3f}, "
        f"current WER={current_wer:.3f}, "
        f"WER delta={wer_delta:.3f}. "
        f"Baseline CER={baseline_cer:.3f}, "
        f"current CER={current_cer:.3f}, "
        f"CER delta={cer_delta:.3f}."
    )


def reset_existing_demo_projects(db: Session) -> None:
    project_names = [spec.project_name for spec in DEMO_SPECS]

    existing_projects = (
        db.query(models.Project)
        .filter(models.Project.name.in_(project_names))
        .all()
    )

    for project in existing_projects:
        run_ids = [
            run_id
            for (run_id,) in db.query(models.EvaluationRun.id)
            .filter(models.EvaluationRun.project_id == project.id)
            .all()
        ]

        dataset_ids = [
            dataset_id
            for (dataset_id,) in db.query(models.Dataset.id)
            .filter(models.Dataset.project_id == project.id)
            .all()
        ]

        test_case_ids: list[int] = []
        if dataset_ids:
            test_case_ids = [
                test_case_id
                for (test_case_id,) in db.query(models.TestCase.id)
                .filter(models.TestCase.dataset_id.in_(dataset_ids))
                .all()
            ]

        comparison_ids: list[int] = []
        if run_ids:
            comparison_ids = [
                comparison_id
                for (comparison_id,) in db.query(
                    models.RunComparison.id
                )
                .filter(
                    or_(
                        models.RunComparison.baseline_run_id.in_(
                            run_ids
                        ),
                        models.RunComparison.current_run_id.in_(
                            run_ids
                        ),
                    )
                )
                .all()
            ]

        db.query(models.ReleaseReport).filter(
            models.ReleaseReport.project_id == project.id
        ).delete(synchronize_session=False)

        if comparison_ids:
            db.query(models.ReleaseReport).filter(
                models.ReleaseReport.comparison_id.in_(
                    comparison_ids
                )
            ).delete(synchronize_session=False)

        db.query(models.ReleasePolicy).filter(
            models.ReleasePolicy.project_id == project.id
        ).delete(synchronize_session=False)

        db.query(models.DebugCase).filter(
            models.DebugCase.project_id == project.id
        ).delete(synchronize_session=False)

        if comparison_ids:
            db.query(models.RunComparison).filter(
                models.RunComparison.id.in_(comparison_ids)
            ).delete(synchronize_session=False)

        if run_ids:
            db.query(models.EvaluationResult).filter(
                models.EvaluationResult.run_id.in_(run_ids)
            ).delete(synchronize_session=False)

        if test_case_ids:
            db.query(models.EvaluationResult).filter(
                models.EvaluationResult.test_case_id.in_(
                    test_case_ids
                )
            ).delete(synchronize_session=False)

            db.query(models.TestCase).filter(
                models.TestCase.id.in_(test_case_ids)
            ).delete(synchronize_session=False)

        if run_ids:
            db.query(models.EvaluationRun).filter(
                models.EvaluationRun.id.in_(run_ids)
            ).delete(synchronize_session=False)

        if dataset_ids:
            db.query(models.Dataset).filter(
                models.Dataset.id.in_(dataset_ids)
            ).delete(synchronize_session=False)

        db.query(models.Project).filter(
            models.Project.id == project.id
        ).delete(synchronize_session=False)

    db.commit()

    if UPLOAD_ROOT.exists():
        shutil.rmtree(UPLOAD_ROOT)


def write_demo_artifacts(
    *,
    project_name: str,
    baseline_output: str,
    current_output: str,
) -> dict[str, str]:
    project_root = UPLOAD_ROOT / slugify(project_name)

    audio_dir = project_root / "audio"
    reference_dir = project_root / "reference"
    result_dir = project_root / "results"

    audio_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    audio_path = audio_dir / "release-validation.wav"
    reference_path = reference_dir / "release-validation.txt"
    baseline_path = result_dir / "baseline-generated.txt"
    current_path = result_dir / "current-generated.txt"

    audio_path.write_bytes(
        b"mock local audio bytes for Ovrin Phase 2 validation\n"
    )
    reference_path.write_text(
        REFERENCE_TRANSCRIPT,
        encoding="utf-8",
    )
    baseline_path.write_text(
        baseline_output,
        encoding="utf-8",
    )
    current_path.write_text(
        current_output,
        encoding="utf-8",
    )

    return {
        "audio": str(audio_path),
        "reference": str(reference_path),
        "baseline": str(baseline_path),
        "current": str(current_path),
    }


def create_evaluation_result(
    *,
    db: Session,
    run: models.EvaluationRun,
    test_case: models.TestCase,
    generated_text: str,
    generated_file_path: str,
    wer_score: float,
    cer_score: float,
) -> models.EvaluationResult:
    quality_label = build_quality_label(wer_score)
    error_summary = (
        "Seeded Phase 2 validation metrics. "
        f"WER={wer_score:.3f}, CER={cer_score:.3f}."
    )

    result = models.EvaluationResult(
        run_id=run.id,
        test_case_id=test_case.id,
        generated_transcript=generated_text,
        generated_file_path=generated_file_path,
        wer=wer_score,
        cer=cer_score,
        quality_label=quality_label,
        error_summary=error_summary,
    )
    db.add(result)

    run.reference_transcript = test_case.reference_transcript
    run.generated_transcript = generated_text
    run.wer = wer_score
    run.cer = cer_score
    run.quality_label = quality_label
    run.error_summary = error_summary
    run.status = "evaluated"

    db.flush()
    return result


def create_demo_project(
    db: Session,
    spec: DemoSpec,
) -> dict[str, object]:
    artifacts = write_demo_artifacts(
        project_name=spec.project_name,
        baseline_output=spec.baseline_output,
        current_output=spec.current_output,
    )

    project = models.Project(
        name=spec.project_name,
        description=spec.description,
    )
    db.add(project)
    db.flush()

    dataset = models.Dataset(
        project_id=project.id,
        name="Release-safety validation samples",
        description=(
            "Controlled ASR metrics for validating release policy "
            "decisions."
        ),
    )
    db.add(dataset)
    db.flush()

    test_case = models.TestCase(
        dataset_id=dataset.id,
        title="Release candidate validation sample",
        audio_file_path=artifacts["audio"],
        reference_file_path=artifacts["reference"],
        reference_transcript=REFERENCE_TRANSCRIPT,
    )
    db.add(test_case)
    db.flush()

    baseline_run = models.EvaluationRun(
        project_id=project.id,
        run_name=f"{spec.expected_status.upper()} baseline run",
        model_name="mock-baseline-asr",
        status="created",
    )
    current_run = models.EvaluationRun(
        project_id=project.id,
        run_name=f"{spec.expected_status.upper()} candidate run",
        model_name="mock-candidate-asr",
        status="created",
    )
    db.add_all([baseline_run, current_run])
    db.flush()

    baseline_result = create_evaluation_result(
        db=db,
        run=baseline_run,
        test_case=test_case,
        generated_text=spec.baseline_output,
        generated_file_path=artifacts["baseline"],
        wer_score=spec.baseline_wer,
        cer_score=spec.baseline_cer,
    )
    current_result = create_evaluation_result(
        db=db,
        run=current_run,
        test_case=test_case,
        generated_text=spec.current_output,
        generated_file_path=artifacts["current"],
        wer_score=spec.current_wer,
        cer_score=spec.current_cer,
    )

    wer_delta = spec.current_wer - spec.baseline_wer
    cer_delta = spec.current_cer - spec.baseline_cer

    comparison_status = build_comparison_status(
        wer_delta=wer_delta,
        cer_delta=cer_delta,
    )
    comparison_summary = build_comparison_summary(
        baseline_wer=spec.baseline_wer,
        current_wer=spec.current_wer,
        wer_delta=wer_delta,
        baseline_cer=spec.baseline_cer,
        current_cer=spec.current_cer,
        cer_delta=cer_delta,
        comparison_status=comparison_status,
    )

    comparison = models.RunComparison(
        baseline_run_id=baseline_run.id,
        current_run_id=current_run.id,
        baseline_average_wer=spec.baseline_wer,
        current_average_wer=spec.current_wer,
        wer_delta=wer_delta,
        baseline_average_cer=spec.baseline_cer,
        current_average_cer=spec.current_cer,
        cer_delta=cer_delta,
        comparison_status=comparison_status,
        summary=comparison_summary,
    )
    db.add(comparison)
    db.flush()

    thresholds = ReleasePolicyThresholds()

    policy = models.ReleasePolicy(
        project_id=project.id,
        name="Default release policy",
        version=1,
        is_active=True,
        **asdict(thresholds),
    )
    db.add(policy)
    db.flush()

    release_result = evaluate_release_safety(
        current_average_wer=spec.current_wer,
        current_average_cer=spec.current_cer,
        wer_delta=wer_delta,
        cer_delta=cer_delta,
        policy=thresholds,
    )

    if release_result.status != spec.expected_status:
        raise RuntimeError(
            f"{spec.project_name} expected status "
            f"{spec.expected_status}, got {release_result.status}"
        )

    if release_result.severity != spec.expected_severity:
        raise RuntimeError(
            f"{spec.project_name} expected severity "
            f"{spec.expected_severity}, got "
            f"{release_result.severity}"
        )

    policy_snapshot = {
        "policy_id": policy.id,
        "name": policy.name,
        "version": policy.version,
        **asdict(thresholds),
    }

    report = models.ReleaseReport(
        project_id=project.id,
        comparison_id=comparison.id,
        policy_id=policy.id,
        status=release_result.status,
        severity=release_result.severity,
        headline=release_result.headline,
        summary=release_result.summary,
        recommendation=release_result.recommendation,
        policy_snapshot=policy_snapshot,
        checks=[
            asdict(check)
            for check in release_result.checks
        ],
    )
    db.add(report)
    db.flush()

    debug_case_id: int | None = None

    if release_result.status == "fail":
        debug_case = models.DebugCase(
            project_id=project.id,
            title="Critical release regression requires investigation",
            status="open",
            severity="high",
            failure_type="asr_regression",
            baseline_run_id=baseline_run.id,
            current_run_id=current_run.id,
            test_case_id=test_case.id,
            baseline_result_id=baseline_result.id,
            current_result_id=current_result.id,
            summary=comparison_summary,
            engineer_notes=None,
            ai_suggestion=(
                "Review the release-report failures and transcript "
                "difference, identify the model or decoding change, "
                "then rerun the candidate before release."
            ),
        )
        db.add(debug_case)
        db.flush()
        debug_case_id = debug_case.id

    return {
        "project_id": project.id,
        "comparison_id": comparison.id,
        "report_id": report.id,
        "status": release_result.status,
        "severity": release_result.severity,
        "debug_case_id": debug_case_id,
    }


def main() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        reset_existing_demo_projects(db)

        created_projects = [
            (
                spec,
                create_demo_project(db, spec),
            )
            for spec in DEMO_SPECS
        ]

        db.commit()

        print("Phase 2 validation data created successfully.")

        for spec, result in created_projects:
            print()
            print(f"{spec.expected_status.upper()} DEMO")
            print(f"Project ID: {result['project_id']}")
            print(f"Project name: {spec.project_name}")
            print(f"Comparison ID: {result['comparison_id']}")
            print(f"Release report ID: {result['report_id']}")
            print(f"Status: {result['status']}")
            print(f"Severity: {result['severity']}")

            if result["debug_case_id"] is not None:
                print(f"Debug case ID: {result['debug_case_id']}")

        print()
        print(
            "Open http://localhost:5173 and select each Phase 2 "
            "validation project."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
