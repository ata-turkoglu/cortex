import json
from pathlib import Path


def test_retrieval_benchmark_fixture_has_versioned_latency_expectations():
    fixture = Path(__file__).parent / "fixtures" / "retrieval_benchmark.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert all(case["workspace_id"] and case["max_latency_ms"] > 0 for case in payload["cases"])
