"""Deterministic structured execution over detached canonical populations."""

from __future__ import annotations

import json
from hashlib import sha256
from time import perf_counter

from app.query.ir.schemas import (
    AggregateNode,
    CompareNode,
    CountNode,
    DistinctNode,
    ExistsNode,
    FilterNode,
    GroupNode,
    IRNode,
    JoinNode,
    LimitNode,
    ProjectNode,
    RankNode,
    ScanNode,
    SortNode,
    TemporalConstraintNode,
)
from app.query.orchestration import (
    AggregateResult,
    CompletenessReport,
    EngineFailure,
    EngineResult,
    EngineTrace,
    GroundedItem,
    ProvenanceLink,
)
from app.query.planning import ExecutionStep

from .schemas import CanonicalPopulation, CanonicalRecord, StructuredGroup, StructuredValue


class StructuredExecutionError(ValueError):
    pass


class StructuredQueryEngine:
    def __init__(self, workspace_id: str, generation_id: str) -> None:
        if not workspace_id or not generation_id:
            raise ValueError("structured execution requires workspace and generation")
        self.workspace_id = workspace_id
        self.generation_id = generation_id

    def execute(
        self,
        step: ExecutionStep,
        node: IRNode,
        inputs: tuple[StructuredValue, ...] = (),
        *,
        population: CanonicalPopulation | None = None,
    ) -> tuple[StructuredValue, EngineResult]:
        started = perf_counter()
        self._validate(step, node, inputs, population)
        if isinstance(node, ScanNode):
            assert population is not None
            value = self._scan(population, node.population_mode == "exhaustive")
        else:
            value = self._apply(node, inputs)
        return value, self._result(step, value, int((perf_counter() - started) * 1_000))

    def _validate(self, step, node, inputs, population) -> None:
        if step.engine != "structured" or step.trace.logical_node_ids != (node.node_id,):
            raise StructuredExecutionError("physical step does not match the structured operator")
        if step.readiness.workspace_id != self.workspace_id:
            raise StructuredExecutionError("structured step crosses the engine workspace")
        if step.readiness.generation_id != self.generation_id:
            raise StructuredExecutionError("structured step uses a different generation")
        if isinstance(node, ScanNode):
            if population is None or (
                population.workspace_id != self.workspace_id
                or population.generation_id != self.generation_id
                or population.resource != node.resource
            ):
                raise StructuredExecutionError("canonical population does not match the scan")
        elif len(inputs) != len(node.inputs):
            raise StructuredExecutionError("structured inputs do not match logical dependencies")

    def _scan(self, population: CanonicalPopulation, exhaustive: bool) -> StructuredValue:
        safe = population.safely_enumerable and not population.unresolved_candidate_ids
        completeness = CompletenessReport(
            coverage="exhaustive" if exhaustive else "grounded",
            state="complete" if exhaustive and safe else ("partial" if exhaustive else "unknown"),
            boundary=population.boundary,
            generation_id=self.generation_id,
            candidate_count=population.candidate_count,
            processed_count=len(population.records),
            confirmed_count=len(population.records),
            unresolved_candidate_ids=population.unresolved_candidate_ids,
            not_safely_enumerable=not safe,
            ready_projections=population.ready_projections,
        )
        return StructuredValue(
            kind="records", records=population.records, completeness=completeness
        )

    def _apply(self, node: IRNode, inputs: tuple[StructuredValue, ...]) -> StructuredValue:
        source = inputs[0]
        if isinstance(node, FilterNode):
            records = tuple(
                item for item in source.records
                if _compare(item.values.get(node.field.field), node.comparator, node.value)
            )
            return _records(records, source.completeness)
        if isinstance(node, DistinctNode):
            fields = tuple(field.field for field in node.fields)
            unique: dict[str, CanonicalRecord] = {}
            for item in source.records:
                key = _stable(tuple(item.values.get(field) for field in fields) or item.values)
                unique.setdefault(key, item)
            return _records(tuple(unique.values()), source.completeness)
        if isinstance(node, GroupNode):
            grouped: dict[str, list[CanonicalRecord]] = {}
            keys: dict[str, dict] = {}
            for item in source.records:
                values = {field.field: item.values.get(field.field) for field in node.keys}
                group_id = _stable(values)
                grouped.setdefault(group_id, []).append(item)
                keys[group_id] = values
            return StructuredValue(
                kind="groups",
                groups=tuple(
                    StructuredGroup(group_id=key, keys=keys[key], records=tuple(items))
                    for key, items in grouped.items()
                ),
                completeness=source.completeness,
            )
        if isinstance(node, JoinNode):
            right = inputs[1]
            joined = []
            for left_item in source.records:
                matches = [
                    right_item
                    for right_item in right.records
                    if all(
                        _compare(
                            left_item.values.get(condition.left.field),
                            condition.comparator,
                            right_item.values.get(condition.right.field),
                        )
                        for condition in node.conditions
                    )
                ]
                if node.join_type == "anti" and not matches:
                    joined.append(left_item)
                elif node.join_type == "semi" and matches:
                    joined.append(left_item)
                elif matches:
                    joined.extend(_joined_record(left_item, item) for item in matches)
                elif node.join_type == "left":
                    joined.append(left_item)
            return _records(
                tuple(joined), _combined(source.completeness, right.completeness)
            )
        if isinstance(node, CountNode):
            if source.groups:
                scalar = {group.group_id: _count(group.records, node) for group in source.groups}
            else:
                scalar = _count(source.records, node)
            return StructuredValue(
                kind="scalar", records=source.records, groups=source.groups, scalar=scalar,
                aggregate_function="distinct_count" if node.distinct_fields else "count",
                completeness=source.completeness,
            )
        if isinstance(node, AggregateNode):
            collections = ({group.group_id: group.records for group in source.groups}
                           if source.groups else {node.alias: source.records})
            values = {key: _aggregate(items, node.field.field, node.function)
                      for key, items in collections.items()}
            return StructuredValue(
                kind="scalar", records=source.records, groups=source.groups,
                scalar=values if source.groups else values[node.alias],
                aggregate_function=node.function, completeness=source.completeness,
            )
        if isinstance(node, RankNode):
            records = sorted(
                source.records,
                key=lambda item: _sortable(item.values.get(node.by.field)),
                reverse=node.direction == "descending",
            )
            return _records(tuple(records[:node.top_n]), source.completeness)
        if isinstance(node, SortNode):
            records = list(source.records)
            for key in reversed(node.keys):
                records.sort(key=lambda item: _sortable(item.values.get(key.field.field)),
                             reverse=key.direction == "descending")
            return _records(tuple(records), source.completeness)
        if isinstance(node, LimitNode):
            return _records(
                source.records[node.offset : node.offset + node.limit], source.completeness
            )
        if isinstance(node, ProjectNode):
            records = tuple(item.model_copy(update={"values": {
                field.name: item.values.get(
                    field.source_field.field if field.source_field else field.name
                )
                for field in node.fields}}) for item in source.records)
            return _records(records, source.completeness)
        if isinstance(node, TemporalConstraintNode):
            records = tuple(
                item
                for item in source.records
                if all(_temporal_match(item, predicate) for predicate in node.predicates)
            )
            return _records(records, source.completeness)
        if isinstance(node, ExistsNode):
            return StructuredValue(kind="boolean", records=source.records,
                                   scalar=bool(source.records), completeness=source.completeness)
        if isinstance(node, CompareNode):
            right = inputs[1]
            left_ids, right_ids = ({item.record_id for item in source.records},
                                   {item.record_id for item in right.records})
            values = {"values": left_ids == right_ids,
                      "populations": {"left": len(left_ids), "right": len(right_ids)},
                      "overlap": sorted(left_ids & right_ids),
                      "difference": sorted(left_ids - right_ids)}
            return StructuredValue(kind="comparison", records=source.records + right.records,
                                   scalar=values[node.comparison],
                                   completeness=_combined(source.completeness, right.completeness))
        raise StructuredExecutionError(f"unsupported structured operator: {node.kind}")

    def _result(self, step: ExecutionStep, value: StructuredValue, duration: int) -> EngineResult:
        evidence = _evidence(value)
        evidence_ids = tuple(item.evidence_id for item in evidence)
        rows: tuple[GroundedItem, ...] = ()
        aggregates: tuple[AggregateResult, ...] = ()
        if value.kind == "records":
            rows = tuple(GroundedItem(item_id=item.record_id, values=item.values,
                                      evidence_ids=tuple(e.evidence_id for e in item.evidence))
                         for item in value.records)
        elif value.kind == "groups":
            rows = tuple(GroundedItem(item_id=group.group_id,
                                      values={**group.keys, "confirmed_count": len(group.records)},
                                      evidence_ids=_record_evidence_ids(group.records))
                         for group in value.groups)
        elif value.aggregate_function and evidence_ids:
            aggregates = (AggregateResult(item_id=f"aggregate-{step.step_id}",
                                           values={"result": value.scalar},
                                           evidence_ids=evidence_ids,
                                           function=value.aggregate_function, value=value.scalar,
                                           population_count=value.completeness.confirmed_count),)
        elif evidence_ids:
            rows = (GroundedItem(item_id=f"value-{step.step_id}",
                                 values={"result": value.scalar}, evidence_ids=evidence_ids),)
        unsafe = value.completeness.not_safely_enumerable
        failures = (
            EngineFailure(
                step_id=step.step_id,
                engine=step.engine,
                capability=step.capability,
                reason="canonical population is not safely enumerable",
            ),
        ) if unsafe else ()
        items = rows + aggregates
        return EngineResult(
            result_id=f"result-{step.step_id}", workspace_id=self.workspace_id,
            generation_id=self.generation_id, step_id=step.step_id, engine=step.engine,
            capability=step.capability,
            state="partial" if failures or value.completeness.state == "partial" else "success",
            structured_rows=rows, aggregates=aggregates, text_evidence=evidence,
            provenance=tuple(ProvenanceLink(result_id=item.item_id,
                                             evidence_ids=item.evidence_ids) for item in items),
            completeness=value.completeness,
            confidence=1.0 if value.completeness.state == "complete" else 0.8,
            failures=failures,
            trace=EngineTrace(step_id=step.step_id, engine=step.engine,
                              capability=step.capability, duration_ms=duration,
                              counters={
                                  "confirmed_count": value.completeness.confirmed_count or 0
                              }),
        )


def _records(records, completeness):
    return StructuredValue(kind="records", records=records, completeness=completeness)


def _compare(actual, comparator, expected):
    if comparator == "exists":
        return actual is not None
    if comparator == "eq":
        return actual == expected
    if comparator == "not_eq":
        return actual != expected
    if comparator == "in":
        return actual in expected if isinstance(expected, list | tuple | set) else False
    if comparator == "contains":
        return str(expected).casefold() in str(actual).casefold()
    if comparator == "starts_with":
        return str(actual).casefold().startswith(str(expected).casefold())
    try:
        if comparator == "lt":
            return actual < expected
        if comparator == "lte":
            return actual <= expected
        if comparator == "gt":
            return actual > expected
        return actual >= expected
    except TypeError:
        return False


def _count(records, node):
    if not node.distinct_fields:
        return len(records)
    return len({tuple(item.values.get(field.field) for field in node.distinct_fields)
                for item in records})


def _aggregate(records, field, function):
    values = [item.values.get(field) for item in records if item.values.get(field) is not None]
    if not values:
        return None
    if function == "minimum":
        return min(values)
    if function == "maximum":
        return max(values)
    if function == "sum":
        return sum(values)
    return sum(values) / len(values)


def _sortable(value):
    normalized = value if isinstance(value, bool | int | float | str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True
    )
    return value is None, type(normalized).__name__, normalized


def _stable(value):
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return sha256(payload).hexdigest()[:24]


def _record_evidence_ids(records):
    return tuple(dict.fromkeys(e.evidence_id for item in records for e in item.evidence))


def _joined_record(left, right):
    return CanonicalRecord(
        record_id=f"join-{left.record_id}-{right.record_id}",
        resource="joined",
        values={**left.values, **{f"right.{key}": value for key, value in right.values.items()}},
        evidence=tuple(dict.fromkeys(left.evidence + right.evidence)),
    )


def _temporal_match(record, predicate):
    start = record.values.get("normalized_start")
    end = record.values.get("normalized_end") or start
    if predicate.normalized_start and (not start or str(start) < predicate.normalized_start):
        return False
    if predicate.normalized_end and (not end or str(end) > predicate.normalized_end):
        return False
    return True


def _evidence(value):
    records = value.records or tuple(item for group in value.groups for item in group.records)
    unique = {}
    for record in records:
        for evidence in record.evidence:
            unique.setdefault(evidence.evidence_id, evidence)
    return tuple(unique.values())


def _combined(left, right):
    complete = left.state == right.state == "complete" and left.generation_id == right.generation_id
    return CompletenessReport(
        coverage="exhaustive" if left.coverage == right.coverage == "exhaustive" else "grounded",
        state="complete" if complete else "partial",
        boundary=f"{left.boundary}; {right.boundary}" if complete else None,
        generation_id=left.generation_id if complete else None,
        candidate_count=(left.candidate_count or 0) + (right.candidate_count or 0),
        processed_count=(left.processed_count or 0) + (right.processed_count or 0),
        confirmed_count=(left.confirmed_count or 0) + (right.confirmed_count or 0),
        unresolved_candidate_ids=left.unresolved_candidate_ids + right.unresolved_candidate_ids,
        not_safely_enumerable=left.not_safely_enumerable or right.not_safely_enumerable,
        ready_projections=tuple(sorted(set(left.ready_projections) & set(right.ready_projections))),
    )
