"""Excel sheet writers for PSI Cash Flow Dashboard."""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import datetime

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from lib_pivot import INDONESIAN_MONTHS, MONTHS_FULL, month_label


HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
SECTION_FILL = PatternFill("solid", fgColor="D9E1F2")
SECTION_FONT = Font(bold=True, color="1F3864")
SUBTOTAL_FILL = PatternFill("solid", fgColor="F2F2F2")
SUBTOTAL_FONT = Font(bold=True)
COMPANY_FONT = Font(bold=True, size=14, color="1F3864")
TOTAL_FILL = PatternFill("solid", fgColor="FFE699")
TOTAL_FONT = Font(bold=True)


def _apply_style(cell, kind):
    if kind == "section_header":
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    elif kind == "subsection":
        cell.fill = SECTION_FILL
        cell.font = SECTION_FONT
    elif kind in ("subtotal_section", "section_total"):
        cell.fill = SUBTOTAL_FILL
        cell.font = SUBTOTAL_FONT


def _write_currency_row(ws, r, col, idr, usd_rate, inr_rate, fill, font):
    for j, val in enumerate((idr, idr / usd_rate if usd_rate else 0,
                             idr / inr_rate if inr_rate else 0)):
        cell = ws.cell(row=r, column=col + j, value=val if val else None)
        cell.number_format = '#,##0;(#,##0);"-"'
        cell.fill = fill
        cell.font = font


def write_cf_summary(wb, lines, periods, usd_rate, inr_rate, bb_agg):
    if "CF Summary" in wb.sheetnames:
        del wb["CF Summary"]
    ws = wb.create_sheet("CF Summary", 0)

    last_col = 2 + len(periods) * 3 + 3

    # Title
    ws.cell(row=1, column=2, value="PT Prasad Seeds Indonesia").font = COMPANY_FONT
    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=last_col)
    ws.cell(row=1, column=2).alignment = Alignment(horizontal="center")

    # Rate / timestamp row
    ws.cell(row=2, column=2,
            value=(f"USD = Rp {int(usd_rate):,}   |   INR = Rp {int(inr_rate)}"
                   f"   |   Updated: {datetime.now():%d %b %Y %H:%M}"))
    ws.merge_cells(start_row=2, start_column=2, end_row=2, end_column=last_col)
    ws.cell(row=2, column=2).font = Font(italic=True, color="666666")
    ws.cell(row=2, column=2).alignment = Alignment(horizontal="center")

    # Header row 3 - month labels
    ws.cell(row=3, column=2, value="Particular").fill = HEADER_FILL
    ws.cell(row=3, column=2).font = HEADER_FONT
    ws.cell(row=3, column=2).alignment = Alignment(horizontal="center", vertical="center")

    col = 3
    for period in periods:
        c = ws.cell(row=3, column=col, value=month_label(period))
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center")
        ws.merge_cells(start_row=3, start_column=col, end_row=3, end_column=col + 2)
        col += 3
    c = ws.cell(row=3, column=col, value=f"YTD {periods[-1].split('-')[0]}")
    c.fill = HEADER_FILL
    c.font = HEADER_FONT
    c.alignment = Alignment(horizontal="center")
    ws.merge_cells(start_row=3, start_column=col, end_row=3, end_column=col + 2)

    # Header row 4 - currency sublabels
    col = 3
    for _ in range(len(periods) + 1):
        for j, cur in enumerate(("IDR", "USD", "INR")):
            c = ws.cell(row=4, column=col + j, value=cur)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.alignment = Alignment(horizontal="center")
        col += 3

    # Data rows
    r = 5
    for line in lines:
        kind = line["kind"]
        if kind == "blank":
            r += 1
            continue
        indent = line.get("indent", 0)
        label_cell = ws.cell(row=r, column=2,
                             value=("    " * indent) + line["label"])
        _apply_style(label_cell, kind)

        ytd = {"IDR": 0.0, "USD": 0.0, "INR": 0.0}
        col = 3
        for period in periods:
            idr = line["values"].get(period, 0.0) or 0.0
            usd = idr / usd_rate if usd_rate else 0
            inr = idr / inr_rate if inr_rate else 0
            ytd["IDR"] += idr
            ytd["USD"] += usd
            ytd["INR"] += inr
            for j, val in enumerate((idr, usd, inr)):
                if line["values"]:
                    cell = ws.cell(row=r, column=col + j,
                                   value=val if val else None)
                    cell.number_format = '#,##0;(#,##0);"-"'
                    _apply_style(cell, kind)
            col += 3
        for j, cur in enumerate(("IDR", "USD", "INR")):
            if line["values"]:
                cell = ws.cell(row=r, column=col + j,
                               value=ytd[cur] if ytd[cur] else None)
                cell.number_format = '#,##0;(#,##0);"-"'
                _apply_style(cell, kind)
        r += 1

    # Reconciliation block
    r += 1
    bb_fill, bb_font = SUBTOTAL_FILL, SUBTOTAL_FONT
    ws.cell(row=r, column=2, value="BEGINNING").fill = bb_fill
    ws.cell(row=r, column=2).font = bb_font
    col = 3
    for period in periods:
        opening = sum(v for (b, p), v in bb_agg.items() if p == period)
        _write_currency_row(ws, r, col, opening, usd_rate, inr_rate, bb_fill, bb_font)
        col += 3
    first_opening = sum(v for (b, p), v in bb_agg.items() if p == periods[0])
    _write_currency_row(ws, r, col, first_opening, usd_rate, inr_rate, bb_fill, bb_font)
    r += 1

    incoming_sum = defaultdict(float)
    outflow_sum = defaultdict(float)
    for line in lines:
        if line["label"] == "TOTAL INCOMING":
            for p, v in line["values"].items():
                incoming_sum[p] += v
        if line["label"] == "TOTAL OUTFLOW":
            for p, v in line["values"].items():
                outflow_sum[p] += v

    ws.cell(row=r, column=2, value="ENDING").fill = bb_fill
    ws.cell(row=r, column=2).font = bb_font
    col = 3
    ytd_ending = 0.0
    for period in periods:
        opening = sum(v for (b, p), v in bb_agg.items() if p == period)
        net = incoming_sum.get(period, 0) + outflow_sum.get(period, 0)
        ending = opening + net
        ytd_ending = ending
        _write_currency_row(ws, r, col, ending, usd_rate, inr_rate, bb_fill, bb_font)
        col += 3
    _write_currency_row(ws, r, col, ytd_ending, usd_rate, inr_rate, bb_fill, bb_font)

    # Column widths
    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = 48
    for cidx in range(3, last_col + 1):
        ws.column_dimensions[get_column_letter(cidx)].width = 16
    ws.freeze_panes = "C5"


def write_bank_sheets(wb, rows, bb_agg, net_change_agg, periods,
                      usd_rate, inr_rate):
    bank_meta = {}
    for r in rows:
        if r["bank"] not in bank_meta:
            bank_meta[r["bank"]] = {"unit": r["unit"]}

    for period in periods:
        sheet_name = f"Bank - {INDONESIAN_MONTHS[int(period.split('-')[1])]}"
        if sheet_name in wb.sheetnames:
            del wb[sheet_name]
        ws = wb.create_sheet(sheet_name)

        ws["A1"] = "PT Prasad Seeds Indonesia"
        ws["A1"].font = Font(bold=True, size=14, color="1F3864")
        ws.merge_cells("A1:H1")
        ws["A1"].alignment = Alignment(horizontal="center")

        ws["A2"] = "Bank Position"
        ws["A2"].font = Font(bold=True, italic=True)
        ws.merge_cells("A2:H2")
        ws["A2"].alignment = Alignment(horizontal="center")

        y, m = period.split("-")
        last_day = monthrange(int(y), int(m))[1]
        ws["A3"] = f"As of: {MONTHS_FULL[int(m)]} {last_day}, {y}"
        ws["A3"].font = Font(italic=True, color="666666")
        ws.merge_cells("A3:H3")
        ws["A3"].alignment = Alignment(horizontal="center")

        headers = ["Bank", "Unit", "Currency", "Opening Balance", "Net Change",
                   "Ending Balance (IDR)", "Ending (USD)", "Ending (INR)"]
        for i, h in enumerate(headers, 1):
            c = ws.cell(row=5, column=i, value=h)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.alignment = Alignment(horizontal="center")

        r = 6
        total_idr = 0.0
        for bank in sorted(bank_meta.keys()):
            opening = bb_agg.get((bank, period), 0.0)
            net_change = net_change_agg.get((bank, period), 0.0)
            ending = opening + net_change
            if not (opening or net_change or ending):
                continue
            ws.cell(row=r, column=1, value=bank)
            ws.cell(row=r, column=2, value=bank_meta[bank]["unit"] or "-")
            cur = "USD-equiv (IDR)" if "USD" in bank else "IDR"
            ws.cell(row=r, column=3, value=cur)
            for col_idx, val in [(4, opening), (5, net_change), (6, ending)]:
                cell = ws.cell(row=r, column=col_idx, value=val)
                cell.number_format = '#,##0;(#,##0);"-"'
            ws.cell(row=r, column=7,
                    value=ending / usd_rate).number_format = '#,##0.00;(#,##0.00);"-"'
            ws.cell(row=r, column=8,
                    value=ending / inr_rate).number_format = '#,##0.00;(#,##0.00);"-"'
            total_idr += ending
            r += 1

        ws.cell(row=r, column=1, value="TOTAL")
        for col_idx in range(1, 9):
            ws.cell(row=r, column=col_idx).fill = TOTAL_FILL
            ws.cell(row=r, column=col_idx).font = TOTAL_FONT
        ws.cell(row=r, column=6,
                value=total_idr).number_format = '#,##0;(#,##0);"-"'
        ws.cell(row=r, column=7,
                value=total_idr / usd_rate).number_format = '#,##0.00;(#,##0.00);"-"'
        ws.cell(row=r, column=8,
                value=total_idr / inr_rate).number_format = '#,##0.00;(#,##0.00);"-"'

        for cidx, w in enumerate([18, 12, 18, 22, 22, 24, 16, 16], start=1):
            ws.column_dimensions[get_column_letter(cidx)].width = w
