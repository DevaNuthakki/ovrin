from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, routes, schemas
from app.database import Base


def build_test_database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    test_session = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    return test_session(), engine


def seed_comparison(db):
    project = models.Project(
        name="Release safety test project",
        description="Tests policy-based release decisions.",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    baseline_run = models.EvaluationRun(
        project_id=project.id,
        run_name="baseline",
        model_name="baseline-model",
        status="completed",
    )
    current_run = models.EvaluationRun(
        project_id=project.id,
        run_name="candidate",
        model_name="candidate-model",
        status="completed",
    )

    db.add_all([baseline_run, current_run])
    db.commit()
    db.refresh(baseline_run)
    db.refresh(current_run)

    comparison = models.RunComparison(
        baseline_run_id=baseline_run.id,
        current_run_id=current_run.id,
        baseline_average_wer=0.17,
        current_average_wer=0.21,
        wer_delta=0.04,
        baseline_average_cer=0.10,
        current_average_cer=0.13,
        cer_delta=0.03,
        comparison_status="regression",
        summary="Regression detected.",
    )

    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    return project, comparison


def test_release_report_creates_default_policy():
    db, engine = build_test_database()

    try:
        project, comparison = seed_comparison(db)

        report = routes.create_release_report(
            comparison_id=comparison.id,
            db=db,
        )

        assert report.project_id == project.id
        assert report.status == "fail"
        assert report.severity == "critical"
        assert len(report.checks) == 4

        policy = routes.get_release_policy(
            project_id=project.id,
            db=db,
        )

        assert policy.name == "Default release policy"
        assert policy.version == 1
        assert report.policy_snapshot["version"] == 1
    finally:
        db.close()
        engine.dispose()


def test_policy_update_refreshes_existing_release_report():
    db, engine = build_test_database()

    try:
        project, comparison = seed_comparison(db)

        initial_report = routes.create_release_report(
            comparison_id=comparison.id,
            db=db,
        )

        updated_policy = routes.upsert_release_policy(
            project_id=project.id,
            policy_update=schemas.ReleasePolicyUpsert(
                name="Lenient test policy",
                warn_current_wer=0.30,
                fail_current_wer=0.40,
                warn_current_cer=0.20,
                fail_current_cer=0.30,
                warn_wer_delta=0.10,
                fail_wer_delta=0.20,
                warn_cer_delta=0.10,
                fail_cer_delta=0.20,
            ),
            db=db,
        )

        refreshed_report = routes.create_release_report(
            comparison_id=comparison.id,
            db=db,
        )

        stored_report = routes.get_release_report(
            comparison_id=comparison.id,
            db=db,
        )

        assert updated_policy.version == 2
        assert refreshed_report.id == initial_report.id
        assert stored_report.id == initial_report.id
        assert refreshed_report.status == "pass"
        assert refreshed_report.severity == "none"
        assert refreshed_report.policy_snapshot["version"] == 2
        assert (
            db.query(models.ReleaseReport).count()
            == 1
        )
    finally:
        db.close()
        engine.dispose()
