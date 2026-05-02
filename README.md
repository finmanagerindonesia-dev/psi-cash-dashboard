# PSI Cash Flow Dashboard

Auto-generated cash flow monitoring for **PT Prasad Seeds Indonesia**.

The dashboard is fed by `PSI Cash Monitoring Master.xlsx` (the file Treasury updates each day) and produces:

1. A regenerated **CF Summary** sheet inside the same workbook (replaces manual pivot copy/paste).
2. A regenerated **Bank - <Month>** sheet for each month (Jan, Feb, Mar, ...).
3. A live **HTML dashboard** at `public/index.html` that can be deployed to Vercel and shared with the boss via a simple URL.

## Folder layout

```
Cash Flow Dashboard Claude/
├── PSI Cash Monitoring Master.xlsx   ← Treasury updates this daily (source of truth)
├── refresh.bat                        ← Windows: one-click refresh + git push
├── refresh.sh                         ← Mac/Linux equivalent
├── scripts/
│   ├── refresh_dashboard.py           ← Main entry point
│   ├── lib_pivot.py
│   ├── lib_excel.py
│   ├── lib_dashboard.py
│   └── requirements.txt
├── public/                            ← Vercel deploys this folder
│   ├── index.html                     ← The live dashboard
│   └── data.json                      ← Auto-generated each refresh
├── backups/                           ← Auto-saved backup before each rewrite
├── vercel.json
├── .gitignore
└── README.md
```

## First-time setup (one-time, ~10 minutes)

### 1. Install Python and dependencies

```bash
python --version          # need Python 3.9+
pip install -r scripts/requirements.txt
```

### 2. Test the refresh locally

Close the Excel file in Excel, then double-click `refresh.bat` (Windows) or run `./refresh.sh` (Mac/Linux). You should see:

```
[1/3] Refreshing CF Summary + Bank sheets + data.json ...
[2/3] Staging changes for Git ...
[3/3] Committing and pushing ...
```

Open `public/index.html` in a browser to verify the dashboard renders.

### 3. Set up Git + GitHub (for Vercel)

```bash
cd "Cash Flow Dashboard Claude"
git init
git add .
git commit -m "Initial commit"
git branch -M main

# Create a private repo on GitHub (e.g. "psi-cash-dashboard")
git remote add origin https://github.com/<your-username>/psi-cash-dashboard.git
git push -u origin main
```

> Tip: keep the GitHub repo **private** — it contains sensitive financial data.

### 4. Connect Vercel

1. Sign in at <https://vercel.com> with GitHub.
2. Click **Add New → Project** → import the GitHub repo.
3. Vercel detects the `vercel.json` automatically. Just click **Deploy**.
4. After ~30 seconds you'll get a URL like `https://psi-cash-dashboard.vercel.app`.
5. Share that URL with the boss.

> Optional: in Vercel **Settings → Deployment Protection**, turn on "Vercel Authentication" so only invited people can open the URL.

## Daily workflow

When Treasury updates `PSI Cash Monitoring Master.xlsx`:

1. **Close Excel** (the script can't write to an open file).
2. Double-click **`refresh.bat`**.
3. Done. Vercel rebuilds in ~30 seconds and the boss's URL shows fresh data.

A backup of the Excel file is saved to `backups/` before each rewrite so nothing is lost if something goes wrong.

## What the dashboard shows

- **KPI strip** — Cash position, Inflow, Outflow, Net cash flow for the latest month.
- **Cash Flow Trend** — Bar + line chart across all months: inflow, outflow, net, ending balance.
- **Top Vendors / Parties (YTD)** — Who you're paying the most.
- **Outflow Mix (YTD)** — Doughnut showing CAPEX vs OPEX vs Loans vs Finance Cost mix.
- **Top Expense Sub-Categories** — Which sub-categories absorb the most cash. Switchable per month or YTD.
- **Bank Position** — Per-bank ending balance for any selected month (with opening + monthly Δ).
- **Cash Flow Summary table** — Full replica of the manual CF Summary sheet (auto-built).
- **Top Outflows (latest month)** — The 15 largest single outflows in the most recent month.

Currency toggle (top-right): IDR / USD / INR. The selected currency is remembered between visits.

## Troubleshooting

| Problem | Fix |
|---|---|
| `[ERROR] Excel file is currently OPEN` | Close Excel and re-run. |
| Dashboard says "Could not load data.json" | Run `refresh.bat` once; or hard-refresh browser (Ctrl+Shift+R). |
| Numbers don't match Tally | Treasury entries in `All Banks` need correcting. The script trusts the source. |
| Want to add a new month | Treasury simply adds the new month's transactions in `All Banks` — the script auto-detects new periods. |
| Want a different USD/INR rate | Update the `17000` and `189` numbers in row 2 of `CF Summary` before saving — the script reads them from there. |

## How the script categorizes data

The script reads the three management columns from `All Banks`:

- **Cash Flow Category** (e.g. `Outflow - CAPEX`)
- **Cash Flow Sub-Category** (e.g. `Repairs, Maintenance and Insurance (Assets)`)
- **Cash Flow Detail-Category** (e.g. `Repairs & Maintenance`)

Output structure:

| Section | Source filter |
|---|---|
| INCOMING | `Category = Incoming`, split by Detail-Category |
| CAPEX | `Category = Outflow - CAPEX`, by Detail-Category |
| INTERCOMPANY LOAN | `Category = Outflow - Loan`, excluding `Citibank Term Loan` and `DBS Term Loan` |
| BANK LOAN REPAYMENT | `Category = Outflow - Loan`, only the two bank term loans |
| OPEX - DIRECT EXPENSE | `Category = Outflow - Direct Expense`, by Sub-Category |
| OPEX - INDIRECT EXPENSE | `Category = Outflow - Indirect Expense`, grouped by Sub-Category → Detail-Category |
| OTHERS | Imprest Fund + Cash Advance + Bank Guarantee categories |
| FINANCE COST | `Category = Outflow - Finance Cost`, by Sub-Category |

Beginning Balance entries (per bank, per month) feed the **Bank Position** calculation. Ending balance = beginning + sum of all non-beginning entries for that month.

## Credits

Built for the PSI Finance team. For changes or feature requests, edit `scripts/lib_*.py`.
