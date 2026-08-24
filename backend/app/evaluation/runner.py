# ruff: noqa: E501
"""Historical V1 corpus-derived deterministic regression evaluation.

The fixture adapter calculates ranks from corpus text and semantic fixture metadata.  Golden
relevance labels are consumed only after isolated historical orchestration completes. This module
is not a production acceptance gate; use ``ProductionEvaluationRunner`` for production truth.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..chat.service import ask, create_conversation
from ..core.config import get_settings
from ..models import Base, Chunk, Document, DocumentVersion, Workspace
from ..retrieval.hybrid import result_for
from ..retrieval.schemas import Evidence, RetrievalTrace


def _tokens(value: str) -> set[str]:
    stopwords = {
        "about",
        "and",
        "does",
        "how",
        "in",
        "is",
        "kim",
        "ne",
        "the",
        "what",
        "who",
        "which",
        "with",
    }
    return {
        x
        for x in re.findall(r"\w+", value.casefold(), re.UNICODE)
        if len(x) > 1 and x not in stopwords
    }
    return {x for x in re.findall(r"[\wçğıöşü]+", value.casefold()) if len(x) > 1}


@dataclass(frozen=True)
class GoldenCase:
    id: str
    version: int
    workspace_fixture: str
    question: str
    tags: tuple[str, ...] = ()
    expected_route: str | None = None
    query_plan: dict[str, object] = field(default_factory=dict)
    relevant_documents: tuple[str, ...] = ()
    min_recall_at: dict[int, float] = field(default_factory=dict)
    expected_citation_ids: tuple[str, ...] = ()
    forbidden_document_ids: tuple[str, ...] = ()
    expected_evidence_ids: tuple[str, ...] = ()
    expected_facts: tuple[str, ...] = ()
    forbidden_facts: tuple[str, ...] = ()
    answerable: bool = True
    expected_answer_state: str | None = None

    @property
    def retrieval_eligible(self) -> bool:
        """Only relevance-labelled cases participate in retrieval quality aggregates."""
        return bool(self.relevant_documents)


@dataclass(frozen=True)
class GoldenSuite:
    schema_version: int
    suite_id: str
    suite_version: int
    fixture_dataset_id: str
    fixtures: dict[str, dict[str, object]]
    cases: tuple[GoldenCase, ...]
    benchmark_kind: str = "synthetic"
    pack_id: str = "committed-synthetic"
    baseline_policy: dict[str, object] = field(default_factory=dict)
    semantic_scorer_version: str = "fixture-token-semantic-v1"

    @property
    def fixture_digest(self) -> str:
        raw = json.dumps(self.fixtures, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class CaseResult:
    id: str
    status: str
    passed: bool
    assertions: list[dict[str, object]]
    latency_ms: int
    retrieval: dict[str, object]
    metadata: dict[str, object]


def load_suite(path: Path) -> GoldenSuite:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2:
        raise ValueError("unsupported evaluation schema_version; expected 2")
    required = ("suite_id", "suite_version", "fixture_dataset", "fixtures", "cases")
    if missing := [key for key in required if key not in payload]:
        raise ValueError(f"evaluation suite missing required fields: {', '.join(missing)}")
    cases = []
    for item in payload["cases"]:
        if missing := [
            key for key in ("id", "workspace_fixture", "question", "relevance") if key not in item
        ]:
            raise ValueError(f"case missing required fields: {', '.join(missing)}")
        relevance = item["relevance"]
        if not isinstance(relevance, dict):
            raise ValueError(f"case {item['id']} relevance must be an object")
        cases.append(
            GoldenCase(
                id=item["id"],
                version=item.get("version", 1),
                workspace_fixture=item["workspace_fixture"],
                question=item["question"],
                tags=tuple(item.get("tags", [])),
                expected_route=item.get("expected_route"),
                query_plan=item.get("query_plan", {}),
                relevant_documents=tuple(relevance.get("relevant_documents", [])),
                min_recall_at={
                    int(k): float(v) for k, v in relevance.get("min_recall_at", {}).items()
                },
                expected_citation_ids=tuple(item.get("expected_citation_ids", [])),
                forbidden_document_ids=tuple(item.get("forbidden_document_ids", [])),
                expected_evidence_ids=tuple(item.get("expected_evidence_ids", [])),
                expected_facts=tuple(item.get("expected_facts", [])),
                forbidden_facts=tuple(item.get("forbidden_facts", [])),
                answerable=item.get("answerable", True),
                expected_answer_state=item.get("expected_answer_state"),
            )
        )
    dataset = payload["fixture_dataset"]
    policy = payload.get("baseline_policy", {})
    allowed_policy = {"max_rank_degradation", "max_rr_drop", "max_recall_drop", "fail_on_hit_loss"}
    if not isinstance(policy, dict) or set(policy) - allowed_policy:
        raise ValueError("invalid baseline_policy")
    if any(
        float(policy[key]) < 0
        for key in ("max_rank_degradation", "max_rr_drop", "max_recall_drop")
        if key in policy
    ):
        raise ValueError("baseline policy thresholds must be non-negative")
    return GoldenSuite(
        2,
        payload["suite_id"],
        int(payload["suite_version"]),
        dataset["id"],
        payload["fixtures"],
        tuple(cases),
        payload.get("benchmark_kind", "synthetic"),
        payload.get("pack_id", path.name),
        policy,
        payload.get("semantic_scorer_version", "fixture-token-semantic-v1"),
    )


def compare_baseline(
    report: dict[str, object], baseline_path: Path, *, allow_incompatible: bool = False
) -> dict[str, object]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current, prior = report.get("provenance", {}), baseline.get("provenance", {})
    keys = (
        "suite_id",
        "suite_version",
        "fixture_digest",
        "benchmark_kind",
        "pack_id",
        "embedding_config_fingerprint",
        "retrieval_config_fingerprint",
        "semantic_scorer_version",
    )
    incompatible = [key for key in keys if current.get(key) != prior.get(key)]
    if not allow_incompatible and incompatible:
        report["baseline"] = {
            "path": str(baseline_path),
            "status": "BASELINE_INCOMPATIBLE",
            "passed": False,
        }
        return report
    before, after = {x["id"]: x for x in baseline.get("cases", [])}, {
        x["id"]: x for x in report["cases"]
    }
    policy = {
        "max_rank_degradation": 0,
        "max_rr_drop": 0.0,
        "max_recall_drop": 0.0,
        "fail_on_hit_loss": True,
    } | report.get("baseline_policy", {})
    diffs, regressions = [], []
    for case_id in sorted(before.keys() | after.keys()):
        if case_id not in before:
            diffs.append({"case_id": case_id, "status": "NEW_CASE"})
            continue
        if case_id not in after:
            diffs.append({"case_id": case_id, "status": "REMOVED_CASE"})
            continue
        old, new = before[case_id], after[case_id]
        lifecycle = (
            "PASS_TO_FAIL"
            if old.get("passed") and not new.get("passed")
            else (
                "FAIL_TO_PASS"
                if not old.get("passed") and new.get("passed")
                else "UNCHANGED_PASS" if old.get("passed") else "UNCHANGED_FAIL"
            )
        )
        diff = {
            "case_id": case_id,
            "lifecycle": lifecycle,
            "baseline_status": old.get("status"),
            "current_status": new.get("status"),
        }
        for key in ("rr", "expected_document_rank", "recall_at", "hit_at"):
            if old.get("retrieval", {}).get(key) != new.get("retrieval", {}).get(key):
                diff[key] = {
                    "baseline": old.get("retrieval", {}).get(key),
                    "current": new.get("retrieval", {}).get(key),
                }
        old_retrieval, new_retrieval = old.get("retrieval", {}), new.get("retrieval", {})
        rank_delta = None
        if isinstance(old_retrieval.get("expected_document_rank"), int) and isinstance(
            new_retrieval.get("expected_document_rank"), int
        ):
            rank_delta = (
                new_retrieval["expected_document_rank"] - old_retrieval["expected_document_rank"]
            )
        rr_drop = (old_retrieval.get("rr") or 0.0) - (new_retrieval.get("rr") or 0.0)
        recall_drops = {
            key: value - (new_retrieval.get("recall_at", {}).get(key, value))
            for key, value in old_retrieval.get("recall_at", {}).items()
        }
        hit_loss = any(
            value is True and new_retrieval.get("hit_at", {}).get(key) is False
            for key, value in old_retrieval.get("hit_at", {}).items()
        )
        metric_regression = (
            (rank_delta is not None and rank_delta > policy["max_rank_degradation"])
            or rr_drop > policy["max_rr_drop"]
            or any(drop > policy["max_recall_drop"] for drop in recall_drops.values())
            or (policy["fail_on_hit_loss"] and hit_loss)
        )
        regression = lifecycle == "PASS_TO_FAIL" or (
            lifecycle == "UNCHANGED_PASS" and metric_regression
        )
        diff["delta"] = {
            "rank": rank_delta,
            "rr": -rr_drop,
            "recall_at": {key: -value for key, value in recall_drops.items()},
        }
        diff["retrieval_regression"] = metric_regression
        diff["status"] = (
            "REGRESSION"
            if regression
            else "IMPROVEMENT" if lifecycle == "FAIL_TO_PASS" else "UNCHANGED"
        )
        diffs.append(diff)
        if regression:
            regressions.append(
                {
                    "case_id": case_id,
                    "kind": "RETRIEVAL_METRIC" if metric_regression else "PASS_TO_FAIL",
                }
            )
    report["baseline"] = {
        "path": str(baseline_path),
        "status": "COMPARED",
        "case_diffs": diffs,
        "hard_regressions": regressions,
        "policy": policy,
        "forced_incompatible_comparison": bool(incompatible),
        "incompatible_fields": incompatible,
        "passed": not regressions,
    }
    return report


class FixtureHybridRuntime:
    """Test provider boundary; labels never enter this object."""

    def __init__(self, corpus: dict[str, list[Evidence]]) -> None:
        self.corpus = corpus

    def search(
        self, _session: Session, workspace_id: str, query: str, *, final_evidence_limit=None
    ):
        query_tokens, rows = _tokens(query), self.corpus.get(workspace_id, [])
        bm25 = [
            x
            for x in sorted(
                rows, key=lambda x: (-len(query_tokens & _tokens(x.content)), x.document_id or "")
            )
            if query_tokens & _tokens(x.content)
        ]
        dense = [
            x
            for x in sorted(
                rows,
                key=lambda x: (
                    -len(query_tokens & _tokens(x.metadata.get("semantic_terms", ""))),
                    x.document_id or "",
                ),
            )
            if query_tokens & _tokens(x.metadata.get("semantic_terms", ""))
        ]
        scores: defaultdict[str, float] = defaultdict(float)
        items: dict[str, Evidence] = {}
        for ranking in (bm25, dense):
            for rank, item in enumerate(ranking, 1):
                key = item.chunk_id or item.document_id or ""
                items[key] = item
                scores[key] += 1 / (60 + rank)
        fused = [items[key] for key in sorted(scores, key=lambda x: (-scores[x], x))]
        final = fused[: final_evidence_limit or len(fused)]
        ranks = {
            "bm25": [x.document_id for x in bm25],
            "dense": [x.document_id for x in dense],
            "fusion": [x.document_id for x in fused],
            "final": [x.document_id for x in final],
        }
        return result_for(
            final,
            trace=RetrievalTrace(
                dense_executed=True,
                dense_candidate_count=len(dense),
                bm25_executed=True,
                bm25_candidate_count=len(bm25),
                fusion_candidate_count=len(fused),
                final_evidence_count=len(final),
                stage_rankings=ranks,
            ),
        )


class EvaluationRunner:
    def __init__(self, suite: GoldenSuite) -> None:
        self.suite = suite

    def run(self, *, tag: str | None = None, case_id: str | None = None) -> dict[str, object]:
        selected = [
            x
            for x in self.suite.cases
            if (not tag or tag in x.tags) and (not case_id or x.id == case_id)
        ]
        if not selected:
            raise ValueError("no golden cases selected")
        try:
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(engine)
            session = sessionmaker(bind=engine)()
            workspace_ids, corpus = self._seed(session)
        except Exception as error:
            return self._report(
                [
                    CaseResult(
                        x.id,
                        "invalid",
                        False,
                        [
                            {
                                "name": "preflight",
                                "passed": False,
                                "expected": "fixture runtime ready",
                                "actual": str(error),
                            }
                        ],
                        0,
                        {},
                        {},
                    )
                    for x in selected
                ]
            )
        try:
            results = [self._run_case(session, workspace_ids, corpus, x) for x in selected]
        finally:
            session.close()
        return self._report(results)

    def _seed(self, session: Session) -> tuple[dict[str, str], dict[str, list[Evidence]]]:
        workspace_ids, corpus, now = {}, {}, datetime.now(UTC)
        for slug, fixture in self.suite.fixtures.items():
            workspace_id = str(uuid4())
            workspace_ids[slug] = workspace_id
            corpus[workspace_id] = []
            session.add(
                Workspace(
                    id=workspace_id,
                    slug=slug,
                    name=slug,
                    state="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            for ordinal, item in enumerate(fixture.get("corpus", [])):
                document_id, version_id, chunk_id = item["id"], str(uuid4()), f"{item['id']}-chunk"
                session.add(
                    Document(
                        id=document_id,
                        workspace_id=workspace_id,
                        title=item.get("title", document_id),
                        active_version_id=version_id,
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.add(
                    DocumentVersion(
                        id=version_id,
                        workspace_id=workspace_id,
                        document_id=document_id,
                        version_number=1,
                        source_hash=f"fixture-{document_id}",
                        source_path="evaluation",
                        source_filename=f"{document_id}.md",
                        size_bytes=len(item["content"]),
                        state="ready",
                        created_at=now,
                    )
                )
                session.add(
                    Chunk(
                        id=chunk_id,
                        workspace_id=workspace_id,
                        document_id=document_id,
                        document_version_id=version_id,
                        ordinal=ordinal,
                        content=item["content"],
                        content_hash=f"fixture-{document_id}",
                        created_at=now,
                    )
                )
                corpus[workspace_id].append(
                    Evidence(
                        workspace_id,
                        "evaluation",
                        item["content"],
                        1.0,
                        document_id=document_id,
                        document_version_id=version_id,
                        chunk_id=chunk_id,
                        citation_label=item.get("title", document_id),
                        metadata={
                            "title": item.get("title", document_id),
                            "semantic_terms": " ".join(item.get("semantic_terms", [])),
                        },
                    )
                )
        session.commit()
        return workspace_ids, corpus

    def _run_case(
        self,
        session: Session,
        workspace_ids: dict[str, str],
        corpus: dict[str, list[Evidence]],
        case: GoldenCase,
    ) -> CaseResult:
        started, workspace_id = time.perf_counter(), workspace_ids[case.workspace_fixture]
        conversation = create_conversation(session, workspace_id, f"evaluation:{case.id}")
        _, answer, run = ask(
            session,
            workspace_id,
            conversation.id,
            case.question,
            "document_search",
            retrieval_runtime=FixtureHybridRuntime(corpus),
        )
        session.flush()
        metadata, assertions = json.loads(answer.metadata_json or "{}"), []
        self._assert(
            assertions,
            "route",
            not case.expected_route or metadata["execution_route"]["route"] == case.expected_route,
            expected=case.expected_route,
            actual=metadata["execution_route"]["route"],
        )
        for key, expected in case.query_plan.items():
            self._assert(
                assertions,
                f"query_plan.{key}",
                metadata["query_plan"].get(key) == expected,
                expected=expected,
                actual=metadata["query_plan"].get(key),
            )
        ranks = metadata.get("retrieval", {}).get("stage_rankings", {})
        final_ids = [x for x in ranks.get("final", []) if x]
        retrieval = self._metrics(case.relevant_documents, final_ids, case.min_recall_at) | {
            "stage_rankings": ranks
        }
        for key, expected in case.min_recall_at.items():
            self._assert(
                assertions,
                f"retrieval.recall@{key}",
                retrieval["recall_at"].get(str(key), 0) >= expected,
                expected=expected,
                actual=retrieval["recall_at"].get(str(key), 0),
            )
        cited = json.loads(answer.citations_json or "[]")
        cited_ids = [x.get("document_id") for x in cited]
        selected_ids = [
            x.get("document_id")
            for x in metadata.get("evidence_selection", {}).get("items", [])
            if x.get("selected")
        ]
        for doc_id in case.expected_citation_ids:
            self._assert(
                assertions,
                f"citation.{doc_id}",
                doc_id in cited_ids or case.expected_route == "aggregation",
                expected=doc_id,
                actual=cited_ids,
            )
        for doc_id in case.expected_evidence_ids:
            self._assert(
                assertions,
                f"evidence.{doc_id}",
                doc_id in selected_ids,
                expected=doc_id,
                actual=selected_ids,
            )
        for doc_id in case.forbidden_document_ids:
            self._assert(
                assertions,
                f"workspace/forbidden.{doc_id}",
                doc_id not in final_ids + selected_ids + cited_ids,
                expected="absent",
                actual=final_ids + selected_ids + cited_ids,
            )
        answer_text = answer.content.casefold()
        for fact in case.expected_facts:
            self._assert(
                assertions,
                f"answer.required:{fact}",
                fact.casefold() in answer_text,
                expected=fact,
                actual=answer.content,
            )
        for fact in case.forbidden_facts:
            self._assert(
                assertions,
                f"answer.forbidden:{fact}",
                fact.casefold() not in answer_text,
                expected="absent",
                actual=answer.content,
            )
        self._assert(
            assertions,
            "answer_state",
            run.answer_state
            == (case.expected_answer_state or ("grounded" if case.answerable else "unsupported")),
            expected=case.expected_answer_state,
            actual=run.answer_state,
        )
        summary = metadata.get("citation_summary", {})
        self._assert(
            assertions,
            "citation.visible_source_integrity",
            summary.get("cited_evidence_count") == summary.get("user_visible_source_count"),
            expected="equal",
            actual=summary,
        )
        if case.expected_route == "aggregation":
            execution = metadata.get("aggregation_execution", {})
            self._assert(
                assertions,
                "aggregation.complete",
                execution.get("complete") is True,
                expected=True,
                actual=execution.get("complete"),
            )
            self._assert(
                assertions,
                "aggregation.processed",
                execution.get("processed_chunk_count") == execution.get("candidate_chunk_count"),
                expected="all candidates",
                actual=execution,
            )
        passed = all(x["passed"] for x in assertions)
        return CaseResult(
            case.id,
            "passed" if passed else "failed",
            passed,
            assertions,
            int((time.perf_counter() - started) * 1000),
            retrieval,
            metadata,
        )

    @staticmethod
    def _metrics(
        relevant: tuple[str, ...], ordered: list[str], expected: dict[int, float]
    ) -> dict[str, object]:
        if not relevant:
            return {
                "eligible": False,
                "expected_document_rank": None,
                "rr": None,
                "hit_at": {},
                "recall_at": {},
            }
        rank = next((i for i, x in enumerate(ordered, 1) if x in relevant), None)
        ks = [k for k in sorted(set(expected) | {1, 3, 5, 10}) if k <= len(ordered)]
        return {
            "eligible": True,
            "expected_document_rank": rank,
            "rr": 1 / rank if rank else 0.0,
            "hit_at": {str(k): any(x in relevant for x in ordered[:k]) for k in ks},
            "recall_at": {
                str(k): (
                    sum(x in relevant for x in ordered[:k]) / len(relevant) if relevant else 1.0
                )
                for k in ks
            },
        }

    @staticmethod
    def _assert(
        items: list[dict[str, object]], name: str, passed: bool, *, expected: object, actual: object
    ) -> None:
        items.append({"name": name, "passed": passed, "expected": expected, "actual": actual})

    def _report(self, results: list[CaseResult]) -> dict[str, object]:
        settings = get_settings()
        invalid = sum(x.status == "invalid" for x in results)
        eligible_cases = [
            x for x in results if x.status != "invalid" and x.retrieval.get("eligible")
        ]
        excluded_cases = len(results) - invalid - len(eligible_cases)
        retrieval_ks = sorted(
            {key for item in eligible_cases for key in item.retrieval.get("hit_at", {})}, key=int
        )
        retrieval_metrics = {
            "eligible_cases": len(eligible_cases),
            "excluded_cases": excluded_cases,
            "mrr": (
                sum(item.retrieval["rr"] for item in eligible_cases) / len(eligible_cases)
                if eligible_cases
                else None
            ),
            "hit_at": {
                key: sum(item.retrieval["hit_at"].get(key, False) for item in eligible_cases)
                / len(eligible_cases)
                for key in retrieval_ks
            },
            "recall_at": {
                key: sum(item.retrieval["recall_at"].get(key, 0.0) for item in eligible_cases)
                / len(eligible_cases)
                for key in retrieval_ks
            },
        }
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        except Exception:
            commit = None
        return {
            "run_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "provenance": {
                "schema_version": self.suite.schema_version,
                "suite_id": self.suite.suite_id,
                "suite_version": self.suite.suite_version,
                "fixture_dataset_id": self.suite.fixture_dataset_id,
                "fixture_digest": self.suite.fixture_digest,
                "benchmark_kind": self.suite.benchmark_kind,
                "pack_id": self.suite.pack_id,
                "semantic_scorer_version": self.suite.semantic_scorer_version,
                "git_revision": commit,
                "retrieval_config_fingerprint": hashlib.sha256(
                    repr(
                        (
                            settings.dense_top_k,
                            settings.bm25_top_k,
                            settings.final_evidence_top_k,
                            settings.reranker_model,
                        )
                    ).encode()
                ).hexdigest(),
                "embedding_config_fingerprint": hashlib.sha256(
                    f"deterministic:{self.suite.semantic_scorer_version}".encode()
                ).hexdigest(),
            },
            "baseline_policy": {
                "max_rank_degradation": 0,
                "max_rr_drop": 0.0,
                "max_recall_drop": 0.0,
                "fail_on_hit_loss": True,
            }
            | self.suite.baseline_policy,
            "summary": {
                "cases": len(results),
                "passed": sum(x.status == "passed" for x in results),
                "failed": len(results) - sum(x.status == "passed" for x in results) - invalid,
                "invalid": invalid,
                "retrieval": retrieval_metrics,
                "mrr": retrieval_metrics["mrr"],
                "latency_ms": sum(x.latency_ms for x in results),
            },
            "cases": [asdict(x) for x in results],
        }
