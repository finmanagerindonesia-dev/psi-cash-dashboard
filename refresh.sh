#!/usr/bin/env bash
# ============================================================
# PSI Cash Flow Dashboard - One-Click Refresh (Mac/Linux)
# ============================================================
set -e
cd "$(dirname "$0")"

echo
echo "===================================================="
echo "  PSI CASH FLOW DASHBOARD - REFRESH"
echo "===================================================="
echo

# Check that Excel is closed
if [ -f "~\$PSI Cash Monitoring Master.xlsx" ]; then
  echo "[ERROR] Excel file is currently OPEN."
  echo "        Please close 'PSI Cash Monitoring Master.xlsx' and try again."
  exit 1
fi

echo "[1/3] Refreshing CF Summary + Bank sheets + data.json ..."
python3 scripts/refresh_dashboard.py

if [ ! -d ".git" ]; then
  echo
  echo "[INFO] Not a Git repo. Skipping Git push."
  echo "       To enable auto-deploy to Vercel:"
  echo "         git init && git remote add origin <your repo URL>"
  echo "         (then connect this repo to Vercel)"
  exit 0
fi

echo
echo "[2/3] Staging changes ..."
git add public/ scripts/ vercel.json README.md .gitignore refresh.bat refresh.sh

echo
echo "[3/3] Committing and pushing ..."
stamp=$(date '+%Y-%m-%d %H:%M')
git commit -m "Refresh dashboard $stamp" || echo "[INFO] No changes to commit."
git push

echo
echo "===================================================="
echo "  DONE. Vercel will auto-rebuild in ~30 seconds."
echo "===================================================="
