import json
from pathlib import Path

from app.evaluation.runner import CaseResult, EvaluationRunner, compare_baseline, load_suite


def test_golden_suite_exercises_production_chat_orchestration():
    suite = load_suite(Path(__file__).parents[1] / "evaluation" / "golden.json")

    report = EvaluationRunner(suite).run()

    assert report["summary"]["cases"] >= 10
    assert report["summary"]["failed"] == 0
    assert report["summary"]["retrieval"]["eligible_cases"] > 0


def test_golden_suite_supports_tag_and_case_filters():
    suite = load_suite(Path(__file__).parents[1] / "evaluation" / "golden.json")

    report = EvaluationRunner(suite).run(tag="aggregation", case_id="property-count-001")

    assert report["summary"]["cases"] == 1
    assert report["cases"][0]["id"] == "property-count-001"


def test_rank_sensitive_metrics_use_ordered_results():
    metrics = EvaluationRunner._metrics(("a", "b"), ["x", "b", "a"], {1: 0, 3: 1})

    assert metrics["expected_document_rank"] == 2
    assert metrics["rr"] == 0.5
    assert metrics["recall_at"] == {"1": 0.0, "3": 1.0}


def test_baseline_rejects_incompatible_fixture(tmp_path):
    report = EvaluationRunner(
        load_suite(Path(__file__).parents[1] / "evaluation" / "golden.json")
    ).run(case_id="bm25-rare-token-001")
    baseline = {**report, "provenance": {**report["provenance"], "fixture_digest": "other"}}
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")

    compared = compare_baseline(report, path)

    assert compared["baseline"]["status"] == "BASELINE_INCOMPATIBLE"


def test_aggregate_metrics_exclude_unlabelled_cases():
    suite = load_suite(Path(__file__).parents[1] / "evaluation" / "golden.json")
    results = [
        CaseResult(
            "a",
            "passed",
            True,
            [],
            0,
            {
                "eligible": True,
                "rr": 1.0,
                "hit_at": {"1": True},
                "recall_at": {"1": 1.0},
                "expected_document_rank": 1,
            },
            {},
        ),
        CaseResult(
            "b",
            "passed",
            True,
            [],
            0,
            {
                "eligible": True,
                "rr": 0.5,
                "hit_at": {"1": False},
                "recall_at": {"1": 0.0},
                "expected_document_rank": 2,
            },
            {},
        ),
        CaseResult(
            "c",
            "passed",
            True,
            [],
            0,
            {"eligible": False, "rr": None, "hit_at": {}, "recall_at": {}},
            {},
        ),
    ]
    report = EvaluationRunner(suite)._report(results)

    assert report["summary"]["retrieval"] == {
        "eligible_cases": 2,
        "excluded_cases": 1,
        "mrr": 0.75,
        "hit_at": {"1": 0.5},
        "recall_at": {"1": 0.5},
    }


def test_metric_only_baseline_regression_fails(tmp_path):
    provenance = {
        "suite_id": "s",
        "suite_version": 1,
        "fixture_digest": "f",
        "benchmark_kind": "synthetic",
        "pack_id": "p",
        "embedding_config_fingerprint": "e",
        "retrieval_config_fingerprint": "r",
        "semantic_scorer_version": "v",
    }
    baseline = {
        "provenance": provenance,
        "cases": [
            {
                "id": "case",
                "passed": True,
                "status": "passed",
                "retrieval": {
                    "expected_document_rank": 2,
                    "rr": 0.5,
                    "recall_at": {"5": 1.0},
                    "hit_at": {"5": True},
                },
            }
        ],
    }
    current = {
        "provenance": provenance,
        "baseline_policy": {},
        "cases": [
            {
                "id": "case",
                "passed": True,
                "status": "passed",
                "retrieval": {
                    "expected_document_rank": 5,
                    "rr": 0.2,
                    "recall_at": {"5": 0.5},
                    "hit_at": {"5": True},
                },
            }
        ],
    }
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")

    compared = compare_baseline(current, path)

    assert compared["baseline"]["passed"] is False
    assert compared["baseline"]["case_diffs"][0]["status"] == "REGRESSION"
