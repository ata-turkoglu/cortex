"""Selection-only GraphRAG search for Query V2.

GraphRAG's Local, Global, and DRIFT engines each have a context-selection step and an answer-
writing step. V2 discards GraphRAG prose, so only the selection step runs:

- Local: entity-description embedding similarity (no LLM call),
- Global: dynamic community selection, where the configured Global model rates community summaries
  and prunes irrelevant branches,
- DRIFT: one primer call from the configured DRIFT model, then report embedding similarity.

The selected entity/report IDs are returned; provenance and validation stay in
``GraphRAGAdapter.query_findings`` and the trusted-source bridge. The ``graphrag`` package is
imported lazily, so environments without it fall back to lexical selection.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..core.config import Settings
from .adapter import GraphRoute, graphrag_api_key, route_model_family

COMMUNITY_LEVEL = 2
_CACHE_SIZE = 128
_cache: OrderedDict[tuple[object, ...], SmartSelection] = OrderedDict()
_cache_lock = threading.Lock()
# GraphRAG resolves ``${GRAPHRAG_API_KEY}`` from the process environment while loading config.
_env_lock = threading.Lock()


@dataclass(frozen=True)
class SmartSelection:
    artifact_ids: tuple[str, ...]
    llm_calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False


def graphrag_available() -> bool:
    return importlib.util.find_spec("graphrag") is not None


def select_context(
    graph_root: Path, route: GraphRoute, query: str, settings: Settings, limit: int = 10
) -> SmartSelection:
    """Run GraphRAG context selection in a private event loop; repeated questions are cached."""
    key = (
        str(graph_root.resolve()),
        route.value,
        " ".join(query.casefold().split()),
        # Local selection uses embeddings only; Global and DRIFT depend on their model.
        getattr(settings, f"graphrag_{route.value}_model", "embeddings"),
        settings.graphrag_drift_k_followups,
        limit,
    )
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            hit = _cache[key]
            return SmartSelection(hit.artifact_ids, cached=True)
    # The caller may already run inside an event loop; GraphRAG's async builders get their own.
    with ThreadPoolExecutor(max_workers=1) as pool:
        selection = pool.submit(
            asyncio.run, _select(graph_root, route, query, settings, limit)
        ).result(timeout=settings.graphrag_command_timeout_seconds)
    with _cache_lock:
        _cache[key] = selection
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return selection


def _load_config(graph_root: Path, settings: Settings, route: GraphRoute):
    from graphrag.config.load_config import load_config

    with _env_lock:
        previous = os.environ.get("GRAPHRAG_API_KEY")
        os.environ["GRAPHRAG_API_KEY"] = graphrag_api_key()
        try:
            config = load_config(graph_root)
        finally:
            if previous is None:
                os.environ.pop("GRAPHRAG_API_KEY", None)
            else:
                os.environ["GRAPHRAG_API_KEY"] = previous
    # Query-time settings apply immediately; they do not change the index.
    model_id = f"cortex_graphrag_{route.value}"
    if route is not GraphRoute.LOCAL and model_id in config.models:
        current = config.models[model_id]
        entry = route_model_family(
            {"model": getattr(settings, f"graphrag_{route.value}_model")},
            getattr(settings, f"graphrag_{route.value}_provider"),
        )
        config.models[model_id] = current.model_copy(
            update={
                "model": entry["model"],
                "type": entry["type"],
                "model_provider": entry.get("model_provider", current.model_provider),
            }
        )
    # Rate short community summaries instead of full reports: same pruning, fewer tokens.
    config.global_search.dynamic_search_use_summary = True
    config.global_search.dynamic_search_num_repeats = 1
    config.drift_search.drift_k_followups = settings.graphrag_drift_k_followups
    config.drift_search.primer_folds = settings.graphrag_drift_primer_folds
    return config


async def _select(
    graph_root: Path, route: GraphRoute, query: str, settings: Settings, limit: int
) -> SmartSelection:
    import pandas as pd
    from graphrag.config.embeddings import (
        community_full_content_embedding,
        entity_description_embedding,
    )
    from graphrag.query.factory import (
        get_drift_search_engine,
        get_global_search_engine,
        get_local_search_engine,
    )
    from graphrag.query.indexer_adapters import (
        read_indexer_communities,
        read_indexer_entities,
        read_indexer_relationships,
        read_indexer_report_embeddings,
        read_indexer_reports,
        read_indexer_text_units,
    )
    from graphrag.utils.api import get_embedding_store

    config = _load_config(graph_root, settings, route)
    output = graph_root / "output"
    entities = pd.read_parquet(output / "entities.parquet")
    communities = pd.read_parquet(output / "communities.parquet")
    reports = pd.read_parquet(output / "community_reports.parquet")
    store_args = {name: store.model_dump() for name, store in config.vector_store.items()}

    def by_short_id(frame: pd.DataFrame, short_ids) -> tuple[str, ...]:
        mapping = {str(row.human_readable_id): str(row.id) for row in frame.itertuples()}
        ordered = (mapping.get(str(value)) for value in short_ids)
        return tuple(dict.fromkeys(value for value in ordered if value))[:limit]

    if route is GraphRoute.LOCAL:
        engine = get_local_search_engine(
            config=config,
            reports=read_indexer_reports(reports, communities, COMMUNITY_LEVEL),
            text_units=read_indexer_text_units(pd.read_parquet(output / "text_units.parquet")),
            entities=read_indexer_entities(entities, communities, COMMUNITY_LEVEL),
            relationships=read_indexer_relationships(
                pd.read_parquet(output / "relationships.parquet")
            ),
            covariates={},
            response_type="list",
            description_embedding_store=get_embedding_store(
                config_args=store_args, embedding_name=entity_description_embedding
            ),
        )
        result = engine.context_builder.build_context(
            query=query, **engine.context_builder_params
        )
        records = result.context_records.get("entities")
        ids = by_short_id(entities, [] if records is None else records["id"])
        return SmartSelection(ids, result.llm_calls, result.prompt_tokens, result.output_tokens)

    if route is GraphRoute.GLOBAL:
        engine = get_global_search_engine(
            config,
            reports=read_indexer_reports(
                reports, communities, COMMUNITY_LEVEL, dynamic_community_selection=True
            ),
            entities=read_indexer_entities(entities, communities, COMMUNITY_LEVEL),
            communities=read_indexer_communities(communities, reports),
            response_type="list",
            dynamic_community_selection=True,
        )
        result = await engine.context_builder.build_context(
            query=query, **{**engine.context_builder_params, "shuffle_data": False}
        )
        records = result.context_records.get("reports")
        ids = by_short_id(reports, [] if records is None else records["id"])
        return SmartSelection(ids, result.llm_calls, result.prompt_tokens, result.output_tokens)

    indexed_reports = read_indexer_reports(reports, communities, COMMUNITY_LEVEL)
    read_indexer_report_embeddings(
        indexed_reports,
        get_embedding_store(
            config_args=store_args, embedding_name=community_full_content_embedding
        ),
    )
    engine = get_drift_search_engine(
        config=config,
        reports=indexed_reports,
        text_units=read_indexer_text_units(pd.read_parquet(output / "text_units.parquet")),
        entities=read_indexer_entities(entities, communities, COMMUNITY_LEVEL),
        relationships=read_indexer_relationships(
            pd.read_parquet(output / "relationships.parquet")
        ),
        description_embedding_store=get_embedding_store(
            config_args=store_args, embedding_name=entity_description_embedding
        ),
        response_type="list",
    )
    top_k, tokens = await engine.context_builder.build_context(query)
    ids = by_short_id(reports, top_k["short_id"])
    return SmartSelection(
        ids,
        int(tokens.get("llm_calls", 0)),
        int(tokens.get("prompt_tokens", 0)),
        int(tokens.get("output_tokens", 0)),
    )
