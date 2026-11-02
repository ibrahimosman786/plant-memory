"""Format parsers. Each returns a ParsedDocument of evidence spans with exact source locators.

| Input              | Method                               | Locator                         |
|--------------------|--------------------------------------|---------------------------------|
| CSV                | strict csv + declared column mapping | {"row": n, "columns": {...}}    |
| XLSX               | openpyxl (formulas preserved)        | {"sheet": s, "row": n, "cell_range": "A2:J2"} |
| text PDF           | Docling if installed, else pypdfium2 | {"page": p, "bbox": [x0,y0,x1,y1]} |
| scanned PDF        | RapidOCR if installed, else partial  | {"page": p, "bbox": [...], "ocr": true} |
| DOCX               | python-docx                          | {"paragraph": i} / {"table": t, "row": r} |
| config CSV         | PM-CONFIG-CSV adapter                | {"record": n, "field": f}       |
| P&ID PDF           | text/tag extraction with regions     | {"page": p, "bbox": [...], "region": true} |

Spreadsheet formulas are never executed; cached values are used and flagged when absent.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from docx import Document as DocxDocument
from openpyxl import load_workbook


@dataclass
class SpanDraft:
    kind: str  # text|table|row|cell|record|region
    locator: dict
    text: str
    tags: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    format: str
    spans: list[SpanDraft]
    page_count: int | None = None
    page_images: dict[int, bytes] = field(default_factory=dict)  # page -> PNG
    warnings: list[str] = field(default_factory=list)
    partial: bool = False
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- CSV

CONFIG_MAGIC = "PM-CONFIG-CSV"

# Declared header mappings. Unknown headers are kept verbatim; only mapped ones drive extraction.
EQUIPMENT_HEADERS = {
    "tag": "tag", "tag no.": "tag", "tag no": "tag", "tagno": "tag",
    "type": "type", "equip type": "type", "equipment type": "type",
    "description": "description", "desc": "description",
    "location": "location", "area": "location",
    "manufacturer": "manufacturer", "mfr": "manufacturer",
    "model": "model", "model no": "model", "model no.": "model",
    "service": "service",
}
IO_HEADERS = {
    "tag": "tag", "signal": "signal", "i/o type": "signal", "io type": "signal", "type": "signal",
    "panel": "panel", "card": "card", "slot": "card", "channel": "channel", "ch": "channel",
    "range_lo": "range_lo", "lrv": "range_lo", "range lo": "range_lo", "low": "range_lo",
    "range_hi": "range_hi", "urv": "range_hi", "range hi": "range_hi", "high": "range_hi",
    "unit": "unit", "eu": "unit", "units": "unit", "eng unit": "unit",
    "wire": "wire", "cable": "wire", "terminal": "terminal", "term": "terminal",
    "revision": "revision", "rev": "revision",
}
CATALOGUE_HEADERS = {"part_number": "part_number", "description": "description", "category": "category", "attributes_json": "attributes_json",
                     "unit_price": "unit_price", "currency": "currency", "effective_date": "effective_date", "source": "source"}
RATES_HEADERS = {"rate_code": "rate_code", "description": "description", "unit": "unit", "rate": "rate", "currency": "currency", "effective_date": "effective_date"}


def map_headers(headers: list[str], mapping: dict[str, str]) -> dict[str, str]:
    """original header -> canonical field (only for recognised headers)."""
    out = {}
    for h in headers:
        key = (h or "").strip().lower()
        if key in mapping:
            out[h] = mapping[key]
    return out


def parse_csv(data: bytes) -> ParsedDocument:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return ParsedDocument("csv", [], warnings=["empty file"])
    if rows[0] and rows[0][0].strip().upper() == "FORMAT" and len(rows[0]) > 1 and rows[0][1].strip() == CONFIG_MAGIC:
        return _parse_config_csv(rows)
    headers = rows[0]
    spans = []
    for i, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        cols = {headers[j] if j < len(headers) else f"col{j}": row[j] for j in range(len(row))}
        line = " | ".join(f"{k}: {v}" for k, v in cols.items() if v.strip())
        spans.append(SpanDraft("row", {"row": i, "columns": cols}, line))
    return ParsedDocument("csv", spans, meta={"headers": headers})


def _parse_config_csv(rows: list[list[str]]) -> ParsedDocument:
    version = rows[0][2].strip() if len(rows[0]) > 2 else "1.0"
    headers = rows[1]
    spans = []
    for i, row in enumerate(rows[2:], start=1):
        if not any(c.strip() for c in row):
            continue
        rec = {headers[j]: row[j] for j in range(min(len(headers), len(row)))}
        line = " | ".join(f"{k}: {v}" for k, v in rec.items() if v.strip())
        spans.append(SpanDraft("record", {"record": i, "fields": rec}, line))
    return ParsedDocument("config_csv", spans, meta={"format": CONFIG_MAGIC, "format_version": version, "headers": headers})


# --------------------------------------------------------------------------- XLSX

def parse_xlsx(data: bytes) -> ParsedDocument:
    wb_formula = load_workbook(io.BytesIO(data), data_only=False, read_only=True)
    wb_cached = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    spans: list[SpanDraft] = []
    warnings: list[str] = []
    meta: dict = {"sheets": {}}
    for ws in wb_formula.worksheets:
        ws_cached = wb_cached[ws.title]
        rows_f = list(ws.iter_rows(values_only=False))
        rows_c = list(ws_cached.iter_rows(values_only=True))
        if not rows_f:
            continue
        headers = [str(c.value).strip() if c.value is not None else f"col{idx}" for idx, c in enumerate(rows_f[0])]
        meta["sheets"][ws.title] = {"headers": headers, "rows": len(rows_f) - 1}
        for r_idx, (frow, crow) in enumerate(zip(rows_f[1:], rows_c[1:]), start=2):
            cols = {}
            formulas = {}
            for j, cell in enumerate(frow):
                header = headers[j] if j < len(headers) else f"col{j}"
                fval = cell.value
                cval = crow[j] if j < len(crow) else None
                if isinstance(fval, str) and fval.startswith("="):
                    formulas[header] = fval
                    if cval is None:
                        warnings.append(f"{ws.title}!{cell.coordinate}: formula {fval} has no cached value")
                        cols[header] = ""
                    else:
                        cols[header] = str(cval)
                else:
                    cols[header] = "" if fval is None else str(fval)
            if not any(v.strip() for v in cols.values()):
                continue
            first = frow[0].coordinate if frow else f"A{r_idx}"
            last = frow[-1].coordinate if frow else first
            loc = {"sheet": ws.title, "row": r_idx, "cell_range": f"{first}:{last}", "columns": cols}
            if formulas:
                loc["formulas"] = formulas
            line = " | ".join(f"{k}: {v}" for k, v in cols.items() if v.strip())
            spans.append(SpanDraft("row", loc, line))
    return ParsedDocument("xlsx", spans, warnings=warnings, meta=meta)


# --------------------------------------------------------------------------- PDF

def _docling_available() -> bool:
    try:
        import docling  # noqa: F401

        return True
    except Exception:
        return False


def _ocr_available() -> bool:
    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: F401

        return True
    except Exception:
        return False


def parse_pdf(data: bytes, *, render_pages: bool = True, ocr: bool = True) -> ParsedDocument:
    """Text PDF via pypdfium2 line boxes (Docling when installed adds table structure). Pages
    without a text layer go to OCR when available; otherwise the document is marked partial."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    spans: list[SpanDraft] = []
    warnings: list[str] = []
    images: dict[int, bytes] = {}
    partial = False
    page_count = len(pdf)
    for p in range(page_count):
        page = pdf[p]
        width, height = page.get_size()
        tp = page.get_textpage()
        n_rects = tp.count_rects()
        page_lines: list[tuple[tuple[float, float, float, float], str]] = []
        for i in range(n_rects):
            l, b, r, t = tp.get_rect(i)
            txt = tp.get_text_bounded(l, b, r, t).strip()
            if txt:
                # Convert PDF coordinates (origin bottom-left) to top-left image coordinates.
                page_lines.append(((l, height - t, r, height - b), txt))
        if render_pages:
            bitmap = page.render(scale=1.5)
            buf = io.BytesIO()
            bitmap.to_pil().save(buf, format="PNG")
            images[p + 1] = buf.getvalue()
        if page_lines:
            for (x0, y0, x1, y1), txt in page_lines:
                spans.append(SpanDraft("text", {"page": p + 1, "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)], "page_size": [width, height]}, txt))
        else:
            if ocr and _ocr_available() and (p + 1) in images:
                try:
                    spans.extend(_ocr_page(images[p + 1], p + 1, width, height, scale=1.5))
                    warnings.append(f"page {p + 1}: no text layer; OCR applied (verify values against the page image)")
                except Exception as exc:  # OCR failure is visible, not silent
                    partial = True
                    warnings.append(f"page {p + 1}: OCR failed: {exc}")
            else:
                partial = True
                warnings.append(f"page {p + 1}: no text layer and OCR unavailable; page requires manual review")
        tp.close()
        page.close()
    pdf.close()
    if _docling_available() and spans:
        try:
            spans = _docling_tables(data, spans)
        except Exception as exc:
            warnings.append(f"docling table extraction skipped: {exc}")
    return ParsedDocument("pdf", spans, page_count=page_count, page_images=images, warnings=warnings, partial=partial)


def _ocr_page(png: bytes, page_no: int, width: float, height: float, scale: float) -> list[SpanDraft]:
    from rapidocr_onnxruntime import RapidOCR
    from PIL import Image
    import numpy as np

    engine = RapidOCR()
    img = Image.open(io.BytesIO(png)).convert("RGB")
    result, _ = engine(np.array(img))
    spans = []
    for box, txt, conf in result or []:
        xs = [pt[0] / scale for pt in box]
        ys = [pt[1] / scale for pt in box]
        spans.append(SpanDraft("text", {"page": page_no, "bbox": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)], "page_size": [width, height], "ocr": True, "confidence": round(float(conf), 3)}, txt))
    return spans


def _docling_tables(data: bytes, spans: list[SpanDraft]) -> list[SpanDraft]:
    """Add table spans from Docling when present. Text spans from pypdfium2 are kept for bbox fidelity."""
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import DocumentStream

    conv = DocumentConverter()
    result = conv.convert(DocumentStream(name="doc.pdf", stream=io.BytesIO(data)))
    for t_idx, table in enumerate(result.document.tables):
        df = table.export_to_dataframe()
        prov = table.prov[0] if table.prov else None
        page = prov.page_no if prov else 1
        bbox = [prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b] if prov else None
        spans.append(SpanDraft("table", {"page": page, "bbox": bbox, "table": t_idx, "columns": list(map(str, df.columns))}, df.to_csv(index=False)))
    return spans


def parse_pid(data: bytes) -> ParsedDocument:
    """P&ID: extract visible tag labels with regions. Connections are NOT inferred from proximity."""
    from .normalize import find_tags

    doc = parse_pdf(data, render_pages=True, ocr=True)
    regions: list[SpanDraft] = []
    for sp in doc.spans:
        tags = find_tags(sp.text)
        if tags:
            loc = dict(sp.locator)
            loc["region"] = True
            regions.append(SpanDraft("region", loc, sp.text, tags=[n for _, n in tags]))
        else:
            regions.append(sp)
    doc.spans = regions
    doc.format = "pid"
    doc.warnings.append("P&ID connections are candidates until confirmed by an engineer; no line tracing performed.")
    return doc


# --------------------------------------------------------------------------- DOCX / text

def parse_docx(data: bytes) -> ParsedDocument:
    doc = DocxDocument(io.BytesIO(data))
    spans: list[SpanDraft] = []
    heading = ""
    for i, para in enumerate(doc.paragraphs):
        txt = para.text.strip()
        if not txt:
            continue
        style = (para.style.name or "").lower() if para.style is not None else ""
        if style.startswith("heading") or style == "title":
            heading = txt
        spans.append(SpanDraft("text", {"paragraph": i, "heading": heading, "style": style}, txt))
    for t_idx, table in enumerate(doc.tables):
        headers = [c.text.strip() for c in table.rows[0].cells] if table.rows else []
        for r_idx, row in enumerate(table.rows[1:], start=1):
            cells = {headers[j] if j < len(headers) else f"col{j}": c.text.strip() for j, c in enumerate(row.cells)}
            line = " | ".join(f"{k}: {v}" for k, v in cells.items() if v)
            spans.append(SpanDraft("row", {"table": t_idx, "row": r_idx, "columns": cells}, line))
    return ParsedDocument("docx", spans)


def parse_text(data: bytes) -> ParsedDocument:
    text = data.decode("utf-8", errors="replace")
    spans = []
    for i, para in enumerate(re.split(r"\n\s*\n", text)):
        p = para.strip()
        if p:
            spans.append(SpanDraft("text", {"paragraph": i}, p))
    return ParsedDocument("text", spans)


def parse_bytes(filename: str, content_type: str, data: bytes, *, kind_hint: str | None = None) -> ParsedDocument:
    name = filename.lower()
    if name.endswith(".csv"):
        return parse_csv(data)
    if name.endswith(".xlsx"):
        return parse_xlsx(data)
    if name.endswith(".pdf"):
        return parse_pid(data) if kind_hint == "pid" or "pid" in name or "p&id" in name else parse_pdf(data)
    if name.endswith(".docx"):
        return parse_docx(data)
    if name.endswith((".txt", ".md")):
        return parse_text(data)
    raise ValueError(f"unsupported file type: {filename} ({content_type})")
