"""Build dashboard data.json for the static HTML view."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from lib_pivot import month_label, month_long_label


def build_dashboard_data(rows, agg, bb_agg, net_change_agg, lines, periods,
                         usd_rate, inr_rate):
    # ---- CF Summary structured ----
    cf_summary = []
    for line in lines:
        if line["kind"] == "blank":
            cf_summary.append({"kind": "blank"})
            continue
        cf_summary.append({
            "label": line["label"],
            "kind": line["kind"],
            "indent": line.get("indent", 0),
            "values": {p: line["values"].get(p, 0.0) for p in periods},
        })

    # ---- Bank position ----
    bank_position = {}
    all_banks = sorted({b for (b, p) in bb_agg.keys()}
                       | {b for (b, p) in net_change_agg.keys()})
    for period in periods:
        rows_for_period = []
        total_idr = 0
        for bank in all_banks:
            opening = bb_agg.get((bank, period), 0.0)
            net_change = net_change_agg.get((bank, period), 0.0)
            ending = opening + net_change
            if not (opening or net_change or ending):
                continue
            rows_for_period.append({
                "bank": bank,
                "opening": opening,
                "net_change": net_change,
                "ending": ending,
            })
            total_idr += ending
        rows_for_period.sort(key=lambda x: -abs(x["ending"]))
        bank_position[period] = {
            "rows": rows_for_period,
            "total": total_idr,
        }

    # ---- Top expense by Sub-Category (per period and YTD) ----
    sub_totals = defaultdict(lambda: defaultdict(float))
    for (period, c, s, d), v in agg.items():
        if not c.startswith("Outflow"):
            continue
        if c in ("Outflow - Indirect Expense", "Outflow - Direct Expense",
                 "Outflow - Finance Cost"):
            label = s
        else:
            label = d or s or c.replace("Outflow - ", "")
        sub_totals[label][period] += abs(v)

    top_expenses_by_period = {}
    for period in periods:
        items = [(lbl, vals.get(period, 0.0))
                 for lbl, vals in sub_totals.items()]
        items = [(l, v) for l, v in items if v > 0]
        items.sort(key=lambda x: -x[1])
        top_expenses_by_period[period] = [
            {"label": l, "amount": v} for l, v in items[:10]
        ]

    ytd_items = [(lbl, sum(vals.values())) for lbl, vals in sub_totals.items()]
    ytd_items = [(l, v) for l, v in ytd_items if v > 0]
    ytd_items.sort(key=lambda x: -x[1])
    top_expenses_ytd = [{"label": l, "amount": v} for l, v in ytd_items[:15]]

    # ---- Top vendors / parties ----
    party_totals = defaultdict(float)
    for r in rows:
        if r["category"].startswith("Outflow") and r["parties"]:
            party_totals[r["parties"]] += abs(r["amount"])
    top_parties = sorted(party_totals.items(), key=lambda x: -x[1])[:15]
    top_parties_list = [{"label": p, "amount": a} for p, a in top_parties]

    # ---- Trend ----
    inflow = defaultdict(float)
    outflow = defaultdict(float)
    for (p, c, s, d), v in agg.items():
        if c == "Incoming":
            inflow[p] += v
        elif c.startswith("Outflow"):
            outflow[p] += v
    trend = {
        "periods": periods,
        "inflow": [inflow.get(p, 0.0) for p in periods],
        "outflow": [outflow.get(p, 0.0) for p in periods],
        "net": [inflow.get(p, 0.0) + outflow.get(p, 0.0) for p in periods],
        "ending": [
            sum(v for (b, pp), v in bb_agg.items() if pp == p)
            + inflow.get(p, 0.0) + outflow.get(p, 0.0)
            for p in periods
        ],
    }

    # ---- Recent largest transactions ----
    last_period = periods[-1]
    last_period_outflows = [r for r in rows
                            if r["period"] == last_period
                            and r["category"].startswith("Outflow")]
    last_period_outflows.sort(key=lambda r: r["amount"])
    recent_top = []
    for r in last_period_outflows[:15]:
        recent_top.append({
            "date": (r["date"].strftime("%Y-%m-%d")
                     if hasattr(r["date"], "strftime") else str(r["date"])),
            "bank": r["bank"],
            "unit": r["unit"],
            "category": r["sub_category"] or r["category"],
            "detail": r["detail_category"],
            "party": r["parties"],
            "amount": r["amount"],
        })

    # ---- Incoming drill-down (per period: groups -> parties) ----
    incoming_drill = _build_incoming_drill(rows, periods)

    # ---- Outflow drill-down (per period: buckets -> subgroups -> parties) ----
    outflow_drill = _build_outflow_drill(rows, periods)

    # ---- Bank position matrix (banks x months) ----
    bp_matrix = _build_bank_matrix(bb_agg, net_change_agg, periods)

    # ---- Daily view (running balances + daily in/out) ----
    daily = _build_daily_view(rows, periods)

    # ---- Period meta ----
    period_meta = []
    for p in periods:
        period_meta.append({
            "key": p,
            "label_short": month_label(p),
            "label_long": month_long_label(p),
        })

    return {
        "company": "PT Prasad Seeds Indonesia",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rates": {"usd": usd_rate, "inr": inr_rate},
        "periods": period_meta,
        "cf_summary": cf_summary,
        "bank_position": bank_position,
        "top_expenses_by_period": top_expenses_by_period,
        "top_expenses_ytd": top_expenses_ytd,
        "top_parties": top_parties_list,
        "trend": trend,
        "recent_top_outflows": recent_top,
        "incoming_drill": incoming_drill,
        "outflow_drill": outflow_drill,
        "bank_position_matrix": bp_matrix,
        "daily": daily,
    }


def _build_daily_view(rows, periods):
    """Build daily cash position + daily inflow/outflow data."""
    if not periods:
        return {"as_of": None, "dates": [], "bank_position": {},
                "totals": [], "inout": [], "current_position": {},
                "mtd": {}, "recent": []}

    first_period = periods[0]

    # 1. Opening balance per bank (sum of Beginning Balance entries
    #    for the FIRST period - represents Jan 1 balance)
    opening = defaultdict(float)
    for r in rows:
        if r["category"] == "Beginning Balance" and r["period"] == first_period:
            opening[r["bank"]] += r["amount"]

    # 2. Daily transactions per bank (excluding Beginning Balance entries)
    by_bank_date = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r["category"] == "Beginning Balance":
            continue
        if not r.get("date"):
            continue
        d = r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else str(r["date"])
        by_bank_date[r["bank"]][d] += r["amount"]

    all_dates = sorted({d for bd in by_bank_date.values() for d in bd.keys()})
    if not all_dates:
        return {"as_of": None, "dates": [], "bank_position": {},
                "totals": [], "inout": [], "current_position": {},
                "mtd": {}, "recent": []}
    as_of = all_dates[-1]

    all_banks = sorted(set(by_bank_date.keys()) | set(opening.keys()))

    # 3. Running balance per bank per date
    bank_position = {}
    for bank in all_banks:
        running = opening.get(bank, 0.0)
        per = {}
        for d in all_dates:
            running += by_bank_date[bank].get(d, 0.0)
            per[d] = running
        bank_position[bank] = per

    # 4. Total across all banks per date
    totals = []
    for d in all_dates:
        total = sum(bank_position[b].get(d, 0.0) for b in all_banks)
        totals.append({"date": d, "total": total})

    # 5. Current position (latest date) per bank
    current_position = {b: bank_position[b][as_of] for b in all_banks}
    current_total = sum(current_position.values())

    # 6. Daily inflow / outflow
    daily_inflow = defaultdict(float)
    daily_outflow = defaultdict(float)
    for r in rows:
        if r["category"] == "Beginning Balance" or not r.get("date"):
            continue
        d = r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else str(r["date"])
        if r["category"] == "Incoming":
            daily_inflow[d] += r["amount"]
        elif r["category"].startswith("Outflow"):
            daily_outflow[d] += r["amount"]
    inout = []
    for d in all_dates:
        inflow = daily_inflow.get(d, 0.0)
        outflow = daily_outflow.get(d, 0.0)
        inout.append({"date": d, "inflow": inflow, "outflow": outflow,
                      "net": inflow + outflow})

    # 7. Month-to-date for the current period (= period of as_of date)
    cur_period = as_of[:7]  # YYYY-MM
    mtd_inflow = sum(daily_inflow[d] for d in all_dates if d.startswith(cur_period))
    mtd_outflow = sum(daily_outflow[d] for d in all_dates if d.startswith(cur_period))
    mtd_opening = sum(
        bank_position[b].get(_prev_date(all_dates, cur_period + "-01"), 0.0)
        for b in all_banks
    )
    mtd = {
        "period": cur_period,
        "inflow": mtd_inflow,
        "outflow": mtd_outflow,
        "net": mtd_inflow + mtd_outflow,
        "opening": mtd_opening,
        "ending": current_total,
    }

    # 8. Recent transactions (last 20 by date desc)
    recent = []
    sorted_rows = [r for r in rows
                   if r["category"] != "Beginning Balance" and r.get("date")]
    sorted_rows.sort(key=lambda r: (r["date"], r["amount"]))
    sorted_rows.reverse()  # most recent first
    for r in sorted_rows[:30]:
        recent.append({
            "date": r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else str(r["date"]),
            "bank": r["bank"],
            "unit": r["unit"],
            "category": r["sub_category"] or r["category"],
            "detail": r["detail_category"],
            "party": r["parties"],
            "amount": r["amount"],
        })

    return {
        "as_of": as_of,
        "dates": all_dates,
        "banks": all_banks,
        "bank_position": bank_position,
        "totals": totals,
        "inout": inout,
        "current_position": current_position,
        "current_total": current_total,
        "mtd": mtd,
        "recent": recent,
    }


def _prev_date(all_dates, target):
    """Return the largest date in all_dates strictly less than `target`,
    or None if there is no earlier date."""
    prev = None
    for d in all_dates:
        if d < target:
            prev = d
        else:
            break
    return prev


# -----------------------------------------------------------------------------
# Drill-down helpers
# -----------------------------------------------------------------------------
INCOMING_LABELS_ID = {
    "Incoming - Customers": "Customer Receipts",
    "Incoming - Bank Loan": "Bank Loan Drawdown",
    "Incoming - Others": "Other Receipts",
}

OUTFLOW_BUCKETS_ID = {
    "Outflow - CAPEX": ("CAPEX (Capital Expenditure)", 1),
    "Outflow - Indirect Expense": ("OPEX - Indirect Expense", 2),
    "Outflow - Direct Expense": ("OPEX - Direct Expense (Production)", 3),
    "Outflow - Loan": ("Loans (Bank & Intercompany)", 4),
    "Outflow - Finance Cost": ("Bank Charges & Interest", 5),
    "Outflow - Imprest Fund": ("Imprest Fund / Petty Cash", 6),
    "Outflow - Cash Advance": ("Cash Advance", 7),
    "Outflow - Bank Guarantee": ("Bank Guarantee", 8),
}


def _build_incoming_drill(rows, periods):
    out = {}
    for period in periods:
        groups = {}
        for r in rows:
            if r["category"] != "Incoming" or r["period"] != period:
                continue
            det = r["detail_category"] or "Lainnya"
            label = INCOMING_LABELS_ID.get(det, det)
            if label not in groups:
                groups[label] = {"amount": 0.0,
                                 "parties": defaultdict(float)}
            groups[label]["amount"] += r["amount"]
            party = r["parties"] or "(tanpa nama)"
            groups[label]["parties"][party] += r["amount"]
        total = sum(g["amount"] for g in groups.values())
        grp_list = []
        for label, data in sorted(groups.items(),
                                  key=lambda x: -x[1]["amount"]):
            parties = sorted(data["parties"].items(),
                             key=lambda x: -x[1])
            grp_list.append({
                "label": label,
                "amount": data["amount"],
                "pct": (data["amount"] / total * 100) if total else 0,
                "parties": [{"label": p, "amount": a}
                            for p, a in parties[:25]],
                "party_count": len(parties),
            })
        out[period] = {"total": total, "groups": grp_list}
    return out


def _build_outflow_drill(rows, periods):
    out = {}
    for period in periods:
        buckets = {}
        for r in rows:
            if not r["category"].startswith("Outflow"):
                continue
            if r["period"] != period:
                continue
            blabel, _ = OUTFLOW_BUCKETS_ID.get(
                r["category"], (r["category"].replace("Outflow - ", ""), 99))
            # Choose level-2 subgroup
            cat = r["category"]
            if cat == "Outflow - Indirect Expense":
                sub = r["sub_category"] or "Lainnya"
            elif cat == "Outflow - Direct Expense":
                sub = (r["sub_category"]
                       if r["sub_category"] and r["sub_category"] != "Direct Expense"
                       else (r["detail_category"] or "Lainnya"))
            elif cat == "Outflow - Finance Cost":
                sub = (r["sub_category"]
                       if r["sub_category"] and r["sub_category"] != "Finance Cost"
                       else (r["detail_category"] or "Lainnya"))
            else:
                sub = r["detail_category"] or r["sub_category"] or "Lainnya"
            b = buckets.setdefault(blabel, {
                "amount": 0.0, "subs": {}})
            s = b["subs"].setdefault(sub, {
                "amount": 0.0, "parties": defaultdict(float)})
            b["amount"] += r["amount"]
            s["amount"] += r["amount"]
            party = r["parties"] or "(tanpa nama)"
            s["parties"][party] += r["amount"]
        total = sum(b["amount"] for b in buckets.values())
        bucket_list = []
        # Most-negative first
        for blabel, b in sorted(buckets.items(), key=lambda x: x[1]["amount"]):
            sub_list = []
            for slabel, s in sorted(b["subs"].items(),
                                    key=lambda x: x[1]["amount"]):
                parties = sorted(s["parties"].items(),
                                 key=lambda x: x[1])  # most negative first
                sub_list.append({
                    "label": slabel,
                    "amount": s["amount"],
                    "parties": [{"label": p, "amount": a}
                                for p, a in parties[:20]],
                    "party_count": len(parties),
                })
            bucket_list.append({
                "label": blabel,
                "amount": b["amount"],
                "pct": (abs(b["amount"]) / abs(total) * 100) if total else 0,
                "subgroups": sub_list,
            })
        out[period] = {"total": total, "buckets": bucket_list}
    return out


def _build_bank_matrix(bb_agg, net_change_agg, periods):
    all_banks = sorted({b for (b, p) in bb_agg.keys()}
                       | {b for (b, p) in net_change_agg.keys()})
    data = {}
    for bank in all_banks:
        row = {}
        for p in periods:
            opening = bb_agg.get((bank, p), 0.0)
            change = net_change_agg.get((bank, p), 0.0)
            row[p] = {
                "opening": opening,
                "change": change,
                "ending": opening + change,
            }
        data[bank] = row
    totals = {p: sum(data[b][p]["ending"] for b in all_banks)
              for p in periods}
    return {"banks": all_banks, "periods": periods,
            "data": data, "totals": totals}
