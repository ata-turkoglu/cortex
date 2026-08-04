import json
from pathlib import Path
from time import perf_counter

from app.ingestion.chunking import chunk_markdown


def test_retrieval_benchmark_fixture_has_versioned_latency_expectations():
    fixture = Path(__file__).parent / "fixtures" / "retrieval_benchmark.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert all(case["workspace_id"] and case["max_latency_ms"] > 0 for case in payload["cases"])


def test_representative_five_thousand_document_chunking_baseline():
    """Detect accidental quadratic behavior in the first ingestion-stage boundary."""
    started = perf_counter()
    document = "# Baseline\n" + "Ankara Türkiye'nin başkentidir. " * 20
    chunk_count = sum(
        len(chunk_markdown(document, token_limit=500, overlap=50)) for _ in range(5_000)
    )
    elapsed_seconds = perf_counter() - started
    assert chunk_count == 5_000
    assert elapsed_seconds < 10
