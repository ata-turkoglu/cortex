from app.ingestion.metadata import effective_metadata


def test_user_metadata_overrides_extracted_and_system_values():
    assert effective_metadata(
        [("title", "system", "file"), ("title", "extracted", "scan"), ("title", "user", "correct")]
    ) == {"title": "correct"}
