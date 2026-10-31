from pathlib import Path
from subprocess import CompletedProcess

from app.evaluation.production import (
    PRODUCTION_CASE_ID,
    PRODUCTION_SUITE_VERSION,
    ProductionEvaluationRunner,
)


def test_production_evaluation_emits_passing_cutover_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.evaluation.production.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, stdout="1 passed", stderr=""),
    )
    report = ProductionEvaluationRunner(backend_root=Path(tmp_path)).run()
    assert report["runtime"] == "v2"
    assert report["suite"] == PRODUCTION_SUITE_VERSION
    assert report["case_id"] == PRODUCTION_CASE_ID
    assert report["passed"] is True
    assert report["evaluation"] == {
        "suite_version": PRODUCTION_SUITE_VERSION,
        "total_cases": 1,
        "passed_cases": 1,
        "score": 1.0,
        "minimum_score": 1.0,
        "mandatory_failures": [],
    }


def test_production_evaluation_turns_a_failed_acceptance_into_a_rejected_gate(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "app.evaluation.production.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args[0], 1, stdout="1 failed", stderr="details"),
    )
    report = ProductionEvaluationRunner(backend_root=Path(tmp_path)).run()
    assert report["passed"] is False
    assert report["returncode"] == 1
    assert report["evaluation"] == {
        "suite_version": PRODUCTION_SUITE_VERSION,
        "total_cases": 1,
        "passed_cases": 0,
        "score": 0.0,
        "minimum_score": 1.0,
        "mandatory_failures": [PRODUCTION_CASE_ID],
    }
