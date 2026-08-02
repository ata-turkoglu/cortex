import pytest

from app.core.uploads import UploadValidationError, normalized_filename, store_upload


def test_store_upload_normalizes_name_and_hashes_text(tmp_path):
    stored = store_upload(tmp_path, "İçerik.md", "text/markdown", b"# Merhaba", 1024)
    assert stored.original_filename == "İçerik.md"
    assert stored.storage_path.exists()
    assert stored.size_bytes == 9


@pytest.mark.parametrize(
    ("filename", "media_type", "content"),
    [
        ("../escape.txt", "text/plain", b"unsafe"),
        ("tool.exe", "application/octet-stream", b"unsafe"),
        ("report.pdf", "application/pdf", b"not a PDF"),
        ("report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"bad"),
    ],
)
def test_store_upload_rejects_unsafe_or_invalid_content(tmp_path, filename, media_type, content):
    with pytest.raises(UploadValidationError):
        store_upload(tmp_path, filename, media_type, content, 1024)


def test_store_upload_enforces_size_limit(tmp_path):
    with pytest.raises(UploadValidationError):
        store_upload(tmp_path, "large.txt", "text/plain", b"12345", 4)


def test_filename_rejects_traversal():
    with pytest.raises(UploadValidationError):
        normalized_filename("..")
