"""Version-tolerant GraphRAG boundary.

Canonical Microsoft GraphRAG parquet/json outputs stay under each workspace root. Cortex
only reads normalized artifacts and mirrors vectors through the Qdrant adapter.
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

import networkx as nx
import yaml

from ..core.config import get_settings
from ..core.secrets import SecretStore


class GraphRoute(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"
    DRIFT = "drift"


@dataclass(frozen=True)
class GraphArtifact:
    artifact_id: str
    resource_type: str
    text: str
    attributes: dict[str, str]


class GraphRAGCommandRunner(Protocol):
    def initialize(self, graph_root: Path) -> Path: ...

    def index(self, graph_root: Path, config_path: Path, method: str = "standard") -> None: ...


logger = logging.getLogger(__name__)


class GraphRAGExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphRAGSourceReference:
    """Immutable source identity attached to a normalized GraphRAG artifact.

    V2 deliberately does not accept the Microsoft CLI's generated answer string:
    GraphRAG artifacts must identify one Cortex source chunk before they can cross
    the Result & Evidence boundary.
    """

    workspace_id: str
    generation_id: str
    document_id: str
    document_version_id: str
    logical_document_id: str
    chunk_id: str
    content_hash: str


@dataclass(frozen=True)
class GraphRAGFindingCandidate:
    mode: GraphRoute
    artifact_id: str
    text: str
    source: GraphRAGSourceReference
    score: float


def _as_list(value) -> list[object]:
    """Normalize a parquet list cell (list, tuple, or numpy array) to a Python list."""
    if value is None or isinstance(value, str | bytes):
        return []
    try:
        return list(value)
    except TypeError:
        return []


def route_model_family(model: dict[str, object], provider: str) -> dict[str, object]:
    """Route OpenAI GPT-5 family models through GraphRAG's LiteLLM chat provider.

    GraphRAG 2.6's ``openai_chat`` provider recognizes only o1/o1-mini/o3-mini as
    reasoning models and sends ``max_tokens`` to every other model, which GPT-5 family
    models reject. LiteLLM maps it to ``max_completion_tokens`` for these models.
    """
    if provider == "openai" and "gpt-5" in str(model.get("model", "")):
        model["type"] = "chat"
        model["model_provider"] = "openai"
    else:
        model["type"] = "openai_chat"
        model.pop("model_provider", None)
    return model


def graphrag_api_key() -> str:
    """Return the credential GraphRAG's ``${GRAPHRAG_API_KEY}`` setting must resolve to."""
    settings = get_settings()
    graph_layers = (
        "graphrag_extraction",
        "graphrag_community",
        "graphrag_global",
        "graphrag_drift",
    )
    if not any(getattr(settings, f"{layer}_provider") == "openai" for layer in graph_layers):
        return "ollama"
    api_key = settings.openai_api_key or SecretStore().get("openai_api_key")
    if not api_key:
        raise GraphRAGExecutionError("OpenAI provider credential is not configured")
    return api_key


class MicrosoftGraphRAGRunner:
    """Run the supported GraphRAG CLI from a worker-owned Python environment."""

    def _run(self, arguments: list[str], graph_root: Path) -> str:
        settings = get_settings()
        api_key = graphrag_api_key()
        backend_root = str(Path(__file__).resolve().parents[2])
        python_path = os.pathsep.join(
            value for value in (backend_root, os.environ.get("PYTHONPATH")) if value
        )
        environment = {**os.environ, "GRAPHRAG_API_KEY": api_key, "PYTHONPATH": python_path}
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "app.graphrag.cli", *arguments],
                cwd=graph_root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                # GraphRAG and its dependencies can emit Windows-console encoded diagnostics.
                # Never let an undecodable diagnostic crash subprocess's reader thread and hide the
                # actual upstream failure behind a secondary NoneType.strip AttributeError.
                errors="replace",
                env=environment,
                timeout=settings.graphrag_command_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise GraphRAGExecutionError(
                "GraphRAG command exceeded its configured "
                f"{settings.graphrag_command_timeout_seconds}s deadline"
            ) from exc
        if completed.returncode:
            detail = (completed.stderr or "").strip() or (completed.stdout or "").strip()
            # Rich-formatted tracebacks put the actionable exception at the end. Keep a bounded
            # tail so workflow diagnostics show the cause without persisting an unbounded CLI log.
            raise GraphRAGExecutionError(
                detail[-1500:] if detail else "Microsoft GraphRAG command failed"
            )
        return (completed.stdout or "").strip()

    def initialize(self, graph_root: Path) -> Path:
        self._run(["init", "--root", str(graph_root)], graph_root)
        config_path = graph_root / "settings.yaml"
        if not config_path.is_file():
            raise GraphRAGExecutionError("GraphRAG initialization did not create settings.yaml")
        return config_path

    def index(self, graph_root: Path, config_path: Path, method: str = "standard") -> None:
        if method not in {"standard", "fast", "standard-update", "fast-update"}:
            raise ValueError("unsupported GraphRAG indexing method")
        self._run(
            [
                "index",
                "--root",
                str(graph_root),
                "--config",
                str(config_path),
                "--method",
                method,
            ],
            graph_root,
        )


class GraphRAGAdapter:
    def __init__(
        self,
        workspace_id: str,
        graph_root: Path,
        *,
        config_path: Path | None = None,
        runner: GraphRAGCommandRunner | None = None,
    ) -> None:
        self.workspace_id, self.graph_root = workspace_id, graph_root
        self.last_search_usage = None
        self.config_path = config_path
        self.runner = runner or MicrosoftGraphRAGRunner()

    def ensure_root(self) -> Path:
        self.graph_root.mkdir(parents=True, exist_ok=True)
        (self.graph_root / "input").mkdir(exist_ok=True)
        (self.graph_root / "output").mkdir(exist_ok=True)
        return self.graph_root

    def initialize(self) -> Path:
        self.ensure_root()
        self.config_path = self.runner.initialize(self.graph_root)
        return self.config_path

    def index(self, method: str = "standard") -> None:
        if self.config_path is None:
            raise GraphRAGExecutionError("GraphRAG configuration is required before indexing")
        self.ensure_root()
        self._configure_generated_settings()
        self.runner.index(self.graph_root, self.config_path, method)

    def _configure_generated_settings(self) -> None:
        """Keep GraphRAG's generated configuration aligned with Cortex's selected model.

        Credentials are deliberately not written to this workspace file: the runner receives
        them only through its process environment.
        """
        if self.config_path is None or not self.config_path.is_file():
            return
        settings = get_settings()
        content = self.config_path.read_text(encoding="utf-8")
        configured = yaml.safe_load(content) or {}
        configured.pop("model", None)
        models = configured.setdefault("models", {})
        default_chat = dict(models.get("default_chat_model", {}))
        if not default_chat:
            # This preserves compatibility with older/generated minimal settings files.
            default_chat = {
                "type": "openai_chat",
                "auth_type": "api_key",
                "model_supports_json": True,
            }
        # GraphRAG validates default_chat_model before it reaches stage-specific model IDs.
        # Never leave the upstream `graphrag init` placeholder (for example
        # gpt-4-turbo-preview) here: it may be retired or unavailable to the user.
        default_chat["model"] = settings.graphrag_extraction_model
        if settings.graphrag_extraction_provider == "ollama":
            default_chat["api_base"] = f"{settings.ollama_base_url.rstrip('/')}/v1"
        else:
            default_chat.pop("api_base", None)
        default_chat["encoding_model"] = "cl100k_base"
        default_chat["max_tokens"] = 4096
        models["default_chat_model"] = route_model_family(
            dict(default_chat), settings.graphrag_extraction_provider
        )
        assignments = {
            "graphrag_extraction": (
                ("extract_graph", "model_id"),
                ("summarize_descriptions", "model_id"),
            ),
            "graphrag_community": (("community_reports", "model_id"),),
            "graphrag_global": (("global_search", "chat_model_id"),),
            "graphrag_drift": (("drift_search", "chat_model_id"),),
        }
        for layer, targets in assignments.items():
            model_id = f"cortex_{layer}"
            model = dict(default_chat)
            model["model"] = getattr(settings, f"{layer}_model")
            if getattr(settings, f"{layer}_provider") == "ollama":
                model["api_base"] = f"{settings.ollama_base_url.rstrip('/')}/v1"
            else:
                model.pop("api_base", None)
            models[model_id] = route_model_family(model, getattr(settings, f"{layer}_provider"))
            for section, key in targets:
                configured.setdefault(section, {})[key] = model_id
        # V2 runs only GraphRAG's selection step (``smart_search``). Local selection uses
        # embeddings alone, so local search reuses the extraction model only to satisfy
        # GraphRAG's config validation; it is never called.
        configured.setdefault("local_search", {})["chat_model_id"] = "cortex_graphrag_extraction"
        # No V2 component reads GraphRAG covariates, so claim extraction would be paid for and
        # discarded.
        configured.setdefault("extract_claims", {})["enabled"] = False
        # Text-unit vectors serve GraphRAG's basic search only; V2 never runs it.
        configured.setdefault("embed_text", {})["names"] = [
            "entity.description",
            "community.full_content",
        ]
        drift = configured.setdefault("drift_search", {})
        drift.update(
            {
                "drift_k_followups": settings.graphrag_drift_k_followups,
                "primer_folds": settings.graphrag_drift_primer_folds,
            }
        )
        # Cortex materializes one normalized Markdown file per logical document.
        # GraphRAG's supported `text` loader is extension-agnostic only when its
        # file pattern is explicit; its generated default otherwise targets .txt.
        input_settings = configured.setdefault("input", {})
        input_settings["file_type"] = "text"
        input_settings["file_pattern"] = r".*\.md\Z"
        embedding = models.get("default_embedding_model")
        if not isinstance(embedding, dict):
            embedding = {}
            models["default_embedding_model"] = embedding
        embedding["model"] = settings.embedding_model
        # Ollama embedding model identifiers are not in tiktoken's model map.
        # GraphRAG only needs a compatible tokenizer for chunk budgeting, so keep
        # that concern separate from the actual embedding provider/model.
        embedding["encoding_model"] = "cl100k_base"
        if settings.embedding_provider == "ollama":
            embedding["api_base"] = f"{settings.ollama_base_url.rstrip('/')}/v1"
        else:
            embedding.pop("api_base", None)
        self.config_path.write_text(
            yaml.safe_dump(configured, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def load_artifacts(self, resource_type: str) -> list[GraphArtifact]:
        artifact_file = self.graph_root / f"{resource_type}.json"
        if artifact_file.exists():
            payload = json.loads(artifact_file.read_text(encoding="utf-8"))
            return [
                GraphArtifact(
                    artifact_id=str(row["id"]),
                    resource_type=resource_type,
                    text=str(row.get("text", "")),
                    attributes={
                        str(key): str(value) for key, value in row.get("attributes", {}).items()
                    },
                )
                for row in payload
            ]
        return self._load_native_parquet(resource_type)

    @staticmethod
    def _attribute_ids(value: str | None) -> set[str]:
        if not value:
            return set()
        try:
            decoded = json.loads(value.replace("'", '"'))
        except (json.JSONDecodeError, AttributeError):
            decoded = re.findall(r"[0-9a-fA-F-]{8,}", value)
        if isinstance(decoded, list):
            return {str(item) for item in decoded}
        return {str(decoded)}

    def logical_document_ids_for(self, artifact: GraphArtifact) -> tuple[str, ...]:
        """Resolve GraphRAG entity/text-unit provenance back to logical documents."""
        direct = self._attribute_ids(
            artifact.attributes.get("logical_document_ids")
            or artifact.attributes.get("logical_document_id")
        )
        if direct:
            return tuple(sorted(direct))

        document_map: dict[str, str] = {}
        for document in self.load_artifacts("documents"):
            searchable = f"{document.text}\n{json.dumps(document.attributes)}"
            match = re.search(r"Logical document ID:\s*([0-9a-fA-F-]{8,})", searchable)
            if match:
                document_map[document.artifact_id] = match.group(1)

        document_ids = self._attribute_ids(artifact.attributes.get("document_ids"))
        if artifact.resource_type == "documents":
            document_ids.add(artifact.artifact_id)
        if artifact.resource_type == "entities":
            text_unit_ids = self._attribute_ids(artifact.attributes.get("text_unit_ids"))
            for text_unit in self.load_artifacts("text_units"):
                if text_unit.artifact_id in text_unit_ids:
                    document_ids.update(
                        self._attribute_ids(text_unit.attributes.get("document_ids"))
                    )
        return tuple(
            sorted(
                {
                    document_map[document_id]
                    for document_id in document_ids
                    if document_id in document_map
                }
            )
        )

    def _load_native_parquet(self, resource_type: str) -> list[GraphArtifact]:
        """Read GraphRAG's final parquet outputs without rewriting them.

        The upstream pipeline prefixes final artifact filenames differently by
        indexing method/version, so matching is intentionally suffix-based.
        """
        name = {"reports": "community_reports"}.get(resource_type, resource_type)
        candidates = sorted((self.graph_root / "output").rglob(f"*{name}*.parquet"))
        if not candidates:
            return []
        import pandas as pd

        rows = pd.read_parquet(candidates[-1]).to_dict(orient="records")
        artifacts: list[GraphArtifact] = []
        for row in rows:
            artifact_id = row.get("id") or row.get("entity_id") or row.get("human_readable_id")
            if artifact_id is None:
                continue
            text = next(
                (
                    str(row[key])
                    for key in ("description", "full_content", "text", "summary", "title")
                    if row.get(key) is not None
                ),
                "",
            )
            attributes = {
                str(key): str(value)
                for key, value in row.items()
                if value is not None and key not in {"description", "full_content", "text"}
            }
            artifacts.append(GraphArtifact(str(artifact_id), resource_type, text, attributes))
        return artifacts

    def query_findings(
        self,
        route: GraphRoute,
        query: str,
        generation_id: str,
        limit: int = 10,
        *,
        sources: Mapping[str, object] | None = None,
        smart: bool = False,
    ) -> tuple[GraphRAGFindingCandidate, ...]:
        """Return only artifact findings with complete Cortex source identities.

        This intentionally bypasses ``runner.query``.  Its output is a native
        answer with no exact chunk references and is therefore untrusted in V2.
        An artifact either declares its Cortex identity explicitly, or it is traced
        through GraphRAG's own text units to the ``<chunk_id>.md`` input document the
        production stage wrote for each Cortex chunk.  The content hash is computed
        from the text GraphRAG indexed, so the bridge rejects any finding whose indexed
        text differs from the trusted manifest.  Anything else yields no finding.

        With ``smart``, GraphRAG's own context selection for the route chooses the
        artifacts (see ``smart_search``); its usage is kept in ``last_search_usage``.
        Any smart-selection failure falls back to lexical selection.
        """
        resource_type = "entities" if route is GraphRoute.LOCAL else "reports"
        artifacts = self.load_artifacts(resource_type)
        self.last_search_usage = None
        scored = self._smart_scored(route, query, limit, artifacts) if smart and sources else None
        if scored is None:
            words = set(query.casefold().split())
            scored = sorted(
                (
                    (len(words & set(item.text.casefold().split())), item)
                    for item in artifacts
                ),
                reverse=True,
                key=lambda pair: pair[0],
            )
        native = self._native_chunk_provenance(resource_type) if sources else {}
        findings: list[GraphRAGFindingCandidate] = []
        for score, item in scored:
            if not score or len(findings) >= limit:
                continue
            reference = self._declared_reference(item) or self._native_reference(
                native.get(item.artifact_id, ()), sources or {}, generation_id
            )
            if reference is None:
                continue
            findings.append(
                GraphRAGFindingCandidate(
                    mode=route,
                    artifact_id=item.artifact_id,
                    text=item.text,
                    source=reference,
                    score=min(1.0, float(score)),
                )
            )
        return tuple(findings)

    def _smart_scored(
        self, route: GraphRoute, query: str, limit: int, artifacts: list[GraphArtifact]
    ) -> list[tuple[float, GraphArtifact]] | None:
        from .smart_search import graphrag_available, select_context

        if not graphrag_available():
            return None
        try:
            selection = select_context(self.graph_root, route, query, get_settings(), limit)
        except Exception:
            logger.warning(
                "GraphRAG %s smart selection failed; using lexical selection",
                route.value,
                exc_info=True,
            )
            return None
        self.last_search_usage = selection
        by_id = {item.artifact_id: item for item in artifacts}
        ranked = [by_id[value] for value in selection.artifact_ids if value in by_id]
        # Selection order is GraphRAG's relevance order; keep it as a descending score.
        return [(1.0 - index / (len(ranked) + 1), item) for index, item in enumerate(ranked)]

    @staticmethod
    def _declared_reference(item: GraphArtifact) -> GraphRAGSourceReference | None:
        required = (
            "workspace_id",
            "knowledge_generation_id",
            "document_id",
            "document_version_id",
            "logical_document_id",
            "chunk_id",
            "content_hash",
        )
        if not all(item.attributes.get(key) for key in required):
            return None
        return GraphRAGSourceReference(
            workspace_id=item.attributes["workspace_id"],
            generation_id=item.attributes["knowledge_generation_id"],
            document_id=item.attributes["document_id"],
            document_version_id=item.attributes["document_version_id"],
            logical_document_id=item.attributes["logical_document_id"],
            chunk_id=item.attributes["chunk_id"],
            content_hash=item.attributes["content_hash"],
        )

    @staticmethod
    def _native_reference(
        chunks: tuple[tuple[str, str], ...], sources: Mapping[str, object], generation_id: str
    ) -> GraphRAGSourceReference | None:
        for chunk_id, content_hash in chunks:
            source = sources.get(chunk_id)
            if source is None or getattr(source, "generation_id", None) != generation_id:
                continue
            return GraphRAGSourceReference(
                workspace_id=source.workspace_id,
                generation_id=source.generation_id,
                document_id=source.document_id,
                document_version_id=source.document_version_id,
                logical_document_id=source.logical_document_id,
                chunk_id=chunk_id,
                content_hash=content_hash,
            )
        return None

    def _native_rows(self, name: str) -> list[dict[str, object]]:
        candidates = sorted((self.graph_root / "output").rglob(f"*{name}.parquet"))
        if not candidates:
            return []
        import pandas as pd

        return pd.read_parquet(candidates[-1]).to_dict(orient="records")

    def _native_chunk_provenance(
        self, resource_type: str
    ) -> dict[str, tuple[tuple[str, str], ...]]:
        """Map native entity/report IDs to the Cortex chunks GraphRAG indexed them from."""
        documents = {
            str(row["id"]): (
                str(row.get("title") or "").removesuffix(".md"),
                hashlib.sha256(str(row.get("text") or "").encode("utf-8")).hexdigest(),
            )
            for row in self._native_rows("documents")
            if row.get("id") is not None
        }
        units = {
            str(row["id"]): tuple(
                documents[str(document_id)]
                for document_id in _as_list(row.get("document_ids"))
                if str(document_id) in documents
            )
            for row in self._native_rows("text_units")
            if row.get("id") is not None
        }

        def chunks_for(text_unit_ids) -> tuple[tuple[str, str], ...]:
            return tuple(
                dict.fromkeys(
                    chunk for unit in _as_list(text_unit_ids) for chunk in units.get(str(unit), ())
                )
            )

        if resource_type == "entities":
            return {
                str(row["id"]): chunks_for(row.get("text_unit_ids"))
                for row in self._native_rows("entities")
                if row.get("id") is not None
            }
        communities = {
            str(row.get("community")): row.get("text_unit_ids")
            for row in self._native_rows("communities")
        }
        return {
            str(row["id"]): chunks_for(communities.get(str(row.get("community"))))
            for row in self._native_rows("community_reports")
            if row.get("id") is not None
        }

    def rebuild_networkx(self) -> nx.MultiDiGraph:
        graph = nx.MultiDiGraph()
        for entity in self.load_artifacts("entities"):
            graph.add_node(entity.artifact_id, **entity.attributes, text=entity.text)
        for relationship in self.load_artifacts("relationships"):
            source = relationship.attributes.get("source")
            target = relationship.attributes.get("target")
            if source and target:
                graph.add_edge(
                    source,
                    target,
                    key=relationship.artifact_id,
                    **relationship.attributes,
                )
        nx.write_graphml(graph, self.ensure_root() / "networkx.graphml")
        return graph
