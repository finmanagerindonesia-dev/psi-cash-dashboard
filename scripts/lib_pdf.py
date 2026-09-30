"""Ready-to-print PDF generation for CF Summary — Detailed Table.

Generates a landscape A4 PDF containing the same Detailed Table shown
in the dashboard, rendered in both IDR (in Million) and INR (in Lakh).
Uses reportlab (server-side generation during refresh.bat).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from lib_pivot import month_label, month_long_label


# Palette (matches dashboard "clean SaaS" look)
BRAND = colors.HexColor("#1E40AF")
BRAND_LIGHT = colors.HexColor("#EFF6FF")
TEXT = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
POS = colors.HexColor("#059669")
NEG = colors.HexColor("#DC2626")
WARN_BG = colors.HexColor("#FEF3C7")
WARN_BORDER = colors.HexColor("#F59E0B")
SECTION_BG = colors.HexColor("#1E40AF")
SECTION_TEXT = colors.white
SUBSECTION_BG = colors.HexColor("#DBEAFE")
SUBTOTAL_BG = colors.HexColor("#EFF6FF")
ALT_ROW_BG = colors.HexColor("#FAFBFD")


def _fmt_amount(v, divisor):
    """Format numeric amount with divisor. Neg = parentheses. Zero = '-'."""
    if v is None:
        return ""
    x = v / divisor
    if abs(x) < 0.5:
        return "-"
    s = f"{abs(x):,.0f}"
    return f"({s})" if x < 0 else s


def _row_style(kind, indent):
    """Return per-row style hints."""
    if kind == "beginning_balance" or kind == "ending_balance":
        return {"bg": WARN_BG, "bold": True, "border": WARN_BORDER, "color": TEXT}
    if kind == "section_header":
        return {"bg": SECTION_BG, "bold": True, "color": SECTION_TEXT}
    if kind == "subsection":
        return {"bg": SUBSECTION_BG, "bold": True, "color": TEXT}
    if kind in ("subtotal_section", "subtotal", "net"):
        return {"bg": SUBTOTAL_BG, "bold": True, "color": TEXT}
    return {"bg": None, "bold": False, "color": TEXT}


def _build_columns(periods, all_periods, current_period):
    """Return column headers and period keys used for each column.

    Layout: <Particular> | <period1> ... <periodN> | <YTD year> | <MTD as-of> | <YTD as-of>
    """
    year = periods[0][:4] if periods else datetime.now().strftime("%Y")
    cols = []
    keys = []
    cols.append("Particular")
    keys.append(None)
    for p in periods:
        cols.append(month_label(p))
        keys.append(("month", p))
    cols.append(f"YTD {year}")
    keys.append(("ytd", year))
    if current_period:
        cols.append("MTD as of")
        keys.append(("mtd", current_period))
    cols.append("YTD as of")
    keys.append(("ytd_asof", None))
    return cols, keys, year


def _cell_value(line, key, all_periods, current_period, divisor, inr_rate=None):
    """Compute cell numeric value for a given column key. Returns formatted string."""
    values = line.get("values") or {}
    kind = line.get("kind")

    def _conv(v):
        if v is None:
            return None
        # If INR conversion needed: convert IDR -> INR, then apply divisor (in INR terms)
        if inr_rate:
            return v / inr_rate
        return v

    if key is None:
        return None
    kt, arg = key

    if kt == "month":
        v = _conv(values.get(arg))
        return _fmt_amount(v, divisor)

    if kt == "ytd":
        # For balance rows, YTD uses first/last period end value
        if kind == "beginning_balance":
            first_p = all_periods[0] if all_periods else None
            v = _conv(values.get(first_p)) if first_p else None
            return _fmt_amount(v, divisor)
        if kind == "ending_balance":
            last_p = all_periods[-1] if all_periods else None
            v = _conv(values.get(last_p)) if last_p else None
            return _fmt_amount(v, divisor)
        # regular: sum of all periods in current year
        year = arg
        total = 0.0
        seen = False
        for p, v in values.items():
            if p.startswith(year):
                total += (v or 0)
                seen = True
        if not seen:
            return "-"
        return _fmt_amount(_conv(total), divisor)

    if kt == "mtd":
        v = _conv(values.get(arg))
        return _fmt_amount(v, divisor)

    if kt == "ytd_asof":
        # Balance rows: use current_period value if available else last known
        if kind == "beginning_balance":
            first_p = all_periods[0] if all_periods else None
            v = _conv(values.get(first_p)) if first_p else None
            return _fmt_amount(v, divisor)
        if kind == "ending_balance":
            target = current_period or (all_periods[-1] if all_periods else None)
            v = _conv(values.get(target)) if target else None
            return _fmt_amount(v, divisor)
        year = (current_period or "")[:4]
        total = 0.0
        seen = False
        for p, v in values.items():
            if p.startswith(year):
                total += (v or 0)
                seen = True
        if not seen:
            return "-"
        return _fmt_amount(_conv(total), divisor)

    return "-"


def _build_table(lines, periods, all_periods, current_period, divisor, inr_rate=None):
    """Return reportlab Table + TableStyle."""
    cols, keys, year = _build_columns(periods, all_periods, current_period)
    header = list(cols)

    # Body rows
    body = []
    style_cmds = []

    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"],
                           fontName="Helvetica-Bold", fontSize=8,
                           textColor=colors.white, alignment=TA_LEFT)

    body.append(header)
    style_cmds.extend([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (1, 0), (-1, 0), "CENTER"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
    ])

    for i, ln in enumerate(lines, start=1):
        kind = ln.get("kind")
        indent = ln.get("indent", 0) or 0
        label = ln.get("label", "")

        # Skip blank rows (leave a small gap by adding thin empty row)
        if kind == "blank":
            body.append([""] * len(cols))
            style_cmds.append(("BOTTOMPADDING", (0, i), (-1, i), 2))
            style_cmds.append(("TOPPADDING", (0, i), (-1, i), 2))
            continue

        row = [("  " * indent) + label]
        for key in keys[1:]:
            row.append(_cell_value(ln, key, all_periods, current_period, divisor, inr_rate=inr_rate))
        body.append(row)

        rs = _row_style(kind, indent)
        if rs["bg"]:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), rs["bg"]))
        if rs.get("color"):
            style_cmds.append(("TEXTCOLOR", (0, i), (-1, i), rs["color"]))
        if rs["bold"]:
            style_cmds.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
        # Balance row: full border
        if kind in ("beginning_balance", "ending_balance"):
            style_cmds.append(("LINEABOVE", (0, i), (-1, i), 1.2, WARN_BORDER))
            style_cmds.append(("LINEBELOW", (0, i), (-1, i), 1.2, WARN_BORDER))
        # Alternating leaf row background
        if kind == "leaf" and indent >= 1 and not rs["bg"]:
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), ALT_ROW_BG))

    # Base column widths (landscape A4 = 297mm, minus 20mm margins = 257mm)
    n_periods = len(periods)
    total_w = 265 * mm
    label_w = 55 * mm
    fixed_w = 22 * mm  # each numeric col
    remaining = total_w - label_w
    n_cols = len(cols) - 1
    if n_cols * fixed_w > remaining:
        fixed_w = remaining / n_cols
    col_widths = [label_w] + [fixed_w] * n_cols

    style_cmds.extend([
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
    ])

    tbl = Table(body, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _page_header_footer(canvas, doc, title, subtitle, logo_path=None):
    canvas.saveState()
    W, H = landscape(A4)
    # Header band
    canvas.setFillColor(BRAND)
    canvas.rect(0, H - 14 * mm, W, 14 * mm, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.setFillColor(colors.white)
    canvas.drawString(15 * mm, H - 9 * mm, title)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(15 * mm, H - 12.5 * mm, subtitle)
    # Right side: date + page number
    canvas.setFont("Helvetica", 8)
    stamp = f"Printed: {datetime.now().strftime('%d %b %Y %H:%M')}"
    canvas.drawRightString(W - 15 * mm, H - 9 * mm, stamp)
    canvas.drawRightString(W - 15 * mm, H - 12.5 * mm, f"Page {doc.page}")
    # Logo if provided (top-left, small)
    if logo_path and Path(logo_path).exists():
        try:
            canvas.drawImage(str(logo_path), W - 42 * mm, H - 12.5 * mm,
                             width=24 * mm, height=8.5 * mm,
                             preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    # Footer
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica-Oblique", 7)
    canvas.drawString(15 * mm, 8 * mm,
                      "PT Prasad Seeds Indonesia  ·  Cash Flow Summary  ·  Confidential")
    canvas.restoreState()


def write_cf_summary_pdf(out_path, lines, periods, usd_rate, inr_rate,
                         current_period=None, as_of_label=None, logo_path=None):
    """Generate a ready-to-print PDF with CF Summary in IDR Million + INR Lakh.

    Args:
      out_path: destination .pdf path
      lines: cf_structure list (from build_cf_structure)
      periods: list of "YYYY-MM" completed periods to render
      usd_rate: IDR per USD (info only)
      inr_rate: IDR per INR (used to convert for INR section)
      current_period: current YYYY-MM for MTD/YTD-as-of columns (or None)
      as_of_label: e.g. "28 Sep 2026" — appears in subtitle
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=20 * mm, bottomMargin=14 * mm,
        title="PSI Cash Flow Summary",
        author="PT Prasad Seeds Indonesia",
    )

    story = []
    styles = getSampleStyleSheet()

    hdr_title = "Cash Flow Summary — Detailed Table"
    sub = f"PT Prasad Seeds Indonesia · As of {as_of_label or datetime.now().strftime('%d %b %Y')}"

    intro_style = ParagraphStyle(
        "intro", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=13, textColor=BRAND,
        alignment=TA_LEFT, spaceAfter=2)
    sub_style = ParagraphStyle(
        "sub", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8.5, textColor=MUTED,
        alignment=TA_LEFT, spaceAfter=8)

    # ===== Section 1: IDR (in Million) =====
    story.append(Paragraph(
        "Section 1 &nbsp;·&nbsp; In IDR (Million)", intro_style))
    story.append(Paragraph(
        f"All amounts in IDR Millions (1,000,000). Reference rates: "
        f"USD = Rp {usd_rate:,.0f} · INR = Rp {inr_rate:,.0f}",
        sub_style))
    story.append(_build_table(lines, periods, periods, current_period,
                              divisor=1_000_000, inr_rate=None))
    story.append(PageBreak())

    # ===== Section 2: INR (in Lakh) =====
    story.append(Paragraph(
        "Section 2 &nbsp;·&nbsp; In INR (Lakh)", intro_style))
    story.append(Paragraph(
        f"All amounts in INR Lakhs (100,000). "
        f"Converted at INR = Rp {inr_rate:,.0f}. Reference: USD = Rp {usd_rate:,.0f}",
        sub_style))
    # For INR: divisor = 100,000 (Lakh) but values must first be converted IDR->INR
    story.append(_build_table(lines, periods, periods, current_period,
                              divisor=100_000, inr_rate=inr_rate))

    def _on_page(canvas, doc):
        _page_header_footer(canvas, doc, hdr_title, sub, logo_path=logo_path)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return out_path
