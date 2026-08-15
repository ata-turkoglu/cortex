"""Deterministic, conservative property-claim extraction and aggregation."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Chunk, Document

_PROPERTY = re.compile(
    r"\b(tapu|taşınmaz|tasinmaz|gayrimenkul|parsel|arsa|arazi|hisse|hissedar|pafta|ada)\b",
    re.I,
)
_FRACTION = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")
_DATE = re.compile(r"\b(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2}[-./]\d{4})\b")
_SHARE_CONTEXT = re.compile(
    r"\b(hisse(?:si|dar)?|pay(?:ı|lı)?|arsa\s+payı|mülkiyet\s+payı)\b", re.I
)
_LEGAL_CONTEXT = re.compile(
    r"\b(karar|esas|dosya|evrak|belge|başvuru)\s*(no|numarası)?\s*[:#-]?\s*$|\bsayı\s*[:#-]?\s*$",
    re.I,
)


@dataclass(frozen=True)
class ShareCandidate:
    text: str
    numerator: int
    denominator: int
    classification: str
    basis: str
    entity_bound: bool


@dataclass(frozen=True)
class OwnershipSpan:
    entity: str
    relation: str
    share: ShareCandidate | None
    source_span: str
    start: int
    end: int
    basis: tuple[str, ...]


def classify_shares(text: str, entity: str) -> tuple[ShareCandidate, ...]:
    """Classify bounded fraction context and bind a share only to its local entity clause."""
    candidates: list[ShareCandidate] = []
    for match in _FRACTION.finditer(text):
        value = match.group(0)
        before, after = (
            text[max(0, match.start() - 48) : match.start()],
            text[match.end() : match.end() + 48],
        )
        line_start = max(text.rfind("\n", 0, match.start()), text.rfind(";", 0, match.start())) + 1
        line_end_candidates = [
            index
            for index in (text.find("\n", match.end()), text.find(";", match.end()))
            if index >= 0
        ]
        line_end = min(line_end_candidates) if line_end_candidates else len(text)
        clause = text[line_start:line_end]
        around = f"{before} {after}"
        if re.search(
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", text[max(0, match.start() - 3) : match.end() + 6]
        ):
            classification, basis = "date", "date_pattern"
        elif _LEGAL_CONTEXT.search(before):
            classification, basis = "legal_identifier", "legal_number_context"
        elif not _SHARE_CONTEXT.search(around):
            classification, basis = "unknown_fraction", "no_share_context"
        else:
            classification = "ownership_share"
            basis = (
                "share_keyword_after" if _SHARE_CONTEXT.search(after) else "share_keyword_before"
            )
        entity_bound = entity.casefold() in clause.casefold()
        candidates.append(
            ShareCandidate(
                value, int(match.group(1)), int(match.group(2)), classification, basis, entity_bound
            )
        )
    return tuple(candidates)


def entity_share(text: str, entity: str) -> ShareCandidate | None:
    return next((span.share for span in ownership_spans(text, entity) if span.share), None)


def ownership_spans(text: str, entity: str) -> tuple[OwnershipSpan, ...]:
    """Extract direct ownership clauses; never bind by whole-chunk co-occurrence."""
    escaped = re.escape(entity)
    patterns = (
        (rf"(?P<share>\d+\s*/\s*\d+)\s*(?:hissesi|hisse|payı|pay)\s+{escaped}\b", "share_owner"),
        (
            rf"{escaped}(?:'|’)(?:in|ın|un|ün)\s+(?:payı|hissesi|hisse)\s+(?P<share>\d+\s*/\s*\d+)",
            "share_owner",
        ),
        (
            rf"{escaped}[^.;\n]{{0,120}}?(?P<share>\d+\s*/\s*\d+)\s*(?:hissesi|hisse|payı|pay)\b",
            "share_owner",
        ),
        (
            rf"{escaped}[^.;\n]{{0,120}}?(?:hissesi|hisse|payı|pay)\s+(?P<share>\d+\s*/\s*\d+)\b",
            "share_owner",
        ),
        (
            rf"{escaped}\s+(?:malikidir|maliki|hissedardır|adına\s+kayıtlı(?:dır)?|adına\s+tescilli(?:dir)?)",
            "registered_owner",
        ),
    )
    spans: list[OwnershipSpan] = []
    for pattern, relation in patterns:
        for match in re.finditer(pattern, text, re.I):
            share = None
            if raw_share := match.groupdict().get("share"):
                numerator, denominator = (int(value) for value in raw_share.split("/"))
                if denominator:
                    share = ShareCandidate(
                        raw_share,
                        numerator,
                        denominator,
                        "ownership_share",
                        "same_ownership_item",
                        True,
                    )
            spans.append(
                OwnershipSpan(
                    entity,
                    relation,
                    share,
                    match.group(0),
                    match.start(),
                    match.end(),
                    ("same_ownership_item", "entity_adjacent"),
                )
            )
    return tuple(spans)


_INVALID_CADASTRAL_VALUES = {"", "no", "nolu", "sayılı", "sayili", "parsel", "ada", "pafta"}


def _cadastral_value(label: str, text: str) -> tuple[str | None, str | None, str | None]:
    """Bind a numeric cadastral value to its own explicit label, in either word order."""
    suffix = r"(?:nolu|no'?lu|sayılı)?\s*" if label == "parsel" else ""
    patterns = (
        rf"\b(?P<value>\d+)\s*{suffix}(?:{label})(?:i)?\b",
        rf"\b(?:{label})(?:i)?\s*(?:no\.?\s*)?(?P<value>\d+)\b",
    )
    for pattern in patterns:
        if match := re.search(pattern, text, re.I):
            value = match.group("value").strip()
            if value.casefold() not in _INVALID_CADASTRAL_VALUES:
                return value, match.group(0), None
    return None, None, None


def _independent_section(text: str) -> tuple[str | None, str | None, str | None]:
    patterns = (
        r"\b(?P<value>\d+)\s*(?:nolu|no'?lu|sayılı)\s+bağımsız\s+bölüm\b",
        r"\bbağımsız\s+bölüm\s*(?:no\.?\s*)?(?P<value>\d+)\b",
        r"\bD\s*:\s*(?P<value>\d+)\b",
        r"\bdaire\s*(?P<value>\d+)\b",
    )
    for pattern in patterns:
        if match := re.search(pattern, text, re.I):
            return match.group("value"), match.group(0), None
    return None, None, None


def _location(label: str, text: str) -> str | None:
    pattern = (
        rf"\b(?:{label})\s*:\s*([\wÇĞİÖŞÜçğıöşü' -]+?)"
        r"(?=\s+(?:ilçe|ilce|mahalle|köy|koy|pafta|ada|parsel)\b|$)"
    )
    match = re.search(pattern, text, re.I)
    return match.group(1).strip(" ,;") if match and match.group(1) else None


def _normal(value: str | None) -> str | None:
    return unicodedata.normalize("NFC", value).casefold().strip() if value else None


@dataclass(frozen=True)
class PropertyClaim:
    entity: str
    property_type: str = "real_property"
    province: str | None = None
    district: str | None = None
    neighborhood: str | None = None
    sheet: str | None = None
    block: str | None = None
    parcel: str | None = None
    independent_section: str | None = None
    sheet_text: str | None = None
    block_text: str | None = None
    parcel_text: str | None = None
    independent_section_text: str | None = None
    extraction_basis: tuple[str, ...] = ()
    identity_complete: bool = False
    share_numerator: int | None = None
    share_denominator: int | None = None
    share_text: str | None = None
    normalized_share: str | None = None
    description: str | None = None
    record_date: str | None = None
    document_id: str = ""
    document_version_id: str = ""
    chunk_id: str = ""
    citation: str = ""
    confidence: float = 0.9
    warnings: tuple[str, ...] = ()

    @property
    def identity_key(self) -> tuple[tuple[str, str], ...]:
        fields = (
            ("province", self.province),
            ("district", self.district),
            ("neighborhood", self.neighborhood),
            ("sheet", self.sheet),
            ("block", self.block),
            ("parcel", self.parcel),
            ("independent_section", self.independent_section),
        )
        return tuple((name, _normal(value)) for name, value in fields if value)


@dataclass(frozen=True)
class PropertyRecord:
    identity_key: tuple[tuple[str, str], ...]
    representative: PropertyClaim
    claims: tuple[PropertyClaim, ...]
    deduplication_basis: tuple[str, ...]
    conflicts: tuple[dict[str, object], ...] = ()


def property_location_display(claim: PropertyClaim) -> str:
    """Display only validated field/value pairs; unknown cadastral fields are omitted."""
    cadastral = ", ".join(
        f"{value} {label}"
        for value, label in (
            (claim.sheet, "pafta"),
            (claim.block, "ada"),
            (claim.parcel, "parsel"),
            (claim.independent_section, "bağımsız bölüm"),
        )
        if value
    )
    location = ", ".join(
        value for value in (claim.province, claim.district, claim.neighborhood) if value
    )
    return " — ".join(value for value in (location, cadastral) if value)


@dataclass(frozen=True)
class AggregationResult:
    entity: str | None
    domain: str
    records: tuple[PropertyRecord, ...]
    complete: bool
    execution: dict[str, object]
    warnings: tuple[str, ...] = ()

    @property
    def distinct_property_count(self) -> int:
        return sum(record.representative.identity_complete for record in self.records)

    @property
    def distinct_parcel_count(self) -> int:
        parcel_keys = {
            next(
                (value for name, value in record.identity_key if name == "parcel"),
                record.identity_key,
            )
            for record in self.records
            if record.representative.parcel
        }
        return len(parcel_keys)


def extract_property_claims(chunk: Chunk, entity: str) -> list[PropertyClaim]:
    text = chunk.content
    if not _PROPERTY.search(text) or entity.casefold() not in text.casefold():
        return []
    label_first_sequence = re.search(
        r"\bpafta\s*(?P<sheet>\d+)\s+ada\s*(?P<block>\d+)\s+parsel\s*(?P<parcel>\d+)\b",
        text,
        re.I,
    )
    if label_first_sequence:
        sheet = label_first_sequence.group("sheet")
        block = label_first_sequence.group("block")
        parcel = label_first_sequence.group("parcel")
        sheet_text = f"pafta {sheet}"
        block_text = f"ada {block}"
        parcel_text = f"parsel {parcel}"
        sheet_warning = block_warning = parcel_warning = None
    else:
        sheet, sheet_text, sheet_warning = _cadastral_value("pafta", text)
        block, block_text, block_warning = _cadastral_value("ada", text)
        parcel, parcel_text, parcel_warning = _cadastral_value("parsel", text)
    section, section_text, section_warning = _independent_section(text)
    numerator = denominator = None
    share_text = normalized_share = None
    warnings: list[str] = []
    warnings.extend(
        warning
        for warning in (sheet_warning, block_warning, parcel_warning, section_warning)
        if warning
    )
    if not parcel:
        warnings.extend(("missing_parcel", "partial_property_identity"))
    share = entity_share(text, entity)
    if share:
        numerator, denominator, share_text = share.numerator, share.denominator, share.text
        divisor = math.gcd(numerator, denominator)
        normalized_share = f"{numerator // divisor}/{denominator // divisor}"
    if not any((sheet, block, parcel, section)):
        return []
    date = _DATE.search(text)
    return [
        PropertyClaim(
            entity=entity,
            province=_location("il", text),
            district=_location("ilçe|ilce", text),
            neighborhood=_location("mahalle|köy|koy", text),
            sheet=sheet,
            block=block,
            parcel=parcel,
            independent_section=section,
            sheet_text=sheet_text,
            block_text=block_text,
            parcel_text=parcel_text,
            independent_section_text=section_text,
            extraction_basis=(
                ("explicit_full_sequence",)
                if sheet and block and parcel
                else tuple(
                    basis
                    for value, basis in (
                        (sheet, "explicit_sheet_label"),
                        (block, "explicit_block_label"),
                        (parcel, "explicit_parcel_label"),
                        (section, "explicit_independent_section_label"),
                    )
                    if value
                )
            ),
            identity_complete=bool(parcel),
            share_numerator=numerator,
            share_denominator=denominator,
            share_text=share_text,
            normalized_share=normalized_share,
            record_date=date.group(0) if date else None,
            document_id=chunk.document_id,
            document_version_id=chunk.document_version_id,
            chunk_id=chunk.id,
            citation=f"{chunk.document_id}:{chunk.ordinal + 1}",
            confidence=0.98 if sheet and block and parcel else 0.9,
            warnings=tuple(warnings),
        )
    ]


def aggregate_properties(
    session: Session, workspace_id: str, entity: str | None, aliases: tuple[str, ...]
) -> AggregationResult:
    active_documents = (
        session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.workspace_id == workspace_id, Document.deleted_at.is_(None))
        )
        or 0
    )
    chunks = session.scalars(
        select(Chunk)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.workspace_id == workspace_id,
            Chunk.deleted_at.is_(None),
            Document.deleted_at.is_(None),
            Chunk.document_version_id == Document.active_version_id,
        )
    ).all()
    names = tuple(dict.fromkeys(name for name in ((entity,) if entity else ()) + aliases if name))
    candidate_chunks = [
        chunk
        for chunk in chunks
        if any(name.casefold() in chunk.content.casefold() for name in names)
        and _PROPERTY.search(chunk.content)
    ]
    claims = [
        claim
        for chunk in candidate_chunks
        for claim in extract_property_claims(chunk, entity or names[0])
    ]
    groups: dict[tuple[tuple[str, str], ...], list[PropertyClaim]] = {}
    for claim in claims:
        if claim.identity_key:
            groups.setdefault(claim.identity_key, []).append(claim)
    records: list[PropertyRecord] = []
    for key, grouped in groups.items():
        shares = sorted({item.normalized_share for item in grouped if item.normalized_share})
        conflicts = ({"field": "share", "values": shares},) if len(shares) > 1 else ()
        records.append(
            PropertyRecord(
                key, grouped[0], tuple(grouped), tuple(f"same_{name}" for name, _ in key), conflicts
            )
        )
    documents = {chunk.document_id for chunk in candidate_chunks}
    execution = {
        "exhaustive_requested": True,
        "workspace_active_document_count": active_documents,
        "workspace_active_chunk_count": len(chunks),
        "candidate_document_count": len(documents),
        "candidate_chunk_count": len(candidate_chunks),
        "processed_document_count": len(documents),
        "processed_chunk_count": len(candidate_chunks),
        "extracted_claim_count": len(claims),
        "normalized_claim_count": len(claims),
        "deduplicated_property_count": len(records),
        "complete": True,
    }
    return AggregationResult(entity, "property", tuple(records), True, execution)
