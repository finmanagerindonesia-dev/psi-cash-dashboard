"""Ready-to-print "printed dashboard" PDF.

Page 1  : Executive summary — Cash Position, Total Inflow, Total Outflow,
          Net, Where did the money come from, Where did the money go
Page 2+ : CF Summary Detailed Table — in IDR (full amount)
Page N+ : CF Summary Detailed Table — in INR (full amount, converted from IDR)

Light version: no charts embedded, only tables + text + logo.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from collections import defaultdict

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


# Palette (matches dashboard clean SaaS look)
BRAND = colors.HexColor("#1E40AF")
BRAND_LIGHT = colors.HexColor("#EFF6FF")
TEXT = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
POS = colors.HexColor("#059669")
POS_BG = colors.HexColor("#ECFDF5")
NEG = colors.HexColor("#DC2626")
NEG_BG = colors.HexColor("#FEF2F2")
WARN_BG = colors.HexColor("#FEF3C7")
WARN_BORDER = colors.HexColor("#F59E0B")
SECTION_BG = colors.HexColor("#1E40AF")
SECTION_TEXT = colors.white
SUBSECTION_BG = colors.HexColor("#DBEAFE")
SUBTOTAL_BG = colors.HexColor("#EFF6FF")
ALT_ROW_BG = colors.HexColor("#FAFBFD")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _fmt_full(v, cur="IDR"):
    """Full amount with thousand separators. Negative -> parentheses. 0 -> '-'."""
    if v is None:
        return ""
    x = float(v)
    if abs(x) < 0.5:
        return "-"
    s = f"{abs(x):,.0f}"
    return f"({s})" if x < 0 else s


def _fmt_full_signed(v):
    if v is None:
        return "-"
    x = float(v)
    if abs(x) < 0.5:
        return "-"
    sign = "-" if x < 0 else ""
    return f"{sign}{abs(x):,.0f}"


def _short(s, n=44):
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + "…"


# ---------------------------------------------------------------------------
# Data crunching for executive summary
# ---------------------------------------------------------------------------
def _incoming_breakdown(rows, period_start, period_end):
    """Aggregate inflow by top-level category (Customer Receipts, Bank Loan
    Drawdown, Other Receipts) within [period_start, period_end] inclusive.

    Returns list of {label, amount, pct, top_parties[]}.
    """
    LABELS_MAP = {
        "Incoming - Customers": "Customer Receipts",
        "Incoming - Bank Loan": "Bank Loan Drawdown",
        "Incoming - Others":    "Other Receipts",
    }
    groups = defaultdict(lambda: {"amount": 0.0, "parties": defaultdict(float)})
    for r in rows:
        if r.get("category") != "Incoming":
            continue
        p = r.get("period")
        if not p or p < period_start or p > period_end:
            continue
        det = r.get("detail_category") or ""
        lbl = LABELS_MAP.get(det, det or "Other Receipts")
        amt = float(r.get("amount") or 0)
        groups[lbl]["amount"] += amt
        party = (r.get("parties") or "").strip() or "(Unnamed)"
        groups[lbl]["parties"][party] += amt

    total = sum(g["amount"] for g in groups.values())
    out = []
    for lbl, data in sorted(groups.items(), key=lambda x: -abs(x[1]["amount"])):
        top_parties = sorted(data["parties"].items(),
                             key=lambda x: -abs(x[1]))[:5]
        out.append({
            "label": lbl,
            "amount": data["amount"],
            "pct": (data["amount"] / total * 100) if total else 0.0,
            "top_parties": [{"label": n, "amount": a} for n, a in top_parties],
        })
    return out, total


def _outflow_breakdown(rows, period_start, period_end):
    """Aggregate outflow by bucket + sub-category (like the dashboard's
    'Where did the money go?' card)."""
    OUTFLOW_MAP = {
        "Outflow - CAPEX": "CAPEX (Capital Expenditure)",
        "Outflow - Indirect Expense": "OPEX - Indirect Expense",
        "Outflow - Direct Expense":   "OPEX - Direct Expense (Production)",
        "Outflow - Bank Loan":        "Bank Loan Repayment",
        "Outflow - Intercompany Loan": "Intercompany Loan Repayment",
        "Outflow - Intercompany Loan Repayment": "Intercompany Loan Repayment",
        "Outflow - Intercompany Loan Receivable": "Intercompany Loan Receivable",
        "Outflow - Finance Cost":     "Bank Charges & Interest",
        "Outflow - Imprest Fund":     "Imprest Fund / Petty Cash",
        "Outflow - Cash Advance":     "Cash Advance",
    }

    def _bucket(cat):
        if cat in OUTFLOW_MAP:
            return OUTFLOW_MAP[cat]
        if not cat or not cat.startswith("Outflow"):
            return cat or "Other"
        cl = cat.lower()
        if "loan" in cl and ("receivable" in cl or "given" in cl):
            return "Intercompany Loan Receivable"
        if "loan" in cl and ("bank" in cl or "term" in cl):
            return "Bank Loan Repayment"
        if "loan" in cl and ("intercompany" in cl or "antar" in cl):
            return "Intercompany Loan Repayment"
        return cat.replace("Outflow - ", "")

    buckets = defaultdict(lambda: {"amount": 0.0, "subs": defaultdict(float)})
    for r in rows:
        cat = r.get("category") or ""
        if not cat.startswith("Outflow"):
            continue
        p = r.get("period")
        if not p or p < period_start or p > period_end:
            continue
        amt = float(r.get("amount") or 0)
        b = _bucket(cat)
        if cat == "Outflow - Indirect Expense":
            sub = (r.get("sub_category") or "").strip() or "Other"
        elif cat == "Outflow - Direct Expense":
            sc = (r.get("sub_category") or "").strip()
            sub = sc if sc and sc != "Direct Expense" else ((r.get("detail_category") or "").strip() or "Other")
        elif cat == "Outflow - Finance Cost":
            sc = (r.get("sub_category") or "").strip()
            sub = sc if sc and sc != "Finance Cost" else ((r.get("detail_category") or "").strip() or "Other")
        else:
            sub = ((r.get("detail_category") or "").strip()
                   or (r.get("sub_category") or "").strip() or "Other")
        buckets[b]["amount"] += amt
        buckets[b]["subs"][sub] += amt

    total = sum(b["amount"] for b in buckets.values())
    out = []
    for lbl, data in sorted(buckets.items(), key=lambda x: x[1]["amount"]):
        top_subs = sorted(data["subs"].items(), key=lambda x: x[1])[:5]
        out.append({
            "label": lbl,
            "amount": data["amount"],
            "pct": (abs(data["amount"]) / abs(total) * 100) if total else 0.0,
            "top_subs": [{"label": n, "amount": a} for n, a in top_subs],
        })
    return out, total


def _cash_position(bb_agg, rows, upto_period):
    """Total ending cash across all banks at end of upto_period."""
    # Sum of BB (all periods up to and including upto) + all txns up to upto
    total = 0.0
    for (b, p), v in bb_agg.items():
        if p <= upto_period:
            total += v
    for r in rows:
        p = r.get("period")
        if not p or p > upto_period:
            continue
        cat = r.get("category")
        if cat and cat.startswith(("Incoming", "Outflow")):
            total += float(r.get("amount") or 0)
    return total


# ---------------------------------------------------------------------------
# CF Summary table (full amounts, no divisor)
# ---------------------------------------------------------------------------
def _build_columns(periods, current_period):
    """Cols: Particular | month1..N | YTD year | MTD as-of | YTD as-of."""
    year = periods[0][:4] if periods else datetime.now().strftime("%Y")
    cols = ["Particular"]
    keys = [None]
    for p in periods:
        cols.append(month_label(p))
        keys.append(("month", p))
    cols.append(f"YTD {year}")
    keys.append(("ytd", year))
    if current_period:
        cols.append("MTD")
        keys.append(("mtd", current_period))
    cols.append("YTD as of")
    keys.append(("ytd_asof", None))
    return cols, keys


def _cell_value(line, key, all_periods, current_period, inr_rate=None):
    values = line.get("values") or {}
    kind = line.get("kind")

    def _conv(v):
        if v is None:
            return None
        return v / inr_rate if inr_rate else v

    if key is None:
        return None
    kt, arg = key

    if kt == "month":
        return _fmt_full(_conv(values.get(arg)))

    if kt == "ytd":
        if kind == "beginning_balance":
            first_p = all_periods[0] if all_periods else None
            return _fmt_full(_conv(values.get(first_p)) if first_p else None)
        if kind == "ending_balance":
            last_p = all_periods[-1] if all_periods else None
            return _fmt_full(_conv(values.get(last_p)) if last_p else None)
        year = arg
        total = 0.0
        seen = False
        for p, v in values.items():
            if p.startswith(year):
                total += (v or 0)
                seen = True
        return _fmt_full(_conv(total)) if seen else "-"

    if kt == "mtd":
        return _fmt_full(_conv(values.get(arg)))

    if kt == "ytd_asof":
        if kind == "beginning_balance":
            first_p = all_periods[0] if all_periods else None
            return _fmt_full(_conv(values.get(first_p)) if first_p else None)
        if kind == "ending_balance":
            target = current_period or (all_periods[-1] if all_periods else None)
            return _fmt_full(_conv(values.get(target)) if target else None)
        year = (current_period or (all_periods[-1] if all_periods else ""))[:4]
        total = 0.0
        seen = False
        for p, v in values.items():
            if p.startswith(year):
                total += (v or 0)
                seen = True
        return _fmt_full(_conv(total)) if seen else "-"

    return "-"


def _row_style(kind):
    if kind in ("beginning_balance", "ending_balance"):
        return {"bg": WARN_BG, "bold": True, "border": WARN_BORDER, "color": TEXT}
    if kind == "section_header":
        return {"bg": SECTION_BG, "bold": True, "color": SECTION_TEXT}
    if kind == "subsection":
        return {"bg": SUBSECTION_BG, "bold": True, "color": TEXT}
    if kind in ("subtotal_section", "subtotal", "net"):
        return {"bg": SUBTOTAL_BG, "bold": True, "color": TEXT}
    return {"bg": None, "bold": False, "color": TEXT}


def _build_cf_table(lines, periods, current_period, inr_rate=None):
    """Build the detailed CF Summary reportlab Table."""
    cols, keys = _build_columns(periods, current_period)
    header = list(cols)
    body = [header]
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("ALIGN", (1, 0), (-1, 0), "CENTER"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
    ]

    for i, ln in enumerate(lines, start=1):
        kind = ln.get("kind")
        indent = ln.get("indent", 0) or 0
        label = ln.get("label", "")
        if kind == "blank":
            body.append([""] * len(cols))
            style_cmds.append(("BOTTOMPADDING", (0, i), (-1, i), 1))
            style_cmds.append(("TOPPADDING", (0, i), (-1, i), 1))
            continue

        row = [("   " * indent) + _short(label, 46)]
        for k in keys[1:]:
            row.append(_cell_value(ln, k, periods, current_period, inr_rate=inr_rate))
        body.append(row)

        rs = _row_style(kind)
        if rs["bg"]:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), rs["bg"]))
        if rs.get("color"):
            style_cmds.append(("TEXTCOLOR", (0, i), (-1, i), rs["color"]))
        if rs["bold"]:
            style_cmds.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
        if kind in ("beginning_balance", "ending_balance"):
            style_cmds.append(("LINEABOVE", (0, i), (-1, i), 1.0, WARN_BORDER))
            style_cmds.append(("LINEBELOW", (0, i), (-1, i), 1.0, WARN_BORDER))
        if kind == "leaf" and indent >= 1 and not rs["bg"] and i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), ALT_ROW_BG))

    # Column widths for landscape A4 (297 - 30 margins = 267mm)
    total_w = 267 * mm
    label_w = 60 * mm
    remaining = total_w - label_w
    n_num_cols = len(cols) - 1
    num_w = remaining / max(1, n_num_cols)
    col_widths = [label_w] + [num_w] * n_num_cols

    style_cmds.extend([
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 6.5),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
        ("GRID", (0, 0), (-1, -1), 0.2, LINE),
    ])

    tbl = Table(body, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


# ---------------------------------------------------------------------------
# Executive summary components
# ---------------------------------------------------------------------------
def _kpi_row(cash_pos, total_in, total_out, net, cur_label, cur_symbol, subtitle):
    """4 KPI cards side-by-side. cur_label = 'IDR' or 'INR'."""
    def _kpi(title, value, tone):
        v_color = TEXT
        if tone == "pos": v_color = POS
        elif tone == "neg": v_color = NEG
        return [
            Paragraph(f'<font color="#64748B" size="7"><b>{title}</b></font>',
                      ParagraphStyle("t", fontSize=7)),
            Paragraph(f'<font color="{v_color.hexval()}" size="14"><b>{cur_symbol} {_fmt_full_signed(value)}</b></font>',
                      ParagraphStyle("v", fontSize=14)),
        ]

    net_tone = "pos" if net >= 0 else "neg"
    data = [
        [_kpi(f"Cash Position — as of {subtitle}", cash_pos, "pos"),
         _kpi("Total Inflow (period)", total_in, "pos"),
         _kpi("Total Outflow (period)", total_out, "neg"),
         _kpi("Net Cash Change", net, net_tone)]
    ]
    tbl = Table(data, colWidths=[66 * mm] * 4)
    tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#ECFDF5")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#ECFDF5")),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FEF2F2")),
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#EFF6FF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return tbl


def _breakdown_card(title, items, is_inflow, cur_symbol, max_items=4, max_subs=3):
    """Card showing top categories with amount, %, and top parties."""
    tone_color = POS.hexval() if is_inflow else NEG.hexval()
    bg = colors.HexColor("#ECFDF5") if is_inflow else colors.HexColor("#FEF2F2")

    data = []
    # Header
    data.append([
        Paragraph(f'<font color="{BRAND.hexval()}" size="10"><b>{title}</b></font>',
                  ParagraphStyle("h", fontSize=10)),
        "",
    ])

    running_items = items[:max_items]
    others_sum = sum(x["amount"] for x in items[max_items:])
    others_count = len(items) - max_items

    for it in running_items:
        cat_lbl = _short(it["label"], 42)
        amt = _fmt_full(it["amount"])
        pct = f"{it.get('pct', 0):.1f}%"
        data.append([
            Paragraph(f'<b>{cat_lbl}</b>  <font color="#64748B" size="7">({pct})</font>',
                      ParagraphStyle("l", fontSize=8)),
            Paragraph(f'<font color="{tone_color}"><b>{cur_symbol} {amt}</b></font>',
                      ParagraphStyle("a", fontSize=8, alignment=TA_RIGHT)),
        ])
        # sub items (parties or subs)
        subs = it.get("top_parties") or it.get("top_subs") or []
        for s in subs[:max_subs]:
            data.append([
                Paragraph(f'<font size="7" color="#64748B">&nbsp;&nbsp;&nbsp;• {_short(s["label"], 40)}</font>',
                          ParagraphStyle("s", fontSize=7)),
                Paragraph(f'<font size="7" color="#64748B">{cur_symbol} {_fmt_full(s["amount"])}</font>',
                          ParagraphStyle("s2", fontSize=7, alignment=TA_RIGHT)),
            ])

    if others_count > 0:
        data.append([
            Paragraph(f'<font size="7.5"><i>Other {others_count} category/ies</i></font>',
                      ParagraphStyle("o", fontSize=7.5)),
            Paragraph(f'<font color="{tone_color}"><b>{cur_symbol} {_fmt_full(others_sum)}</b></font>',
                      ParagraphStyle("oa", fontSize=7.5, alignment=TA_RIGHT)),
        ])

    total = sum(x["amount"] for x in items)
    data.append([
        Paragraph(f'<b><font color="{BRAND.hexval()}">TOTAL</font></b>',
                  ParagraphStyle("tt", fontSize=9)),
        Paragraph(f'<font color="{tone_color}"><b>{cur_symbol} {_fmt_full(total)}</b></font>',
                  ParagraphStyle("tv", fontSize=9, alignment=TA_RIGHT)),
    ])

    col_w = [92 * mm, 44 * mm]
    tbl = Table(data, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), bg),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, BRAND),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return tbl


# ---------------------------------------------------------------------------
# Page header / footer
# ---------------------------------------------------------------------------
def _page_hdr_ftr(canvas, doc, title, subtitle, logo_path=None):
    """Plain simple footer only — no header banner, no logo."""
    canvas.saveState()
    W, H = landscape(A4)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(15 * mm, 8 * mm,
                      "PT Prasad Seeds Indonesia · Cash Flow Dashboard · Confidential")
    canvas.drawRightString(W - 15 * mm, 8 * mm,
                           f"Page {doc.page}  ·  Printed {datetime.now().strftime('%d %b %Y')}")
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def write_dashboard_pdf(
    out_path, lines, rows, bb_agg, periods, usd_rate, inr_rate,
    current_period=None, as_of_label=None, logo_path=None,
):
    """Write the printed-dashboard PDF.

    lines           : cf_structure for completed periods
    rows            : raw transactions (for exec-summary aggregations)
    bb_agg          : {(bank, period): amount} beginning balance
    periods         : list of completed periods (e.g. ['2026-01', ..., '2026-08'])
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not periods:
        raise ValueError("write_dashboard_pdf: at least one completed period required")

    period_start = periods[0]
    period_end   = periods[-1]

    # Aggregate for exec summary
    inflow_items, total_in = _incoming_breakdown(rows, period_start, period_end)
    outflow_items, total_out_neg = _outflow_breakdown(rows, period_start, period_end)
    total_out = total_out_neg  # negative sum
    net = total_in + total_out  # outflow already negative
    cash_pos = _cash_position(bb_agg, rows, period_end)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=12 * mm, bottomMargin=13 * mm,
        title="PSI Cash Flow Dashboard (Printed)",
        author="PT Prasad Seeds Indonesia",
    )

    period_txt = f"{month_long_label(period_start)} – {month_long_label(period_end)}"
    hdr_title = "PSI Cash Flow Dashboard"
    hdr_sub = f"{period_txt}  ·  As of {as_of_label or datetime.now().strftime('%d %b %Y')}"

    styles = getSampleStyleSheet()
    h_title = ParagraphStyle("h_title", parent=styles["Normal"],
                             fontName="Helvetica-Bold", fontSize=14,
                             textColor=BRAND, spaceAfter=2, alignment=TA_LEFT)
    h_sub = ParagraphStyle("h_sub", parent=styles["Normal"],
                           fontName="Helvetica", fontSize=8.5,
                           textColor=MUTED, spaceAfter=8, alignment=TA_LEFT)
    h_section = ParagraphStyle("h_section", parent=styles["Normal"],
                               fontName="Helvetica-Bold", fontSize=11,
                               textColor=BRAND, spaceBefore=8, spaceAfter=4,
                               alignment=TA_LEFT)

    story = []

    # =====================================================================
    # PAGE 1 — Executive Summary (IDR full amount)
    # =====================================================================
    story.append(Paragraph("Executive Summary", h_title))
    story.append(Paragraph(
        f"Period: <b>{period_txt}</b>  ·  As of <b>{as_of_label}</b>  ·  All amounts in IDR (full amount)  ·  "
        f"Reference: USD = Rp {usd_rate:,.0f}  ·  INR = Rp {inr_rate:,.0f}",
        h_sub))
    story.append(_kpi_row(cash_pos, total_in, total_out, net,
                          "IDR", "Rp", as_of_label))
    story.append(Spacer(1, 8))

    # Two-column: inflow + outflow breakdown
    inflow_card = _breakdown_card(
        "Where Did the Money Come From?", inflow_items, True, "Rp")
    outflow_card = _breakdown_card(
        "Where Did the Money Go?", outflow_items, False, "Rp")
    combo = Table([[inflow_card, outflow_card]],
                  colWidths=[137 * mm, 137 * mm])
    combo.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(combo)
    story.append(PageBreak())

    # =====================================================================
    # PAGE 2 — Executive Summary (INR full amount)
    # =====================================================================
    story.append(Paragraph("Executive Summary — INR View", h_title))
    story.append(Paragraph(
        f"Period: <b>{period_txt}</b>  ·  As of <b>{as_of_label}</b>  ·  All amounts in INR (full amount)  ·  "
        f"Converted at INR = Rp {inr_rate:,.0f}",
        h_sub))
    story.append(_kpi_row(cash_pos / inr_rate, total_in / inr_rate,
                          total_out / inr_rate, net / inr_rate,
                          "INR", "Rs", as_of_label))
    story.append(Spacer(1, 8))

    inflow_items_inr = [
        {**it, "amount": it["amount"] / inr_rate,
         "top_parties": [{"label": p["label"], "amount": p["amount"] / inr_rate}
                         for p in it.get("top_parties", [])]}
        for it in inflow_items
    ]
    outflow_items_inr = [
        {**it, "amount": it["amount"] / inr_rate,
         "top_subs": [{"label": s["label"], "amount": s["amount"] / inr_rate}
                      for s in it.get("top_subs", [])]}
        for it in outflow_items
    ]
    combo_inr = Table([[
        _breakdown_card("Where Did the Money Come From?", inflow_items_inr, True, "Rs"),
        _breakdown_card("Where Did the Money Go?", outflow_items_inr, False, "Rs"),
    ]], colWidths=[137 * mm, 137 * mm])
    combo_inr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(combo_inr)
    story.append(PageBreak())

    # =====================================================================
    # PAGE 3+ — Cash Flow Summary Detailed Table (IDR — full amount)
    # =====================================================================
    story.append(Paragraph("Cash Flow Summary — Detailed Table (IDR, full amount)", h_title))
    story.append(Paragraph(
        f"Period: <b>{period_txt}</b>  ·  All amounts in IDR (full amount)",
        h_sub))
    story.append(_build_cf_table(lines, periods, current_period, inr_rate=None))
    story.append(PageBreak())

    # =====================================================================
    # PAGE N+ — Cash Flow Summary Detailed Table (INR — full amount)
    # =====================================================================
    story.append(Paragraph("Cash Flow Summary — Detailed Table (INR, full amount)", h_title))
    story.append(Paragraph(
        f"Period: <b>{period_txt}</b>  ·  All amounts in INR (full amount)  ·  "
        f"Converted at INR = Rp {inr_rate:,.0f}",
        h_sub))
    story.append(_build_cf_table(lines, periods, current_period, inr_rate=inr_rate))

    def _on_page(canvas, doc):
        _page_hdr_ftr(canvas, doc, hdr_title, hdr_sub, logo_path=logo_path)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return out_path


# Back-compat: keep old function name aliased to new one
def write_cf_summary_pdf(out_path, lines, periods, usd_rate, inr_rate,
                         current_period=None, as_of_label=None, logo_path=None,
                         rows=None, bb_agg=None):
    """Deprecated alias — use write_dashboard_pdf."""
    if rows is None or bb_agg is None:
        # Minimal fallback: just build table without exec summary
        raise ValueError("Provide rows + bb_agg for dashboard PDF")
    return write_dashboard_pdf(
        out_path, lines, rows, bb_agg, periods, usd_rate, inr_rate,
        current_period=current_period, as_of_label=as_of_label, logo_path=logo_path,
    )
