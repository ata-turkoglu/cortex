"""Version-tolerant GraphRAG boundary.

Canonical Microsoft GraphRAG parquet/json outputs stay under each workspace root. Cortex
only reads normalized artifacts and mirrors vectors through the Qdrant adapter.
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

import networkx as nx
import yaml

from ..core.config import get_settings
from ..core.secrets import SecretStore
from ..retrieval.hybrid import result_for
from ..retrieval.schemas import AnswerState, Evidence, RetrievalResult


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

    def query(self, graph_root: Path, config_path: Path, route: GraphRoute, query: str) -> str: ...


class GraphRAGExecutionError(RuntimeError):
    pass


class MicrosoftGraphRAGRunner:
    """Run the supported GraphRAG CLI from a worker-owned Python environment."""

    def _run(self, arguments: list[str], graph_root: Path) -> str:
        settings = get_settings()
        graph_layers = (
            "graphrag_extraction",
            "graphrag_claims",
            "graphrag_community",
            "graphrag_local",
            "graphrag_global",
            "graphrag_drift",
        )
        if any(getattr(settings, f"{layer}_provider") == "openai" for layer in graph_layers):
            api_key = settings.openai_api_key or SecretStore().get("openai_api_key")
            if not api_key:
                raise GraphRAGExecutionError("OpenAI provider credential is not configured")
        else:
            api_key = "ollama"
        backend_root = str(Path(__file__).resolve().parents[2])
        python_path = os.pathsep.join(
            value for value in (backend_root, os.environ.get("PYTHONPATH")) if value
        )
        environment = {**os.environ, "GRAPHRAG_API_KEY": api_key, "PYTHONPATH": python_path}
        completed = subprocess.run(
            [sys.executable, "-m", "app.graphrag.cli", *arguments],
            cwd=graph_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            # Rich-formatted tracebacks put the actionable exception at the end. Keep a bounded
            # tail so workflow diagnostics show the cause without persisting an unbounded CLI log.
            raise GraphRAGExecutionError(
                detail[-1500:] if detail else "Microsoft GraphRAG command failed"
            )
        return completed.stdout.strip()

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

    def query(self, graph_root: Path, config_path: Path, route: GraphRoute, query: str) -> str:
        return self._run(
            [
                "query",
                "--root",
                str(graph_root),
                "--config",
                str(config_path),
                "--data",
                str(graph_root / "output"),
                "--method",
                route.value,
                "--query",
                query,
                "--no-streaming",
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
        models["default_chat_model"] = default_chat
        assignments = {
            "graphrag_extraction": (
                ("extract_graph", "model_id"),
                ("summarize_descriptions", "model_id"),
            ),
            "graphrag_claims": (("extract_claims", "model_id"),),
            "graphrag_community": (("community_reports", "model_id"),),
            "graphrag_local": (("local_search", "chat_model_id"),),
            "graphrag_global": (("global_search", "chat_model_id"),),
            "graphrag_drift": (("drift_search", "chat_model_id"),),
        }
        for layer, targets in assignments.items():
            if layer == "graphrag_claims" and not settings.graphrag_claims_enabled:
                continue
            model_id = f"cortex_{layer}"
            model = dict(default_chat)
            model["model"] = getattr(settings, f"{layer}_model")
            if getattr(settings, f"{layer}_provider") == "ollama":
                model["api_base"] = f"{settings.ollama_base_url.rstrip('/')}/v1"
            else:
                model.pop("api_base", None)
            models[model_id] = model
            for section, key in targets:
                configured.setdefault(section, {})[key] = model_id
        configured.setdefault("extract_claims", {})["enabled"] = settings.graphrag_claims_enabled
        drift = configured.setdefault("drift_search", {})
        drift.update(
            {
                "n_depth": settings.graphrag_drift_n_depth,
                "drift_k_followups": settings.graphrag_drift_k_followups,
                "primer_folds": settings.graphrag_drift_primer_folds,
                "concurrency": settings.graphrag_drift_concurrency,
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

    def query(self, route: GraphRoute, query: str, limit: int = 10) -> RetrievalResult:
        if not self.graph_root.exists():
            return result_for([], "graph_not_indexed")
        output_root = self.graph_root / "output"
        if self.config_path is not None and any(output_root.rglob("*.parquet")):
            try:
                answer = self.runner.query(self.graph_root, self.config_path, route, query)
            except GraphRAGExecutionError:
                return result_for([], "graph_stale")
            evidence = (
                Evidence(
                    self.workspace_id,
                    f"graphrag:{route.value}",
                    answer,
                    1.0,
                    citation_label="Microsoft GraphRAG",
                ),
            )
            return RetrievalResult(evidence, AnswerState.GROUNDED)
        resource_type = "entities" if route is GraphRoute.LOCAL else "reports"
        words = set(query.casefold().split())
        candidates = self.load_artifacts(resource_type)
        scored = sorted(
            ((len(words & set(item.text.casefold().split())), item) for item in candidates),
            reverse=True,
            key=lambda pair: pair[0],
        )
        evidence = [
            Evidence(
                self.workspace_id,
                f"graphrag:{route.value}",
                item.text,
                float(score),
                document_id=(self.logical_document_ids_for(item) or (None,))[0],
                citation_label=item.attributes.get("title"),
                metadata={
                    **item.attributes,
                    "logical_document_ids": ",".join(self.logical_document_ids_for(item)),
                },
            )
            for score, item in scored[:limit]
            if score
        ]
        return result_for(evidence, "graph_stale" if not evidence else None)

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
