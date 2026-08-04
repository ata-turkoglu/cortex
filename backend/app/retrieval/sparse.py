"""Persistent bm25s boundary; workspace corpora are never combined."""

import json
from dataclasses import dataclass
from pathlib import Path

from .schemas import Evidence


@dataclass(frozen=True)
class SparseDocument:
    chunk_id: str
    content: str
    evidence: Evidence


class WorkspaceBM25Index:
    """A workspace-scoped bm25s corpus with optional durable storage.

    The index and the serialised evidence are stored beneath one workspace-owned
    directory.  Callers must supply that directory from ``WorkspaceContext``;
    this boundary never derives another workspace's path.
    """

    DOCUMENTS_FILE = "evidence.json"

    def __init__(
        self,
        workspace_id: str,
        documents: list[SparseDocument] | None = None,
        storage_path: Path | None = None,
    ) -> None:
        if not workspace_id:
            raise ValueError("workspace_id is required for sparse retrieval")
        self.workspace_id = workspace_id
        self.documents = documents or []
        self.storage_path = storage_path
        self._retriever = None

    def build(self, documents: list[SparseDocument] | None = None) -> None:
        import bm25s

        if documents is not None:
            self.documents = documents
        corpus = [item.content for item in self.documents]
        self._retriever = bm25s.BM25()
        if corpus:
            self._retriever.index(bm25s.tokenize(corpus, stopwords=[]))

    def save(self) -> None:
        if self.storage_path is None:
            raise ValueError("storage_path is required to persist a sparse index")
        if self._retriever is None:
            self.build()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        if self.documents:
            self._retriever.save(self.storage_path, show_progress=False)
        payload = {
            "workspace_id": self.workspace_id,
            "documents": [
                {
                    "chunk_id": item.chunk_id,
                    "content": item.content,
                    "evidence": {
                        "workspace_id": item.evidence.workspace_id,
                        "source": item.evidence.source,
                        "content": item.evidence.content,
                        "score": item.evidence.score,
                        "document_id": item.evidence.document_id,
                        "document_version_id": item.evidence.document_version_id,
                        "chunk_id": item.evidence.chunk_id,
                        "citation_label": item.evidence.citation_label,
                        "metadata": item.evidence.metadata,
                    },
                }
                for item in self.documents
            ],
        }
        (self.storage_path / self.DOCUMENTS_FILE).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, workspace_id: str, storage_path: Path) -> "WorkspaceBM25Index":
        import bm25s

        payload = json.loads((storage_path / cls.DOCUMENTS_FILE).read_text(encoding="utf-8"))
        if payload.get("workspace_id") != workspace_id:
            raise ValueError("sparse index belongs to a different workspace")
        documents = [
            SparseDocument(
                chunk_id=str(item["chunk_id"]),
                content=str(item["content"]),
                evidence=Evidence(**item["evidence"]),
            )
            for item in payload["documents"]
        ]
        index = cls(workspace_id, documents, storage_path)
        if documents:
            index._retriever = bm25s.BM25.load(storage_path, load_corpus=False)
        return index

    def search(self, query: str, limit: int) -> list[Evidence]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not self.documents:
            return []
        if self._retriever is None:
            self.build()
        import bm25s

        results, scores = self._retriever.retrieve(
            bm25s.tokenize([query], stopwords=[]),
            k=min(limit, len(self.documents)),
            show_progress=False,
        )
        return [
            Evidence(**{**self.documents[int(index)].evidence.__dict__, "score": float(score)})
            for index, score in zip(results[0], scores[0], strict=True)
        ]
