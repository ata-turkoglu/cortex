import pytest

from app.core.uploads import UploadValidationError, store_upload
from app.ingestion.parsers import DocumentParseError, parse_to_markdown


@pytest.mark.parametrize(
    ("filename", "media_type", "content"),
    [
        ("valid.pdf", "application/pdf", b"%PDF-1.7\n"),
        (
            "valid.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"PK\x03\x04",
        ),
    ],
)
def test_binary_upload_signatures_are_accepted_before_worker_parsing(
    tmp_path, filename, media_type, content
):
    assert store_upload(tmp_path, filename, media_type, content, 1024).storage_path.exists()


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("corrupt.pdf", b"%PDF-1.7\nthis is not a PDF document"),
        ("encrypted.pdf", b"%PDF-1.7\n/Encrypt 1 0 R\n%%EOF"),
        ("corrupt.docx", b"PK\x03\x04not-a-valid-office-archive"),
    ],
)
def test_corrupt_or_encrypted_binary_documents_return_structured_parse_errors(
    tmp_path, filename, content
):
    source = tmp_path / filename
    source.write_bytes(content)
    with pytest.raises(DocumentParseError, match="document parsing failed"):
        parse_to_markdown(source, filename)


def test_mime_and_path_validation_remain_enforced_for_supported_extensions(tmp_path):
    with pytest.raises(UploadValidationError, match="invalid MIME type"):
        store_upload(tmp_path, "notes.txt", "application/pdf", b"content", 1024)
    with pytest.raises(UploadValidationError, match="invalid filename"):
        store_upload(tmp_path, "../notes.pdf", "application/pdf", b"%PDF-1.7", 1024)
