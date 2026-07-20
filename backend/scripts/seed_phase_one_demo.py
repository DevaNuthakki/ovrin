import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from jiwer import cer as calculate_cer
from jiwer import process_words
from sqlalchemy import or_

from app import models
from app.database import SessionLocal


PROJECT_NAME = "Ovrin Phase 1 Validation Demo"
UPLOAD_ROOT = Path("uploads") / "phase-one-validation"


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


def slugify(value: str) -> str:
    return (
        value.lower()
        .replace("/", "-")
        .replace(" ", "-")
        .replace("_", "-")
    )


def reset_existing_demo_project(db) -> None:
    existing_project = (
        db.query(models.Project)
        .filter(models.Project.name == PROJECT_NAME)
        .first()
    )

    if existing_project is None:
        return

    run_ids = [
        run_id
        for (run_id,) in db.query(models.EvaluationRun.id)
        .filter(models.EvaluationRun.project_id == existing_project.id)
        .all()
    ]

    dataset_ids = [
        dataset_id
        for (dataset_id,) in db.query(models.Dataset.id)
        .filter(models.Dataset.project_id == existing_project.id)
        .all()
    ]

    test_case_ids = []
    if dataset_ids:
        test_case_ids = [
            test_case_id
            for (test_case_id,) in db.query(models.TestCase.id)
            .filter(models.TestCase.dataset_id.in_(dataset_ids))
            .all()
        ]

    if run_ids:
        db.query(models.RunComparison).filter(
            or_(
                models.RunComparison.baseline_run_id.in_(run_ids),
                models.RunComparison.current_run_id.in_(run_ids),
            )
        ).delete(synchronize_session=False)

        db.query(models.EvaluationResult).filter(
            models.EvaluationResult.run_id.in_(run_ids)
        ).delete(synchronize_session=False)

    if test_case_ids:
        db.query(models.EvaluationResult).filter(
            models.EvaluationResult.test_case_id.in_(test_case_ids)
        ).delete(synchronize_session=False)

    db.query(models.DebugCase).filter(
        models.DebugCase.project_id == existing_project.id
    ).delete(synchronize_session=False)

    if dataset_ids:
        db.query(models.TestCase).filter(
            models.TestCase.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

    db.query(models.EvaluationRun).filter(
        models.EvaluationRun.project_id == existing_project.id
    ).delete(synchronize_session=False)

    db.query(models.Dataset).filter(
        models.Dataset.project_id == existing_project.id
    ).delete(synchronize_session=False)

    db.query(models.Project).filter(
        models.Project.id == existing_project.id
    ).delete(synchronize_session=False)

    db.commit()


def write_test_case_artifacts(dataset_name: str, title: str, reference_text: str) -> tuple[str, str]:
    safe_dataset = slugify(dataset_name)
    safe_title = slugify(title)

    audio_dir = UPLOAD_ROOT / safe_dataset / "audio"
    reference_dir = UPLOAD_ROOT / safe_dataset / "reference"

    audio_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)

    audio_path = audio_dir / f"{safe_title}.wav"
    reference_path = reference_dir / f"{safe_title}.txt"

    # The mock ASR provider only requires a non-empty local audio file path.
    audio_path.write_bytes(b"mock local audio bytes for Ovrin phase one validation\n")
    reference_path.write_text(reference_text, encoding="utf-8")

    return str(audio_path), str(reference_path)


def create_result(db, run, test_case, generated_text: str) -> models.EvaluationResult:
    wer_score, cer_score, error_summary = build_error_summary(
        reference_text=test_case.reference_transcript,
        generated_text=generated_text,
    )

    quality_label = build_quality_label(wer_score)

    result_dir = UPLOAD_ROOT / "runs" / str(run.id) / "results"
    result_dir.mkdir(parents=True, exist_ok=True)

    generated_path = result_dir / f"test-case-{test_case.id}-generated.txt"
    generated_path.write_text(generated_text, encoding="utf-8")

    result = models.EvaluationResult(
        run_id=run.id,
        test_case_id=test_case.id,
        generated_transcript=generated_text,
        generated_file_path=str(generated_path),
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


def average(values: list[float]) -> float:
    return sum(values) / len(values)


def main() -> None:
    db = SessionLocal()

    try:
        reset_existing_demo_project(db)

        project = models.Project(
            name=PROJECT_NAME,
            description=(
                "Local Phase 1 validation project showing datasets, test cases, "
                "runs, WER/CER, comparison, and debug-case workflow."
            ),
        )
        db.add(project)
        db.flush()

        customer_dataset = models.Dataset(
            project_id=project.id,
            name="Customer support regression samples",
            description="Short support-call transcripts used for ASR regression checks.",
        )
        accent_dataset = models.Dataset(
            project_id=project.id,
            name="Accent and number stress samples",
            description="Samples focused on accent sensitivity and numeric transcription errors.",
        )

        db.add_all([customer_dataset, accent_dataset])
        db.flush()

        test_case_specs = [
            (
                customer_dataset,
                "Account balance question",
                "hello i need to check my account balance today",
            ),
            (
                accent_dataset,
                "Money transfer amount",
                "please transfer twenty five dollars to savings",
            ),
        ]

        test_cases = []
        for dataset, title, reference_text in test_case_specs:
            audio_path, reference_path = write_test_case_artifacts(
                dataset_name=dataset.name,
                title=title,
                reference_text=reference_text,
            )

            test_case = models.TestCase(
                dataset_id=dataset.id,
                title=title,
                audio_file_path=audio_path,
                reference_file_path=reference_path,
                reference_transcript=reference_text,
            )
            db.add(test_case)
            test_cases.append(test_case)

        db.flush()

        baseline_run = models.EvaluationRun(
            project_id=project.id,
            run_name="Phase 1 baseline run",
            model_name="mock-baseline-asr",
            status="created",
        )
        current_run = models.EvaluationRun(
            project_id=project.id,
            run_name="Phase 1 current regression run",
            model_name="mock-current-asr",
            status="created",
        )

        db.add_all([baseline_run, current_run])
        db.flush()

        baseline_outputs = [
            "hello i need to check my account balance today",
            "please transfer twenty five dollars to savings",
        ]

        current_outputs = [
            "hello i need to check my account policy today",
            "please transfer fifty five dollars to savings",
        ]

        baseline_results = [
            create_result(db, baseline_run, test_case, generated_text)
            for test_case, generated_text in zip(test_cases, baseline_outputs)
        ]

        current_results = [
            create_result(db, current_run, test_case, generated_text)
            for test_case, generated_text in zip(test_cases, current_outputs)
        ]

        baseline_average_wer = average([result.wer for result in baseline_results if result.wer is not None])
        current_average_wer = average([result.wer for result in current_results if result.wer is not None])
        wer_delta = current_average_wer - baseline_average_wer

        baseline_average_cer = average([result.cer for result in baseline_results if result.cer is not None])
        current_average_cer = average([result.cer for result in current_results if result.cer is not None])
        cer_delta = current_average_cer - baseline_average_cer

        comparison_status = build_comparison_status(
            wer_delta=wer_delta,
            cer_delta=cer_delta,
        )

        comparison_summary = (
            "Regression detected. "
            f"Baseline WER={baseline_average_wer:.3f}, current WER={current_average_wer:.3f}, "
            f"WER delta={wer_delta:.3f}. "
            f"Baseline CER={baseline_average_cer:.3f}, current CER={current_average_cer:.3f}, "
            f"CER delta={cer_delta:.3f}."
        )

        comparison = models.RunComparison(
            baseline_run_id=baseline_run.id,
            current_run_id=current_run.id,
            baseline_average_wer=baseline_average_wer,
            current_average_wer=current_average_wer,
            wer_delta=wer_delta,
            baseline_average_cer=baseline_average_cer,
            current_average_cer=current_average_cer,
            cer_delta=cer_delta,
            comparison_status=comparison_status,
            summary=comparison_summary,
        )
        db.add(comparison)
        db.flush()

        worst_current_result = max(current_results, key=lambda result: result.wer or 0.0)
        worst_index = current_results.index(worst_current_result)
        worst_baseline_result = baseline_results[worst_index]
        worst_test_case = test_cases[worst_index]

        debug_case = models.DebugCase(
            project_id=project.id,
            title=f"Regression detected in {worst_test_case.title}",
            status="open",
            severity="medium",
            failure_type="asr_regression",
            baseline_run_id=baseline_run.id,
            current_run_id=current_run.id,
            test_case_id=worst_test_case.id,
            baseline_result_id=worst_baseline_result.id,
            current_result_id=worst_current_result.id,
            summary=comparison_summary,
            engineer_notes=None,
            ai_suggestion=(
                f"Start with {worst_test_case.title}. Inspect the transcript diff, "
                "confirm the reference transcript, then check whether the model changed "
                "number handling, domain vocabulary, or decoding behavior."
            ),
        )
        db.add(debug_case)

        db.commit()
        db.refresh(project)
        db.refresh(comparison)
        db.refresh(debug_case)

        print("Phase 1 validation data created successfully.")
        print(f"Project ID: {project.id}")
        print(f"Project name: {project.name}")
        print(f"Baseline run ID: {baseline_run.id}")
        print(f"Current run ID: {current_run.id}")
        print(f"Comparison ID: {comparison.id}")
        print(f"Debug case ID: {debug_case.id}")
        print("Open http://localhost:5173 and select this project from the dashboard.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
