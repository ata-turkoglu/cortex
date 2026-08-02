# Phase 5 — Document Ingestion

## Goal

Implement upload, validation, Docling parsing, normalized Markdown storage, metadata extraction, chunking, deduplication, and document lifecycle.

## Checklist

- [x] Support `.md`, `.txt`, `.docx`, and `.pdf`.
- [x] Implement multi-file upload.
- [x] Implement folder-aware uploads.
- [x] Store original source files unchanged.
- [x] Store normalized Markdown separately.
- [x] Integrate Docling.
- [ ] Integrate Docling with LlamaIndex document/node processing where appropriate.
- [x] Implement file hash and normalized-content hash.
- [x] Reject exact duplicates safely.
- [x] Create new document versions for changed content.
- [x] Preserve logical document IDs.
- [ ] Implement document lifecycle states.
- [ ] Implement metadata extraction through layer-specific provider assignment.
- [x] Store metadata origin as system, extracted, or user.
- [x] Implement user metadata correction precedence.
- [x] Implement Cortex chunk creation.
- [x] Persist parent/neighbor/heading relationships.
- [x] Create ingestion workflow definition.
- [ ] Make ingestion resumable and idempotent.
- [ ] Add tests with all supported formats.
- [x] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [x] Original and normalized files are both available.
- [x] Re-uploading an identical file does not duplicate content.
- [x] Changed content creates a new version.
- [ ] Failed parsing exposes sanitized technical details.
- [ ] Page navigation does not stop ingestion.

## Additional checklist

- [x] Add configurable maximum upload size.
- [x] Validate extension and MIME/content type.
- [x] Normalize filenames.
- [x] Prevent path traversal.
- [x] Use unique safe storage names.
- [ ] Handle corrupt files with structured errors.
- [ ] Handle encrypted/password-protected files with structured errors.
- [x] Ensure uploaded content is never executed.
- [x] Document that external file watching is out of scope for V1.
- [x] Add upload security tests.
