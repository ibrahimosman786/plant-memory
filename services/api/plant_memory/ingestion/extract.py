"""Deterministic candidate-fact extraction from parsed spans into engineering records.

Rules:
- Structured sources (equipment list, I/O list, config export, catalogue, rates) yield
  `method=structured`, `review_status=recorded` assertions with row/record evidence.
- Datasheet PDFs yield regex-extracted assertions with the exact text line as evidence.
- Prose (narrative, notes, P&ID labels) yields tag references. Facts in prose are extracted
  only by the model path (`model_extract`) and stored as `candidate`, after verification that
  every cited evidence ID exists, belongs to this version, and contains the numeric value.
- Nothing here ever overwrites an existing assertion. Conflicts are preserved for the rules.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..contracts import ExtractionCandidates
from ..db.models import Assertion, CataloguePart, Equipment, EvidenceSpan, Rate, Relationship, UnresolvedReference
from .normalize import canonicalize, find_tags, normalize_tag, to_decimal, is_loose_mention
from .parsers import EQUIPMENT_HEADERS, IO_HEADERS, map_headers


@dataclass
class ExtractionStats:
    equipment_created: int = 0
    equipment_updated: int = 0
    assertions: int = 0
    relationships: int = 0
    unresolved: int = 0
    catalogue_parts: int = 0
    rates: int = 0
    candidates: int = 0
    rejected_candidates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Extractor:
    def __init__(self, session: Session, *, org_id: uuid.UUID, project_id: uuid.UUID, version_id: uuid.UUID):
        self.s = session
        self.org_id = org_id
        self.project_id = project_id
        self.version_id = version_id
        self.stats = ExtractionStats()
        self._eq_cache: dict[str, list[Equipment]] | None = None
        self._deferred_rows: list = []

    # ------------------------------------------------------------------ equipment helpers

    def _equipment_index(self) -> dict[str, list[Equipment]]:
        if self._eq_cache is None:
            rows = self.s.execute(select(Equipment).where(Equipment.project_id == self.project_id).order_by(Equipment.created_at)).scalars().all()
            idx: dict[str, list[Equipment]] = {}
            for e in rows:
                idx.setdefault(e.normalized_tag, []).append(e)
            self._eq_cache = idx
        return self._eq_cache

    def resolve(self, normalized: str) -> Equipment | None:
        matches = self._equipment_index().get(normalized, [])
        return matches[0] if matches else None

    def ensure_equipment(self, raw_tag: str, *, equipment_type: str = "unknown", description: str = "", location: str | None = None,
                         evidence_ids: list[uuid.UUID] | None = None, allow_duplicate: bool = False) -> Equipment:
        norm = normalize_tag(raw_tag) or raw_tag.strip().upper()
        existing = self._equipment_index().get(norm, [])
        if existing and not allow_duplicate:
            eq = existing[0]
            if eq.equipment_type == "unknown" and equipment_type != "unknown":
                eq.equipment_type = equipment_type
                eq.description = description or eq.description
                eq.location = location or eq.location
                eq.document_version_id = self.version_id
                eq.evidence_ids = list(evidence_ids or [])
                self.stats.equipment_updated += 1
            return eq
        eq = Equipment(org_id=self.org_id, project_id=self.project_id, raw_tag=raw_tag.strip(), normalized_tag=norm, equipment_type=equipment_type,
                       description=description, location=location, document_version_id=self.version_id if equipment_type != "unknown" else None,
                       evidence_ids=list(evidence_ids or []))
        self.s.add(eq)
        self.s.flush()
        self._equipment_index().setdefault(norm, []).append(eq)
        self.stats.equipment_created += 1
        return eq

    def add_assertion(self, eq: Equipment, attribute: str, value, unit: str | None, evidence_ids: list[uuid.UUID], *, method: str = "structured", review_status: str = "recorded") -> Assertion | None:
        if value is None or value == "":
            return None
        value_s = str(value).strip()
        num = to_decimal(value_s)
        canon_val, canon_unit, _ = canonicalize(num, unit) if num is not None else (None, unit, False)
        a = Assertion(org_id=self.org_id, project_id=self.project_id, equipment_id=eq.id, attribute=attribute, value=value_s, unit=(unit or None),
                      value_numeric=num, unit_canonical=canon_unit, value_canonical=canon_val, evidence_ids=evidence_ids,
                      document_version_id=self.version_id, method=method, review_status=review_status)
        self.s.add(a)
        self.stats.assertions += 1
        return a

    def add_relationship(self, source: Equipment, target: Equipment, rtype: str, evidence_ids: list[uuid.UUID], status: str = "recorded") -> None:
        self.s.add(Relationship(org_id=self.org_id, project_id=self.project_id, source_id=source.id, target_id=target.id, relationship_type=rtype,
                                evidence_ids=evidence_ids, document_version_id=self.version_id, status=status))
        self.stats.relationships += 1

    def add_unresolved(self, raw: str, norm: str, evidence_ids: list[uuid.UUID]) -> None:
        self.s.add(UnresolvedReference(org_id=self.org_id, project_id=self.project_id, raw_tag=raw, normalized_tag=norm, document_version_id=self.version_id, evidence_ids=evidence_ids))
        self.stats.unresolved += 1

    # ------------------------------------------------------------------ per-kind extractors

    def extract(self, kind: str, spans: list[EvidenceSpan], meta: dict) -> ExtractionStats:
        handler = {
            "equipment_list": self._equipment_list,
            "io_list": self._io_list,
            "config_export": self._config_export,
            "datasheet": self._datasheet,
            "catalogue": self._catalogue,
            "rates": self._rates,
            "narrative": self._prose,
            "note": self._prose,
            "pid": self._pid,
            "other": self._prose,
        }.get(kind, self._prose)
        handler(spans, meta)
        return self.stats

    def _row_fields(self, span: EvidenceSpan, mapping: dict[str, str]) -> dict[str, str]:
        cols = span.locator.get("columns") or span.locator.get("fields") or {}
        hmap = map_headers(list(cols.keys()), mapping)
        return {hmap[h]: (v or "").strip() for h, v in cols.items() if h in hmap}

    def _equipment_list(self, spans, meta) -> None:
        for sp in spans:
            if sp.kind != "row":
                continue
            f = self._row_fields(sp, EQUIPMENT_HEADERS)
            tag = f.get("tag")
            if not tag:
                continue
            # Duplicate rows for the same tag are preserved as separate equipment (rule: duplicate_tag).
            exists_from_this_doc = any(e.document_version_id == self.version_id for e in self._equipment_index().get(normalize_tag(tag) or tag.upper(), []))
            eq = self.ensure_equipment(tag, equipment_type=f.get("type") or "unknown", description=f.get("description", ""), location=f.get("location") or None,
                                       evidence_ids=[sp.id], allow_duplicate=exists_from_this_doc)
            for attr in ("manufacturer", "model", "service"):
                if f.get(attr):
                    self.add_assertion(eq, attr, f[attr], None, [sp.id])
            self._deferred_rows.append((eq, f, sp))
        # Relationships derived from structured columns, after every row exists so targets resolve.
        for eq, f, sp in self._deferred_rows:
            loc = f.get("location") or ""
            for raw, norm in find_tags(loc):
                host = self.resolve(norm)
                if host is not None and host.id != eq.id:
                    # "CP-101 / rack 0" → installed_in CP-101: a recorded fact from the location column.
                    self.add_relationship(eq, host, "installed_in", [sp.id])
            desc = f.get("description") or ""
            for raw, norm in find_tags(desc):
                other = self.resolve(norm)
                if other is None or other.id == eq.id:
                    continue
                # A tag in free-text description ("Tank T-101 level") implies a link whose type is inferred → candidate.
                etype = eq.equipment_type
                rtype = "measures" if (etype.endswith("_transmitter") or etype.endswith("_switch") or etype in ("analyzer",)) else "part_of"
                self.add_relationship(eq, other, rtype, [sp.id], status="candidate")
        self._deferred_rows = []

    def _io_list(self, spans, meta) -> None:
        for sp in spans:
            if sp.kind != "row":
                continue
            sheet = sp.locator.get("sheet", "")
            cols = sp.locator.get("columns") or {}
            if sheet.lower() == "panels" or ("channels_total" in cols):
                card_tag = cols.get("card")
                if not card_tag:
                    continue
                card = self.ensure_equipment(card_tag, evidence_ids=[sp.id])
                for attr in ("channels_total", "channels_used", "channels_spare"):
                    if cols.get(attr):
                        self.add_assertion(card, attr, cols[attr], None, [sp.id])
                    elif attr == "channels_spare":
                        self.stats.warnings.append(f"{card_tag}: spare channel count not recorded ({sp.locator.get('cell_range')})")
                continue
            f = self._row_fields(sp, IO_HEADERS)
            tag = f.get("tag")
            if not tag:
                continue
            eq = self.ensure_equipment(tag, evidence_ids=[sp.id])
            unit = f.get("unit") or None
            for attr in ("signal", "panel", "card", "channel", "wire", "terminal", "revision"):
                if f.get(attr):
                    self.add_assertion(eq, attr, f[attr], None, [sp.id])
            if f.get("range_lo") not in (None, ""):
                self.add_assertion(eq, "range_lo", f["range_lo"], unit, [sp.id])
            if f.get("range_hi") not in (None, ""):
                self.add_assertion(eq, "range_hi", f["range_hi"], unit, [sp.id])
            if unit:
                self.add_assertion(eq, "unit", unit, None, [sp.id])
            if f.get("card"):
                card = self.ensure_equipment(f["card"], evidence_ids=[sp.id])
                self.add_relationship(eq, card, "wired_to", [sp.id])

    def _config_export(self, spans, meta) -> None:
        for sp in spans:
            if sp.kind != "record":
                continue
            rec = sp.locator.get("fields") or {}
            tag = rec.get("tag")
            if not tag:
                continue
            eq = self.ensure_equipment(tag, evidence_ids=[sp.id])
            unit = rec.get("eng_unit") or None
            if rec.get("address"):
                self.add_assertion(eq, "address", rec["address"], None, [sp.id])
            if rec.get("card"):
                self.add_assertion(eq, "card", rec["card"], None, [sp.id])
                card = self.ensure_equipment(rec["card"], evidence_ids=[sp.id])
                self.add_relationship(eq, card, "wired_to", [sp.id])
            if rec.get("channel"):
                self.add_assertion(eq, "channel", rec["channel"], None, [sp.id])
            # Config scaling is comparable to instrument range: stored under the same attribute family.
            if rec.get("scale_lo"):
                self.add_assertion(eq, "range_lo", rec["scale_lo"], unit, [sp.id])
            if rec.get("scale_hi"):
                self.add_assertion(eq, "range_hi", rec["scale_hi"], unit, [sp.id])
            if unit:
                self.add_assertion(eq, "unit", unit, None, [sp.id])
            for a in ("alarm_lo", "alarm_hi"):
                if rec.get(a):
                    self.add_assertion(eq, a, rec[a], unit, [sp.id])

    DATASHEET_PATTERNS = {
        "range": re.compile(r"Calibrated range:\s*(-?[\d.]+)\s*to\s*(-?[\d.]+)\s*([A-Za-z%/°3²³]+)", re.I),
        "manufacturer": re.compile(r"Manufacturer:\s*(.+)$", re.I),
        "model": re.compile(r"Model:\s*(.+)$", re.I),
        "signal": re.compile(r"Output signal:\s*(.+)$", re.I),
        "power": re.compile(r"Power:\s*(.+)$", re.I),
    }
    DATASHEET_TITLE = re.compile(r"DATASHEET\s*[—\-–]\s*([A-Z]{1,4}-\d{2,4}[A-Z0-9]*)", re.I)

    def _datasheet(self, spans, meta) -> None:
        tag = None
        title_span = None
        for sp in spans:
            m = self.DATASHEET_TITLE.search(sp.text)
            if m:
                tag = m.group(1).upper()
                title_span = sp
                break
        if not tag:
            self.stats.warnings.append("datasheet: no tag found in title; nothing extracted")
            return
        eq = self.ensure_equipment(tag, evidence_ids=[title_span.id])
        found_range = False
        for sp in spans:
            text = sp.text.strip()
            m = self.DATASHEET_PATTERNS["range"].search(text)
            if m:
                lo, hi, unit = m.groups()
                self.add_assertion(eq, "range_lo", lo, unit, [sp.id])
                self.add_assertion(eq, "range_hi", hi, unit, [sp.id])
                self.add_assertion(eq, "unit", unit, None, [sp.id])
                found_range = True
                continue
            for attr in ("manufacturer", "model", "signal", "power"):
                m = self.DATASHEET_PATTERNS[attr].search(text)
                if m:
                    self.add_assertion(eq, attr, m.group(1).strip(), None, [sp.id])
        if not found_range:
            self.stats.warnings.append(f"{tag}: calibrated range not found in datasheet text (scan damage or layout); range remains unrecorded from this document")

    def _catalogue(self, spans, meta) -> None:
        for sp in spans:
            cols = sp.locator.get("columns") or {}
            pn = cols.get("part_number")
            if not pn:
                continue
            try:
                attrs = json.loads(cols.get("attributes_json") or "{}")
            except json.JSONDecodeError:
                attrs = {}
            price = to_decimal(cols.get("unit_price"))
            self.s.add(CataloguePart(org_id=self.org_id, project_id=self.project_id, part_number=pn.strip(), description=cols.get("description", ""), category=cols.get("category", "other"),
                                     attributes=attrs, unit_price=price, currency=cols.get("currency", "CAD") or "CAD", effective_date=_date(cols.get("effective_date")),
                                     source=cols.get("source", ""), document_version_id=self.version_id, evidence_ids=[sp.id]))
            self.stats.catalogue_parts += 1

    def _rates(self, spans, meta) -> None:
        for sp in spans:
            cols = sp.locator.get("columns") or {}
            code = cols.get("rate_code")
            rate = to_decimal(cols.get("rate"))
            if not code or rate is None:
                continue
            eff = _date(cols.get("effective_date"))
            self.s.add(Rate(org_id=self.org_id, project_id=self.project_id, rate_code=code.strip(), description=cols.get("description", ""), unit=cols.get("unit", "hour"),
                            rate=rate, currency=cols.get("currency", "CAD") or "CAD", effective_date=eff, rate_set_version=f"rates-{eff.isoformat()}",
                            document_version_id=self.version_id, evidence_ids=[sp.id]))
            self.stats.rates += 1

    def _prose(self, spans, meta) -> None:
        """Record tag references; resolved tags get no new assertions here (model path handles facts)."""
        seen: set[str] = set()
        for sp in spans:
            for raw, norm in find_tags(sp.text):
                key = f"{norm}:{sp.id}"
                if key in seen:
                    continue
                seen.add(key)
                eq = self.resolve(norm)
                if eq is None:
                    self.add_unresolved(raw, norm, [sp.id])
                elif is_loose_mention(raw, norm):
                    # Loose spelling that resolved: keep a candidate "mentioned_as" so ambiguity rules can inspect it.
                    self.add_assertion(eq, "mentioned_as", raw, None, [sp.id], method="structured", review_status="candidate")

    def _pid(self, spans, meta) -> None:
        for sp in spans:
            if sp.kind != "region":
                continue
            for raw, norm in find_tags(sp.text):
                eq = self.resolve(norm)
                if eq is None:
                    self.add_unresolved(raw, norm, [sp.id])
                else:
                    self.add_assertion(eq, "pid_region", f"page {sp.locator.get('page')}", None, [sp.id])

    # ------------------------------------------------------------------ model-assisted candidates

    def apply_model_candidates(self, candidates: ExtractionCandidates, spans_by_id: dict[str, EvidenceSpan]) -> None:
        """Verify and store model output. Rejections are recorded, never silently dropped."""
        for a in candidates.assertions:
            ev = [spans_by_id.get(e) for e in a.evidence_ids]
            if any(e is None for e in ev):
                self.stats.rejected_candidates.append(f"{a.raw_tag}.{a.attribute}: cites unknown evidence id")
                continue
            norm = normalize_tag(a.raw_tag)
            eq = self.resolve(norm) if norm else None
            if eq is None:
                self.stats.rejected_candidates.append(f"{a.raw_tag}.{a.attribute}: tag does not resolve to project equipment")
                continue
            if a.value is not None:
                num = to_decimal(a.value)
                joined = " ".join(e.text for e in ev)
                if num is not None and not _number_in_text(num, joined):
                    self.stats.rejected_candidates.append(f"{a.raw_tag}.{a.attribute}: value {a.value} not present in cited evidence")
                    continue
                if a.unit and a.unit.lower() not in joined.lower():
                    self.stats.rejected_candidates.append(f"{a.raw_tag}.{a.attribute}: unit {a.unit} not present in cited evidence")
                    continue
            self.add_assertion(eq, a.attribute, a.value, a.unit, [e.id for e in ev], method="model", review_status="candidate")
            self.stats.candidates += 1
        for r in candidates.relationships:
            ev = [spans_by_id.get(e) for e in r.evidence_ids]
            if any(e is None for e in ev):
                self.stats.rejected_candidates.append(f"{r.source_tag}->{r.target_tag}: cites unknown evidence id")
                continue
            src = self.resolve(normalize_tag(r.source_tag) or "")
            tgt = self.resolve(normalize_tag(r.target_tag) or "")
            if src is None or tgt is None:
                self.stats.rejected_candidates.append(f"{r.source_tag}->{r.target_tag}: endpoint does not resolve")
                continue
            self.add_relationship(src, tgt, r.relationship_type, [e.id for e in ev], status="candidate")
            self.stats.candidates += 1


def _number_in_text(num: Decimal, text: str) -> bool:
    candidates = {str(num), format(num, "f"), format(num.normalize(), "f")}
    if num == num.to_integral_value():
        candidates.add(str(int(num)))
    return any(re.search(rf"(?<![\d.]){re.escape(c)}(?![\d.])", text) for c in candidates)


def _date(value: str | None) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return date(1970, 1, 1)
