import json
from pathlib import Path


def test_starter_evaluation_fixture_uses_the_versioned_contract():
    fixture = Path(__file__).parent / "fixtures" / "evaluation.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    required = {
        "id",
        "workspace_slug",
        "route",
        "documents",
        "facts",
        "evidence_chunk_ids",
        "answerable",
        "max_latency_ms",
        "max_estimated_cost_usd",
    }
    assert all(required <= set(case) for case in payload["cases"])
