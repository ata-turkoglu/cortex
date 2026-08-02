# Phase 5 — Document Ingestion

## Goal

Implement upload, validation, Docling parsing, normalized Markdown storage, metadata extraction, chunking, deduplication, and document lifecycle.

## Checklist

- [ ] Support `.md`, `.txt`, `.docx`, and `.pdf`.
- [ ] Implement multi-file upload.
- [ ] Implement folder-aware uploads.
- [ ] Store original source files unchanged.
- [ ] Store normalized Markdown separately.
- [ ] Integrate Docling.
- [ ] Integrate Docling with LlamaIndex document/node processing where appropriate.
- [ ] Implement file hash and normalized-content hash.
- [ ] Reject exact duplicates safely.
- [ ] Create new document versions for changed content.
- [ ] Preserve logical document IDs.
- [ ] Implement document lifecycle states.
- [ ] Implement metadata extraction through layer-specific provider assignment.
- [ ] Store metadata origin as system, extracted, or user.
- [ ] Implement user metadata correction precedence.
- [ ] Implement Cortex chunk creation.
- [ ] Persist parent/neighbor/heading relationships.
- [ ] Create ingestion workflow definition.
- [ ] Make ingestion resumable and idempotent.
- [ ] Add tests with all supported formats.
- [ ] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [ ] Original and normalized files are both available.
- [ ] Re-uploading an identical file does not duplicate content.
- [ ] Changed content creates a new version.
- [ ] Failed parsing exposes sanitized technical details.
- [ ] Page navigation does not stop ingestion.

## Additional checklist

- [ ] Add configurable maximum upload size.
- [ ] Validate extension and MIME/content type.
- [ ] Normalize filenames.
- [ ] Prevent path traversal.
- [ ] Use unique safe storage names.
- [ ] Handle corrupt files with structured errors.
- [ ] Handle encrypted/password-protected files with structured errors.
- [ ] Ensure uploaded content is never executed.
- [ ] Document that external file watching is out of scope for V1.
- [ ] Add upload security tests.
