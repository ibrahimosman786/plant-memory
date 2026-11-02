"""Serialize a Bundle to files that exercise every supported ingestion path."""

from __future__ import annotations

import csv
import io
import json
import random
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont
from docx import Document

from .bundle import Bundle


STANDARD_EQ_COLUMNS = ["tag", "type", "description", "location", "manufacturer", "model", "service"]
LEGACY_EQ_COLUMNS = {"tag": "Tag No.", "type": "Equip Type", "description": "Description", "location": "Area", "manufacturer": "Mfr", "model": "Model No", "service": "Service"}

STANDARD_IO_COLUMNS = ["tag", "signal", "panel", "card", "channel", "range_lo", "range_hi", "unit", "wire", "terminal"]
LEGACY_IO_COLUMNS = {"tag": "TAG", "signal": "I/O TYPE", "panel": "PANEL", "card": "SLOT", "channel": "CH", "range_lo": "LRV", "range_hi": "URV", "unit": "EU", "wire": "CABLE", "terminal": "TERM"}


def write_equipment_csv(b: Bundle, path: Path) -> None:
    cols = STANDARD_EQ_COLUMNS
    header = cols if b.template == "standard" else [LEGACY_EQ_COLUMNS[c] for c in cols]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in b.equipment_rows:
            w.writerow([r[c] for c in cols])


def write_io_xlsx(b: Bundle, path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "IO"
    cols = STANDARD_IO_COLUMNS
    header = cols if b.template == "standard" else [LEGACY_IO_COLUMNS[c] for c in cols]
    ws.append(header)
    for r in b.io_rows:
        ws.append([r[c] for c in cols])
    # Second sheet: panel schedule with a formula (never executed by the ingester).
    ps = wb.create_sheet("Panels")
    ps.append(["card", "model", "channels_total", "channels_used", "channels_spare"])
    cards = {}
    for r in b.io_rows:
        cards[r["card"]] = cards.get(r["card"], 0) + 1
    totals = {"AI-01": 8, "AI-02": 8, "AO-01": 4, "DI-01": 16, "DI-02": 16, "DO-01": 16}
    row = 2
    spare_recorded = not any(f.kind == "spare_capacity_unrecorded" for f in b.faults)
    for card, used in sorted(cards.items()):
        ps.append([card, "", totals.get(card, ""), used, f"=C{row}-D{row}" if spare_recorded else ""])
        row += 1
    wb.save(path)


def write_config_csv(b: Bundle, path: Path) -> None:
    """Documented synthetic configuration export (see docs/formats/config-csv.md)."""
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["FORMAT", "PM-CONFIG-CSV", "1.0"])
        w.writerow(["tag", "address", "card", "channel", "scale_lo", "scale_hi", "eng_unit", "alarm_lo", "alarm_hi", "description"])
        for r in b.config_rows:
            w.writerow([r.tag, r.address, r.card, r.channel, r.scale_lo or "", r.scale_hi or "", r.eng_unit or "", r.alarm_lo or "", r.alarm_hi or "", r.description])


def write_catalogue_csv(b: Bundle, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["part_number", "description", "category", "attributes_json", "unit_price", "currency", "effective_date", "source"])
        for p in b.catalogue:
            w.writerow([p.part_number, p.description, p.category, json.dumps(p.attributes), p.unit_price or "", p.currency, p.effective_date, p.source])


def write_rates_csv(b: Bundle, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rate_code", "description", "unit", "rate", "currency", "effective_date"])
        for r in b.rates:
            w.writerow([r.rate_code, r.description, r.unit, r.rate, r.currency, r.effective_date])


def write_narrative_docx(b: Bundle, path: Path) -> None:
    doc = Document()
    doc.add_heading(f"Control Narrative — {b.plant.name}", level=0)
    doc.add_paragraph(f"Revision {b.revision_label}. Fictional document generated for software testing.")
    for title, body in b.narrative:
        doc.add_heading(title, level=1)
        doc.add_paragraph(body)
    doc.add_heading("Appendix A — Alarm summary", level=1)
    table = doc.add_table(rows=1, cols=3)
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Tag", "Alarm", "Action"
    for tag, alarm, action in (("LSH-101", "High level", "Alarm on HMI-101"), ("LSL-101", "Low level", "Stop pumps"), ("PT-104", "High pressure", "Reduce speed, alarm"), ("TT-101A", "High-high bearing temp", "Trip P-101A"), ("TT-101B", "High-high bearing temp", "Trip P-101B")):
        row = table.add_row().cells
        row[0].text, row[1].text, row[2].text = tag, alarm, action
    doc.save(path)


def write_datasheet_pdf(ds, path: Path, rnd: random.Random) -> None:
    lines = [
        f"INSTRUMENT DATASHEET — {ds.tag}",
        f"Manufacturer: {ds.manufacturer}",
        f"Model: {ds.model}",
        f"Calibrated range: {ds.range_lo} to {ds.range_hi} {ds.unit}",
        f"Output signal: {ds.attributes.get('signal', '4-20 mA')}",
        f"Power: {ds.attributes.get('power', '24 VDC loop')}",
        "Process connection: 1/2 in NPT",
        "Accuracy: 0.075 % of span (fictional)",
        "Ambient limits: -40 to 85 degC",
        "Hazardous area: none (fictional general purpose)",
    ] + [f"Note: {n}" for n in ds.notes] + ["Fictional document generated for software testing. Not a real instrument."]
    if not ds.scanned:
        c = canvas.Canvas(str(path), pagesize=letter)
        y = 740
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, y, lines[0])
        c.setFont("Helvetica", 11)
        for ln in lines[1:]:
            y -= 22
            c.drawString(72, y, ln)
        c.showPage()
        c.save()
        return
    # Scanned: render text into an image, drop some lines, embed as the only content.
    img = Image.new("L", (1275, 1650), color=235)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    y = 120
    for ln in lines:
        if rnd.random() < ds.scan_damage and ln is not lines[0]:
            # damaged line: smeared block
            draw.rectangle([140, y, 1100, y + 30], fill=150)
        else:
            draw.text((140, y), ln, fill=20, font=font)
        y += 48
    # noise speckles
    for _ in range(1500):
        x, yy = rnd.randint(0, 1274), rnd.randint(0, 1649)
        img.putpixel((x, yy), rnd.randint(60, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    c = canvas.Canvas(str(path), pagesize=letter)
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(buf), 0, 0, width=612, height=792)
    c.showPage()
    c.save()


def write_pid_pdf(b: Bundle, path: Path) -> dict:
    """Simplified P&ID: symbols with tag labels and process lines. Returns the region map (ground truth)."""
    c = canvas.Canvas(str(path), pagesize=landscape(letter))
    width, height = landscape(letter)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, height - 40, f"P&ID — {b.plant.name} — Rev {b.revision_label} (fictional, simplified)")
    c.setFont("Helvetica", 8)
    regions = {}
    layout = b.plant.pid_layout
    # lines
    c.setLineWidth(1.2)
    for a, bb in b.plant.pid_lines:
        if a in layout and bb in layout:
            (x1, y1, _), (x2, y2, _) = layout[a], layout[bb]
            c.line(x1 + 15, y1, x2 - 15, y2)
    # symbols
    for tag, (x, y, sym) in layout.items():
        if sym == "tank":
            c.rect(x - 25, y - 40, 50, 80)
        elif sym == "pump":
            c.circle(x, y, 15)
            c.line(x - 15, y, x + 15, y)
        elif sym in ("valve", "cvalve", "psv"):
            c.line(x - 10, y - 8, x + 10, y + 8); c.line(x - 10, y + 8, x + 10, y - 8)
            c.line(x - 10, y - 8, x - 10, y + 8); c.line(x + 10, y - 8, x + 10, y + 8)
            if sym == "cvalve":
                c.line(x, y, x, y + 18); c.arc(x - 8, y + 14, x + 8, y + 26)
        elif sym == "inst":
            c.circle(x, y, 11)
        label_y = y - 55 if sym == "tank" else y - 24
        c.drawString(x - 18, label_y, tag)
        regions[tag] = {"page": 1, "bbox": [x - 25, label_y - 4, x + 25, y + 20]}
    for tag, x, y in b.pid_extra_tags:
        c.circle(x, y, 11)
        c.drawString(x - 18, y - 24, tag)
        regions[tag] = {"page": 1, "bbox": [x - 25, y - 28, x + 25, y + 12]}
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(40, 30, "Connections shown are process lines only. Instrument signal wiring is in the I/O list. Fictional drawing.")
    c.showPage()
    c.save()
    return regions


def write_bundle(b: Bundle, out: Path, rnd: random.Random) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    docs = out / "documents"
    docs.mkdir(exist_ok=True)
    (docs / "datasheets").mkdir(exist_ok=True)
    write_equipment_csv(b, docs / "equipment_list.csv")
    write_io_xlsx(b, docs / "io_list.xlsx")
    write_config_csv(b, docs / "config_export.csv")
    write_catalogue_csv(b, docs / "catalogue.csv")
    write_rates_csv(b, docs / "rates.csv")
    write_narrative_docx(b, docs / "control_narrative.docx")
    for ds in b.datasheets:
        write_datasheet_pdf(ds, docs / "datasheets" / f"{ds.tag}.pdf", rnd)
    regions = write_pid_pdf(b, docs / "pid.pdf")
    for name, text in b.extra_documents:
        (docs / name).write_text(text)
    manifest = {
        "variant_id": b.variant_id,
        "family": b.family,
        "template": b.template,
        "revision": b.revision_label,
        "documents": sorted(str(p.relative_to(out)) for p in docs.rglob("*") if p.is_file()),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return regions
