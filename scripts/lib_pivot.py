"""Pivot / aggregation logic for PSI Cash Flow Dashboard."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

DEFAULT_USD_RATE = 17000.0
DEFAULT_INR_RATE = 189.0

INDONESIAN_MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}
MONTHS_FULL = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}


def _norm(s):
    if s is None:
        return ""
    return str(s).strip()


def parse_period(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return f"{value.year:04d}-{value.month:02d}"
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m"):
        try:
            d = datetime.strptime(s, fmt)
            return f"{d.year:04d}-{d.month:02d}"
        except ValueError:
            continue
    return None


def month_label(period_key: str) -> str:
    y, m = period_key.split("-")
    return f"{INDONESIAN_MONTHS[int(m)]} {y[2:]}"


def month_long_label(period_key: str) -> str:
    y, m = period_key.split("-")
    return f"{MONTHS_FULL[int(m)]} {y}"


def read_all_banks(wb):
    """Read transactions from "All Banks" sheet.

    Column layout (1-indexed):
      A=Unit  B=Bank  C=Date  D=Period  E=Category  F=Sub-Category
      G=Detail-Category  H=Parties  I=Details  J=Vch Type  K=Vch No.
      L=IDR (always filled, IDR equivalent at actual daily rate)
      M=USD (only for USD banks, native USD amount; can be empty)
    """
    ws = wb["All Banks"]
    rows = []
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row, values_only=True):
        unit = _norm(row[0])
        bank = _norm(row[1])
        if not bank:
            continue
        amt = row[11]
        if amt is None:
            continue
        usd_amt = row[12] if len(row) > 12 else None
        try:
            usd_amt = float(usd_amt) if usd_amt is not None and usd_amt != "" else None
        except (TypeError, ValueError):
            usd_amt = None
        is_usd_bank = "USD" in bank.upper()
        rows.append({
            "unit": unit,
            "bank": bank,
            "bank_currency": "USD" if is_usd_bank else "IDR",
            "date": row[2],
            "period": parse_period(row[3]),
            "category": _norm(row[4]),
            "sub_category": _norm(row[5]),
            "detail_category": _norm(row[6]),
            "parties": _norm(row[7]),
            "details": _norm(row[8]),
            "vch_type": _norm(row[9]),
            "vch_no": _norm(row[10]),
            "amount": float(amt),
            "amount_usd": usd_amt,
        })
    return rows


def detect_currency_rates(wb):
    try:
        ws = wb["CF Summary"]
        row2 = [c.value for c in ws[2]]
        nums = [v for v in row2 if isinstance(v, (int, float))]
        if len(nums) >= 2:
            usd, inr = nums[0], nums[1]
            if 5_000 <= usd <= 50_000 and 50 <= inr <= 500:
                return float(usd), float(inr)
    except Exception:
        pass
    return DEFAULT_USD_RATE, DEFAULT_INR_RATE


def all_periods(rows):
    return sorted({r["period"] for r in rows if r["period"]})


def aggregate_by_path(rows):
    agg = defaultdict(float)
    for r in rows:
        if not r["period"]:
            continue
        key = (r["period"], r["category"], r["sub_category"], r["detail_category"])
        agg[key] += r["amount"]
    return agg


def aggregate_beginning_balance(rows):
    agg = defaultdict(float)
    for r in rows:
        if r["category"] == "Beginning Balance" and r["period"]:
            agg[(r["bank"], r["period"])] += r["amount"]
    return agg


def aggregate_net_change_per_bank(rows):
    agg = defaultdict(float)
    for r in rows:
        if r["category"] == "Beginning Balance":
            continue
        if r["period"]:
            agg[(r["bank"], r["period"])] += r["amount"]
    return agg


def aggregate_beginning_balance_usd(rows):
    """Native USD opening per (bank, period) - only for USD banks with data."""
    agg = defaultdict(float)
    for r in rows:
        if r["category"] != "Beginning Balance":
            continue
        if not r.get("period"):
            continue
        if r.get("bank_currency") != "USD":
            continue
        if r.get("amount_usd") is None:
            continue
        agg[(r["bank"], r["period"])] += r["amount_usd"]
    return agg


def aggregate_net_change_per_bank_usd(rows):
    """Native USD net change per (bank, period) - only for USD banks with data."""
    agg = defaultdict(float)
    for r in rows:
        if r["category"] == "Beginning Balance":
            continue
        if not r.get("period"):
            continue
        if r.get("bank_currency") != "USD":
            continue
        if r.get("amount_usd") is None:
            continue
        agg[(r["bank"], r["period"])] += r["amount_usd"]
    return agg


def has_any_usd_native_data(rows):
    for r in rows:
        if r.get("bank_currency") == "USD" and r.get("amount_usd") is not None:
            return True
    return False


def build_cf_structure(agg, periods):
    def pull(cat=None, sub=None, det=None):
        out = defaultdict(float)
        for (period, c, s, d), v in agg.items():
            if cat is not None and c != cat:
                continue
            if sub is not None and s != sub:
                continue
            if det is not None and d != det:
                continue
            out[period] += v
        return dict(out)

    def pull_excluding(cat, sub, exclude_dets):
        out = defaultdict(float)
        for (period, c, s, d), v in agg.items():
            if c != cat or s != sub:
                continue
            if d in exclude_dets:
                continue
            out[period] += v
        return dict(out)

    lines = []

    def add(label, kind, values=None, indent=0):
        lines.append({"label": label, "kind": kind, "indent": indent,
                      "values": values or {}})

    add("INCOMING", "section_header")
    incoming_dets = ["Incoming - Customers", "Incoming - Bank Loan", "Incoming - Others"]
    for det in incoming_dets:
        add(det, "leaf", pull(cat="Incoming", det=det), indent=1)
    extra = sorted({d for (p, c, s, d), v in agg.items()
                    if c == "Incoming" and d not in incoming_dets})
    for det in extra:
        add(det, "leaf", pull(cat="Incoming", det=det), indent=1)
    add("TOTAL INCOMING", "subtotal_section", pull(cat="Incoming"))
    add("", "blank")

    add("OUTFLOW", "section_header")

    add("CAPEX", "subsection", indent=1)
    capex_dets = sorted({d for (p, c, s, d), v in agg.items()
                         if c == "Outflow - CAPEX" and d})
    for det in capex_dets:
        add(det, "leaf", pull(cat="Outflow - CAPEX", det=det), indent=2)
    add("TOTAL CAPEX", "subtotal_section", pull(cat="Outflow - CAPEX"), indent=1)
    add("", "blank")

    bank_term_loans = {"Citibank Term Loan", "DBS Term Loan"}
    intercompany_dets = sorted({d for (p, c, s, d), v in agg.items()
                                if c == "Outflow - Loan"
                                and d not in bank_term_loans and d})
    if intercompany_dets:
        add("INTERCOMPANY LOAN", "subsection", indent=1)
        for det in intercompany_dets:
            add(det, "leaf", pull(cat="Outflow - Loan", det=det), indent=2)
        add("TOTAL INTERCOMPANY LOAN", "subtotal_section",
            pull_excluding("Outflow - Loan", "Loan", bank_term_loans), indent=1)
        add("", "blank")

    bank_loans_present = sorted({d for (p, c, s, d), v in agg.items()
                                 if c == "Outflow - Loan" and d in bank_term_loans})
    if bank_loans_present:
        add("BANK LOAN REPAYMENT", "subsection", indent=1)
        for det in bank_loans_present:
            add(det, "leaf", pull(cat="Outflow - Loan", det=det), indent=2)
        bl_total = defaultdict(float)
        for det in bank_loans_present:
            for p, v in pull(cat="Outflow - Loan", det=det).items():
                bl_total[p] += v
        add("TOTAL BANK LOAN REPAYMENT", "subtotal_section",
            dict(bl_total), indent=1)
        add("", "blank")

    add("OPEX - DIRECT EXPENSE", "subsection", indent=1)
    direct_leaves = {}
    for (p, c, s, d), v in agg.items():
        if c != "Outflow - Direct Expense":
            continue
        leaf = s if s and s != "Direct Expense" else (d or "Other Direct Cost")
        direct_leaves.setdefault(leaf, defaultdict(float))[p] += v
    for leaf in sorted(direct_leaves.keys()):
        add(leaf, "leaf", dict(direct_leaves[leaf]), indent=2)
    add("TOTAL OPEX - DIRECT EXPENSE", "subtotal_section",
        pull(cat="Outflow - Direct Expense"), indent=1)
    add("", "blank")

    add("OPEX - INDIRECT EXPENSE", "subsection", indent=1)
    indirect_subs = sorted({s for (p, c, s, d), v in agg.items()
                            if c == "Outflow - Indirect Expense" and s})
    for sub in indirect_subs:
        add(sub, "subsection", indent=2)
        dets = sorted({d for (p, c, s_, d), v in agg.items()
                       if c == "Outflow - Indirect Expense" and s_ == sub and d})
        for det in dets:
            add(det, "leaf",
                pull(cat="Outflow - Indirect Expense", sub=sub, det=det),
                indent=3)
        add(f"Total {sub}", "subtotal_section",
            pull(cat="Outflow - Indirect Expense", sub=sub), indent=2)
    add("TOTAL OPEX - INDIRECT EXPENSE", "subtotal_section",
        pull(cat="Outflow - Indirect Expense"), indent=1)
    add("", "blank")

    others_cats = ["Outflow - Imprest Fund", "Outflow - Cash Advance",
                   "Outflow - Bank Guarantee"]
    others_present = [c for c in others_cats
                      if any(c == cc and v != 0
                             for (pp, cc, ss, dd), v in agg.items())]
    if others_present:
        add("OTHERS", "subsection", indent=1)
        for c in others_present:
            dets = sorted({d for (p, cc, s, d), v in agg.items()
                           if cc == c and d})
            for det in dets:
                add(det, "leaf", pull(cat=c, det=det), indent=2)
        others_total = defaultdict(float)
        for c in others_present:
            for p, v in pull(cat=c).items():
                others_total[p] += v
        add("TOTAL OTHERS", "subtotal_section", dict(others_total), indent=1)
        add("", "blank")

    add("FINANCE COST", "subsection", indent=1)
    fc_leaves = {}
    for (p, c, s, d), v in agg.items():
        if c != "Outflow - Finance Cost":
            continue
        leaf = s if s and s != "Finance Cost" else (d or "Other Finance Cost")
        fc_leaves.setdefault(leaf, defaultdict(float))[p] += v
    for leaf in sorted(fc_leaves.keys()):
        add(leaf, "leaf", dict(fc_leaves[leaf]), indent=2)
    add("TOTAL FINANCE COST", "subtotal_section",
        pull(cat="Outflow - Finance Cost"), indent=1)
    add("", "blank")

    outflow_total = defaultdict(float)
    for (p, c, s, d), v in agg.items():
        if c.startswith("Outflow"):
            outflow_total[p] += v
    add("TOTAL OUTFLOW", "section_total", dict(outflow_total))
    add("", "blank")

    inc = pull(cat="Incoming")
    net = {p: inc.get(p, 0) + outflow_total.get(p, 0) for p in periods}
    add("NET CASH SURPLUS (LOSS)", "section_total", net)

    return lines
