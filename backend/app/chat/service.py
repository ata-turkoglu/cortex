"""Safe deterministic router and evidence-first synthesis for the chat API.

Provider-backed selector/synthesis can replace these adapters without changing the persisted
query contract. Until then no model is called and answers are limited to stored evidence.
"""

import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..aggregation.property import (
    AggregationResult,
    aggregate_properties,
    entity_share,
    ownership_spans,
    property_location_display,
)
from ..core.config import get_settings
from ..models import Conversation, Message, QueryRun, QueryStepRun, Workspace
from ..retrieval.document_lookup import group_evidence_by_document, match_reason
from ..retrieval.runtime import HybridRetrievalRuntime, get_hybrid_retrieval_runtime
from ..retrieval.schemas import AnswerState, Evidence, RetrievalResult
from ..workflows.queries import create_query_run
from .evidence_selection import select_answer_evidence
from .execution import citation_summary, finalize_citations
from .query_plan import (
    QueryPlan,
    entity_resolution_trace,
    plan_query,
    resolve_entities,
    retrieval_queries,
)

MODES = {"automatic", "document_search", "deep_analysis"}
ROUTES = {"hybrid", "graphrag_local", "graphrag_global", "graphrag_drift"}
DEFAULT_CONVERSATION_TITLE = "New conversation"
CONVERSATION_TITLE_LIMIT = 72


@dataclass(frozen=True)
class RouteSelection:
    routes: tuple[str, ...]
    reason: str
    confidence: float
    intent: str = "generic_qa"
    needs_list: bool = False


DOCUMENT_LOOKUP_PATTERNS = (
    r"hangi\s+(?:belgelerde|dosyalarda)\s+ge[çc]",
    r"(?:ge[çc]ti[ğg]i|bulundu[ğg]u|ad[ıi]\s+ge[çc]en)\s+(?:belge|dosya)ler",
    r"ge[çc]en\s+(?:belge|dosya)leri\s+listele",
    r"(?:belge|dosya)lerini\s+listele",
    r"appears?\s+in\s+which\s+documents?",
    r"documents?\s+(?:containing|mentioning)",
    r"list\s+documents?\s+(?:containing|mentioning)",
)


def is_document_lookup(query: str) -> bool:
    normalized = " ".join(query.casefold().split())
    return any(re.search(pattern, normalized) for pattern in DOCUMENT_LOOKUP_PATTERNS)


def lookup_target(query: str) -> str:
    """Remove list-language and retain the entity, place, or type being searched."""
    normalized = " ".join(query.strip().split()).strip(" ?.!")
    removals = (
        r"\s+hangi\s+(?:belgelerde|dosyalarda)\s+ge[çc](?:iyor|mektedir|er)?$",
        r"\s+(?:ge[çc]ti[ğg]i|bulundu[ğg]u|ad[ıi]\s+ge[çc]en)\s+(?:belge|dosya)ler(?:i)?$",
        r"\s+ge[çc]en\s+(?:belge|dosya)leri\s+listele$",
        r"\s+(?:belge|dosya)lerini\s+listele$",
        r"\s+appears?\s+in\s+which\s+documents?$",
        r"^documents?\s+(?:containing|mentioning)\s+",
        r"^list\s+documents?\s+(?:containing|mentioning)\s+",
    )
    for pattern in removals:
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)
    return normalized.strip(" ?.!")


def select_routes(query: str, mode: str) -> RouteSelection:
    """Selector behavior, deliberately constrained to approved V1 combinations."""
    normalized = query.casefold()
    if is_document_lookup(query):
        return RouteSelection(
            ("hybrid",),
            "The question requests a unique document list for a named entity or term.",
            1.0,
            intent="entity_document_lookup",
            needs_list=True,
        )
    if mode == "document_search":
        return RouteSelection(("hybrid",), "Document Search mode requires Hybrid Search.", 1.0)
    if mode == "deep_analysis":
        return RouteSelection(
            ("hybrid", "graphrag_global"),
            "Deep Analysis combines document evidence with graph-wide context.",
            0.82,
        )
    if any(term in normalized for term in ("overview", "pattern", "across", "genel", "ilişki")):
        return RouteSelection(
            ("hybrid", "graphrag_global"), "The question requests cross-document context.", 0.76
        )
    return RouteSelection(("hybrid",), "The question is best answered from document passages.", 0.9)


def _step(session: Session, run: QueryRun, name: str, state: str) -> None:
    item = session.scalar(
        select(QueryStepRun).where(
            QueryStepRun.query_run_id == run.id, QueryStepRun.step_name == name
        )
    )
    if item:
        item.state, item.updated_at = state, datetime.now(UTC)


def _hybrid_evidence(
    session: Session,
    workspace_id: str,
    query: str,
    *,
    needs_list: bool,
    runtime: HybridRetrievalRuntime | None = None,
) -> RetrievalResult:
    """A `hybrid` route always reaches HybridRetriever.search through this boundary."""
    settings = get_settings()
    return (runtime or get_hybrid_retrieval_runtime()).search(
        session,
        workspace_id,
        lookup_target(query) if needs_list else query,
        final_evidence_limit=(
            settings.document_lookup_final_evidence_top_k if needs_list else None
        ),
    )


def _planned_hybrid_evidence(
    session: Session,
    workspace_id: str,
    query: str,
    plan: QueryPlan,
    *,
    needs_list: bool,
    runtime: HybridRetrievalRuntime | None = None,
) -> tuple[RetrievalResult, list[str], dict[str, object]]:
    queries = retrieval_queries(query, plan)
    results = [
        _hybrid_evidence(session, workspace_id, item, needs_list=needs_list, runtime=runtime)
        for item in queries
    ]
    seen: set[str] = set()
    evidence: list[Evidence] = []
    for result in results:
        for item in result.evidence:
            key = item.chunk_id or f"{item.source}:{item.content}"
            if key not in seen:
                seen.add(key)
                evidence.append(item)
    primary = results[0]
    if needs_list:
        selected = evidence
        selection_trace = {
            "operation": plan.operation,
            "resolved_entity": plan.entities[0].resolved_value if plan.entities else None,
            "input_count": len(evidence),
            "selected_count": len(evidence),
            "mode": "document_lookup_grouping",
            "items": [],
        }
    else:
        selected, selection_trace = select_answer_evidence(evidence, plan)
    return (
        RetrievalResult(
            tuple(selected),
            primary.state,
            primary.fallback_reason,
            primary.trace,
        ),
        queries,
        selection_trace,
    )


def _answer(
    evidence: list[Evidence], plan: QueryPlan | None = None
) -> tuple[str, AnswerState, list[dict[str, str]]]:
    if not evidence:
        return (
            "Bu çalışma alanındaki kaynaklarda bu soruyu destekleyen kanıt bulamadım.",
            AnswerState.UNSUPPORTED,
            [],
        )
    citations = [
        {
            "document_id": item.document_id or "",
            "document_version_id": item.document_version_id or "",
            "chunk_id": item.chunk_id or "",
            "label": item.citation_label or item.source,
        }
        for item in evidence
    ]
    if plan and plan.operation in {"identify", "describe", "timeline", "generic_qa"}:
        return _concise_fallback(evidence, plan, citations)
    if plan:
        if plan.requires_aggregation:
            prefix, state = (
                "Bu sorgu kapsamlı toplama ve tekilleştirme gerektiriyor; aşağıdaki kayıtlar "
                "doğrulanmış bir toplam değildir:",
                AnswerState.PARTIAL,
            )
        elif plan.requires_exhaustive_retrieval:
            prefix, state = (
                "Aşağıdaki kayıtlar görülen kanıtlardır; tam bir envanter değildir:",
                AnswerState.GROUNDED,
            )
        elif plan.operation == "identify" and plan.entities and plan.entities[0].resolved_value:
            entity = plan.entities[0]
            qualifier = "likely " if entity.confidence < 0.95 else ""
            prefix, state = (
                f'Kaynaklarda "{entity.mention}" '
                f"{'büyük olasılıkla ' if qualifier else ''}"
                f'"{entity.resolved_value}" olarak geçiyor:',
                AnswerState.GROUNDED,
            )
        else:
            prefix, state = "Kaynaklardaki ilgili kanıtlar:", AnswerState.GROUNDED
        excerpts = "\n".join(
            f"[{index}] {item.content.strip()[:280]}" for index, item in enumerate(evidence, 1)
        )
        return f"{prefix}\n\n{excerpts}", state, citations
    limit = {"concise": 280, "balanced": 700, "detailed": 1400}[get_settings().answer_style]
    excerpts = "\n\n".join(
        f"[{index}] {item.content.strip()[:limit]}" for index, item in enumerate(evidence, 1)
    )
    return (f"Kaynaklardaki ilgili kanıtlar:\n\n{excerpts}", AnswerState.GROUNDED, citations)


def _concise_fallback(
    evidence: list[Evidence], plan: QueryPlan, citations: list[dict[str, str]]
) -> tuple[str, AnswerState, list[dict[str, str]]]:
    """A deliberately small, grounded fallback that never exposes a chunk buffer."""
    entity = plan.entities[0] if plan.entities else None
    name = (entity.resolved_value or entity.mention) if entity else "Bu konu"
    resolved_name = entity.resolved_value if entity else None
    first = evidence[0].content.casefold()
    if any(term in first for term in ("tapu", "hisse", "malik", "taşınmaz", "gayrimenkul")):
        context = "taşınmaz ve hissedarlık bağlamında"
    elif any(term in first for term in ("miras", "veraset")):
        context = "miras ve veraset bağlamında"
    elif any(term in first for term in ("icra", "borç", "senet")):
        context = "hukuki veya mali kayıtlar bağlamında"
    else:
        context = "incelenen belgelerde"
    if plan.operation == "identify" and entity and entity.resolved_value:
        uncertainty = "büyük olasılıkla " if entity.confidence < 0.95 else ""
        answer = (
            f"Kaynaklarda “{entity.mention}” {uncertainty}"
            f"{entity.resolved_value}’i ifade ediyor.\n\n"
            f"{entity.resolved_value}, {context} geçiyor. [1]"
        )
    elif plan.operation == "timeline":
        date = plan.constraints.date_start or "İlgili dönemde"
        answer = f"- {date}: {name}, {context} yer alan bir kayıtla ilişkilendiriliyor. [1]"
    elif (
        plan.operation == "describe"
        and resolved_name
        and any(
            term in " ".join(item.content.casefold() for item in evidence)
            for term in ("tapu", "hisse", "taşınmaz", "gayrimenkul", "parsel")
        )
    ):
        facts: dict[tuple[str | None, str | None], tuple[int, str, int]] = {}
        for index, item in enumerate(evidence, 1):
            text = item.content
            ownership = ownership_spans(text, resolved_name)
            cadastral = re.search(
                r"(?:(\d+)\s+pafta[\s,]*)?(?:(\d+)\s+ada[\s,]*)?(?:(\d+)\s+(?:nolu\s+|sayılı\s+)?parsel)",
                text,
                re.I,
            )
            share = entity_share(text, resolved_name)
            parts = []
            if cadastral:
                parts.extend(
                    f"{value} {label}"
                    for value, label in zip(
                        cadastral.groups(), ("pafta", "ada", "parsel"), strict=True
                    )
                    if value
                )
            if share:
                parts.append(f"{share.text} hisse")
            if parts and ownership:
                key = (
                    cadastral.group(2) if cadastral else None,
                    cadastral.group(3) if cadastral else None,
                )
                row = f"- {', '.join(parts)} ile ilişkilendiriliyor. [{index}]"
                richness = sum(bool(value) for value in cadastral.groups()) if cadastral else 0
                if key == (None, None) or key not in facts or richness > facts[key][2]:
                    facts[key] = (index, row, richness)
        if facts:
            answer = (
                f"{name}, arşiv belgelerinde taşınmaz ve hissedarlık kayıtlarıyla "
                "ilişkilendiriliyor.\n\n"
                + "\n".join(row for _, row, _ in facts.values())
                + "\n\nBu kayıtlar tarihsel belge bilgisidir; güncel mülkiyet durumu "
                "olarak yorumlanmamalıdır."
            )
        else:
            answer = (
                f"Seçilen kaynaklar, belirli taşınmazları {resolved_name} ile yerel bir "
                "mülkiyet ilişkisine güvenle bağlamak için yeterli değil."
            )
    elif plan.operation == "describe":
        markers = " ".join(f"[{index}]" for index in range(1, min(len(evidence), 3) + 1))
        answer = f"{name}, {context} geçiyor. {markers}"
    else:
        answer = f"Soruyla ilgili seçilen kayıtlar {context} bilgi sağlıyor. [1]"
    return answer, AnswerState.GROUNDED, citations


def _document_lookup_answer(
    query: str, evidence: list[Evidence]
) -> tuple[str, AnswerState, list[dict[str, str]]]:
    target = lookup_target(query)
    documents = group_evidence_by_document(evidence, exact_text=target)
    if not documents:
        return _answer([])
    citations = []
    rows = []
    for document in documents:
        representative = document.matched_chunks[0]
        label = document.document_code or document.title
        details = [match_reason(document, target)]
        if document.page:
            details.append(f"sayfa {document.page}")
        if document.document_type:
            details.append(document.document_type)
        rows.append(f"| {label} | {' · '.join(details)} |")
        citations.append(
            {
                "document_id": document.document_id,
                "document_version_id": document.document_version_id or "",
                "chunk_id": representative.chunk_id or "",
                "label": representative.citation_label or label,
            }
        )
    answer = (
        f'"{target}" aşağıdaki belgelerde geçmektedir.\n\n'
        "| Belge | Neden geçiyor |\n|---|---|\n"
        + "\n".join(rows)
        + f"\n\nToplam: {len(documents)} belge"
    )
    return answer, AnswerState.GROUNDED, citations


def _aggregation_answer(
    result: AggregationResult, plan: QueryPlan
) -> tuple[str, AnswerState, list[dict[str, str]]]:
    """Render normalized property records rather than raw evidence chunks."""
    citations: list[dict[str, str]] = []
    if plan.operation == "count":
        count, label = (
            (result.distinct_parcel_count, "farklı parsel")
            if plan.aggregation_type == "distinct_parcel"
            else (result.distinct_property_count, "farklı taşınmaz kaydı")
        )
        text = (
            f"Aktif arşivde {count} {label} tekilleştirildi."
            if result.complete
            else f"En az {count} {label} tespit edildi; kesin toplam doğrulanamadı."
        )
        return text, AnswerState.GROUNDED if result.complete else AnswerState.PARTIAL, citations
    rows: list[str] = []
    for index, record in enumerate(result.records, 1):
        claim = record.representative
        details = property_location_display(claim)
        rows.append(f"{index}. {details or 'Kimliği eksik taşınmaz kaydı'}")
        if claim.normalized_share:
            rows.append(f"   Hisse: {claim.normalized_share}")
        rows.append(f"   Kaynak: [{index}]")
        citations.append(
            {
                "document_id": claim.document_id,
                "document_version_id": claim.document_version_id,
                "chunk_id": claim.chunk_id,
                "label": claim.citation,
            }
        )
    disclaimer = (
        "Bu liste, bu workspace'teki aktif belgelerde tespit edilen "
        "ve tekilleştirilebilen kayıtlardır."
        if result.complete
        else (
            "Tam envanter doğrulanamadı; aşağıdakiler erişilebilen kaynaklarda "
            "tespit edilen kayıtlardır."
        )
    )
    return (
        f"Belgelerde {result.entity} adına/hissesine kayıtlı görülen taşınmazlar:\n\n"
        + "\n".join(rows)
        + f"\n\n{disclaimer}",
        AnswerState.GROUNDED if result.complete else AnswerState.PARTIAL,
        citations,
    )


def require_conversation(session: Session, workspace_id: str, conversation_id: str) -> Conversation:
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise LookupError("conversation not found in workspace")
    return conversation


def delete_conversation(session: Session, workspace_id: str, conversation_id: str) -> None:
    conversation = require_conversation(session, workspace_id, conversation_id)
    now = datetime.now(UTC)
    conversation.deleted_at = now
    conversation.updated_at = now


def create_conversation(session: Session, workspace_id: str, title: str) -> Conversation:
    if not session.scalar(
        select(Workspace.id).where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
    ):
        raise LookupError("workspace not found")
    timestamp = datetime.now(UTC)
    conversation = Conversation(
        id=str(uuid4()),
        workspace_id=workspace_id,
        title=title.strip() or DEFAULT_CONVERSATION_TITLE,
        summary=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(conversation)
    return conversation


def conversation_title_from_query(content: str) -> str:
    """Create a compact, stable history label from the first user question."""
    normalized = " ".join(content.split())
    if len(normalized) <= CONVERSATION_TITLE_LIMIT:
        return normalized
    return f"{normalized[: CONVERSATION_TITLE_LIMIT - 1].rstrip()}…"


def backfill_default_conversation_titles(
    session: Session, conversations: list[Conversation]
) -> None:
    """Upgrade legacy placeholder titles from their first user message."""
    pending = {item.id: item for item in conversations if item.title == DEFAULT_CONVERSATION_TITLE}
    if not pending:
        return
    messages = session.scalars(
        select(Message)
        .where(
            Message.conversation_id.in_(pending),
            Message.role == "user",
        )
        .order_by(Message.conversation_id, Message.created_at)
    )
    for message in messages:
        conversation = pending.pop(message.conversation_id, None)
        if conversation:
            conversation.title = conversation_title_from_query(message.content)
        if not pending:
            break


def edit_message(
    session: Session, workspace_id: str, conversation_id: str, message_id: str, content: str
) -> Message:
    require_conversation(session, workspace_id, conversation_id)
    message = session.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.workspace_id == workspace_id,
            Message.conversation_id == conversation_id,
            Message.role == "user",
        )
    )
    if not message:
        raise LookupError("user message not found in workspace conversation")
    if not content.strip():
        raise ValueError("message content is required")
    timestamp = datetime.now(UTC)
    message.content, message.edited_at, message.updated_at = content.strip(), timestamp, timestamp
    return message


def ask(
    session: Session,
    workspace_id: str,
    conversation_id: str,
    content: str,
    mode: str,
    *,
    retrieval_runtime: HybridRetrievalRuntime | None = None,
) -> tuple[Message, Message, QueryRun]:
    if mode not in MODES or not content.strip():
        raise ValueError("a query and supported mode are required")
    conversation = require_conversation(session, workspace_id, conversation_id)
    started = time.perf_counter()
    timestamp = datetime.now(UTC)
    user = Message(
        id=str(uuid4()),
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        query_run_id=None,
        role="user",
        content=content.strip(),
        status="completed",
        citations_json=None,
        metadata_json=None,
        edited_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(user)
    if conversation.title == DEFAULT_CONVERSATION_TITLE:
        conversation.title = conversation_title_from_query(content)
    recent = session.scalars(
        select(Message)
        .where(Message.workspace_id == workspace_id, Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(get_settings().conversation_memory_window_messages)
    ).all()
    memory = [{"role": item.role, "content": item.content[:500]} for item in reversed(recent)]
    run = create_query_run(session, workspace_id, content, conversation_id)
    _step(session, run, "route", "running")
    # Import lazily to keep the deterministic service usable in minimal worker environments.
    from .router import LlamaIndexRouter

    choice = LlamaIndexRouter().select(content, mode)
    plan = resolve_entities(session, workspace_id, plan_query(content))
    if plan.operation == "lookup_documents":
        choice = RouteSelection(
            choice.routes, choice.reason, choice.confidence, "entity_document_lookup", True
        )
    run.selected_routes_json, run.route_reason, run.route_confidence = (
        json.dumps(choice.routes),
        choice.reason,
        choice.confidence,
    )
    _step(session, run, "route", "completed")
    _step(session, run, "retrieve", "running")
    graph_routes = [route for route in choice.routes if route.startswith("graphrag_")]
    aggregation_result = None
    execution_route = {
        "route": "aggregation" if plan.requires_aggregation else "normal_qa",
        "operation": plan.operation,
        "target": plan.target,
        "requires_exhaustive_retrieval": plan.requires_exhaustive_retrieval,
        "requires_aggregation": plan.requires_aggregation,
        "requires_deduplication": plan.requires_deduplication,
        "reason_codes": list(plan.reason_codes),
    }
    if plan.requires_aggregation:
        entity = plan.entities[0] if plan.entities else None
        aggregation_result = aggregate_properties(
            session,
            workspace_id,
            entity.resolved_value if entity else None,
            entity.aliases if entity else (),
        )
        graph_routes = []
    if graph_routes:
        # API only persists and submits the job. The worker imports and executes GraphRAG.
        answer, answer_state, citations = "GraphRAG query queued.", AnswerState.UNSUPPORTED, []
        graph_metadata: dict[str, object] = {
            "requested_route": graph_routes[0],
            "executed_route": None,
            "graphrag_query_job": True,
            "fallback_used": False,
        }
        run.state = "queued"
    else:
        answer = None
        answer_state = AnswerState.UNSUPPORTED
        citations = []
        if aggregation_result:
            retrieval = None
            evidence = []
            graph_metadata = {"aggregation_execution": aggregation_result.execution}
        else:
            retrieval, retrieval_query_list, selection_trace = _planned_hybrid_evidence(
                session,
                workspace_id,
                content,
                plan,
                needs_list=choice.needs_list,
                runtime=retrieval_runtime,
            )
            evidence = list(retrieval.evidence)
            graph_metadata = {
                "retrieval": retrieval.trace.as_dict(),
                "retrieval_queries": retrieval_query_list,
                "evidence_selection": selection_trace,
            }
    _step(session, run, "retrieve", "completed")
    _step(session, run, "synthesize", "running")
    if answer is None:
        answer, generated_state, citations = (
            _aggregation_answer(aggregation_result, plan)
            if aggregation_result
            else (
                _document_lookup_answer(
                    (
                        plan.entities[0].resolved_value
                        if plan.entities and plan.entities[0].resolved_value
                        else content
                    ),
                    evidence,
                )
                if choice.needs_list
                else _answer(evidence, plan)
            )
        )
        answer_state = (
            generated_state
            if aggregation_result
            else (retrieval.state if evidence else generated_state)
        )
        if not choice.needs_list and not aggregation_result and citations:
            finalized = finalize_citations(answer, citations)
            if finalized:
                answer, citations = finalized
    run.answer_state = answer_state.value
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    if not graph_routes:
        run.state = "completed"
    run.updated_at = datetime.now(UTC)
    _step(session, run, "synthesize", "pending" if graph_routes else "completed")
    assistant = Message(
        id=str(uuid4()),
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        query_run_id=run.id,
        role="assistant",
        content=answer,
        status="queued" if graph_routes else "completed",
        citations_json=json.dumps(citations, ensure_ascii=False),
        metadata_json=json.dumps(
            {
                "query_run_id": run.id,
                "route_reason": run.route_reason,
                "confidence": choice.confidence,
                "answer_state": answer_state.value,
                "intent": choice.intent,
                "needs_list": choice.needs_list,
                "query_plan": plan.as_dict(),
                "execution_route": execution_route,
                "citation_summary": citation_summary(
                    {"evidence_selection": graph_metadata.get("evidence_selection", {})}, citations
                ),
                "entity_resolution": entity_resolution_trace(plan),
                "memory_message_count": len(memory),
                "inference": False,
                "synthesis": {
                    "eligible": bool(not graph_routes and not choice.needs_list and citations),
                    "attempted": False,
                    "success": False,
                    "provider": get_settings().answer_provider,
                    "model": get_settings().answer_model,
                    "fallback_used": True,
                    "raw_evidence_guard_triggered": False,
                    "regeneration_attempted": False,
                },
                **graph_metadata,
            }
        ),
        edited_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(assistant)
    conversation.updated_at = datetime.now(UTC)
    return user, assistant, run
