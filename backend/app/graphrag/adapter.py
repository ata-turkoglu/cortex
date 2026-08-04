"""Version-tolerant GraphRAG boundary.

Canonical Microsoft GraphRAG parquet/json outputs stay under each workspace root. Cortex
only reads normalized artifacts and mirrors vectors through the Qdrant adapter.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

import networkx as nx

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
        completed = subprocess.run(
            [sys.executable, "-m", "graphrag", *arguments],
            cwd=graph_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise GraphRAGExecutionError(detail or "Microsoft GraphRAG command failed")
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
        self.runner.index(self.graph_root, self.config_path, method)

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
                citation_label=item.attributes.get("title"),
                metadata=item.attributes,
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
