// PSI Cash Flow Dashboard - app logic

const FORMATS = {
  IDR:{label:"Rp", div:1, decimals:0, hint:"Rupiah"},
  USD:{label:"US$", div:17000, decimals:0, hint:"US Dollar"},
  INR:{label:"Rs", div:189, decimals:0, hint:"Indian Rupee"},
};
let CUR = localStorage.getItem("psi_cur") || "IDR";
let DATA = null;
let SELECTED_PERIOD = null;
let TAB = localStorage.getItem("psi_tab") || "monthly";
let CHARTS = {};

function fmtDate(d){
  if(!d) return "-";
  const dt = new Date(d + "T00:00:00");
  return dt.toLocaleDateString("en-US", {day:"numeric", month:"short", year:"numeric"});
}
function fmt(n, cur){
  if(n===null||n===undefined||isNaN(n)) return "-";
  const f = FORMATS[cur||CUR];
  const v = (n / f.div);
  if(Math.abs(v) < 0.005) return "-";
  const s = v.toLocaleString("en-US",{maximumFractionDigits:f.decimals,minimumFractionDigits:f.decimals});
  return v < 0 ? `(${s.replace("-","")})` : s;
}
function fmtBig(n, cur){
  if(n===null||n===undefined||isNaN(n)) return "-";
  const f = FORMATS[cur||CUR];
  return f.label + " " + fmt(n, cur);
}
function fmtCompact(n, cur){
  if(n===null||n===undefined||isNaN(n)) return "-";
  const f = FORMATS[cur||CUR];
  const v = Math.abs(n / f.div);
  let s; if(v>=1e9) s=(v/1e9).toFixed(2)+"B";
  else if(v>=1e6) s=(v/1e6).toFixed(1)+"M";
  else if(v>=1e3) s=(v/1e3).toFixed(0)+"K";
  else s=v.toFixed(0);
  return (n<0?"-":"")+s;
}
function escapeHtml(s){
  return String(s||"").replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
}
function el(html){
  const t = document.createElement("template"); t.innerHTML = html.trim();
  return t.content.firstChild;
}

// Bank-aware formatter: for USD tab, use native USD if provided.
function fmtBankAmt(idrAmt, nativeUsdAmt){
  if(CUR === "USD" && nativeUsdAmt !== null && nativeUsdAmt !== undefined){
    if(Math.abs(nativeUsdAmt) < 0.005) return "US$ -";
    const s = nativeUsdAmt.toLocaleString("en-US",{maximumFractionDigits:0,minimumFractionDigits:0});
    return "US$ " + (nativeUsdAmt < 0 ? `(${s.replace("-","")})` : s);
  }
  return fmtBig(idrAmt);
}
function fmtTotalCash(idrTotal, usdTotal){
  if(CUR === "USD" && usdTotal !== null && usdTotal !== undefined){
    if(Math.abs(usdTotal) < 0.005) return "US$ -";
    const s = usdTotal.toLocaleString("en-US",{maximumFractionDigits:0,minimumFractionDigits:0});
    return "US$ " + (usdTotal < 0 ? `(${s.replace("-","")})` : s);
  }
  return fmtBig(idrTotal);
}
function computeTotalCashByCurrency(bankIdrMap, bankUsdMap){
  if(CUR === "IDR") return Object.values(bankIdrMap).reduce((a,v)=>a+v, 0);
  if(CUR === "INR") return Object.values(bankIdrMap).reduce((a,v)=>a+v, 0) / 189;
  let total = 0;
  for(const bank in bankIdrMap){
    if(bankUsdMap && bankUsdMap[bank] !== undefined && bankUsdMap[bank] !== null){
      total += bankUsdMap[bank];
    } else {
      total += bankIdrMap[bank] / 17000;
    }
  }
  return total;
}

// ----- Encryption (matches Python lib_crypto.py) -----
async function decryptPayload(enc, password){
  const b64 = (s) => Uint8Array.from(atob(s), c=>c.charCodeAt(0));
  const baseKey = await crypto.subtle.importKey("raw",
    new TextEncoder().encode(password), {name:"PBKDF2"}, false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
    {name:"PBKDF2", salt: b64(enc.salt), iterations: enc.iter, hash:"SHA-256"},
    baseKey, {name:"AES-GCM", length: 256}, false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt(
    {name:"AES-GCM", iv: b64(enc.iv)}, key, b64(enc.ct));
  return JSON.parse(new TextDecoder().decode(plain));
}
async function tryDecryptAndApply(enc, password){
  try {
    const data = await decryptPayload(enc, password);
    window._PSI_ENCRYPTED = true;
    sessionStorage.setItem("psi_pw", password);
    hidePwGate(); applyData(data); return true;
  } catch(e){ return false; }
}
function showPwGate(enc){
  const gate = document.getElementById("pwGate");
  gate.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  const form = document.getElementById("pwForm");
  const input = document.getElementById("pwInput");
  const btn = document.getElementById("pwBtn");
  const err = document.getElementById("pwErr");
  const cached = sessionStorage.getItem("psi_pw");
  if(cached){ tryDecryptAndApply(enc, cached); }
  setTimeout(()=>input.focus(), 50);
  form.addEventListener("submit", async (e)=>{
    e.preventDefault();
    err.classList.add("hidden");
    btn.disabled = true; btn.textContent = "Opening...";
    const ok = await tryDecryptAndApply(enc, input.value);
    if(!ok){
      err.textContent = "Incorrect password. Try again.";
      err.classList.remove("hidden");
      btn.disabled = false; btn.textContent = "Open Dashboard";
      input.select();
    }
  });
}
function hidePwGate(){
  document.getElementById("pwGate").classList.add("hidden");
  document.body.style.overflow = "";
}
function logout(){
  sessionStorage.removeItem("psi_pw");
  location.reload();
}

// ----- Load -----
function applyData(d){
  DATA = d;
  if(!SELECTED_PERIOD){
    SELECTED_PERIOD = d.periods[d.periods.length-1].key;
  }
  document.getElementById("company").textContent = d.company;
  document.getElementById("stamp").textContent =
    "Last updated: " + new Date(d.generated_at).toLocaleString("en-US");
  populatePeriodSelect();
  render();
  if(window._PSI_ENCRYPTED){
    document.getElementById("logoutBtn").classList.remove("hidden");
  }
}

function load(){
  if (window.PSI_DATA_ENCRYPTED) { showPwGate(window.PSI_DATA_ENCRYPTED); return; }
  if (window.PSI_DATA) {
    try { applyData(window.PSI_DATA); return; }
    catch(e){ console.error("Embedded data error:", e); }
  }
  fetch("data.json?ts="+Date.now()).then(r=>r.json()).then(d=>{
    if(d && d.encrypted){ showPwGate(d); }
    else { applyData(d); }
  }).catch(e=>{
    document.getElementById("root").innerHTML =
      `<div class="empty"><b>Failed to load dashboard data.</b><br><br>` +
      `<small>${escapeHtml(e.message)}</small><br><br>` +
      `Make sure <code>refresh.bat</code> has been run first.</div>`;
  });
}

function populatePeriodSelect(){
  const sel = document.getElementById("periodSel");
  sel.innerHTML = DATA.periods.map(p=>`<option value="${p.key}">${p.label_long}</option>`).join("");
  sel.value = SELECTED_PERIOD;
  sel.onchange = () => { SELECTED_PERIOD = sel.value; render(); };
}

function render(){
  const r = document.getElementById("root");
  r.innerHTML = "";
  const asof = DATA.daily && DATA.daily.as_of;
  document.getElementById("asOfBanner").innerHTML =
    asof ? `Data as of: <b>${fmtDate(asof)}</b>` : "";
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === TAB));
  if(TAB === "daily") {
    r.appendChild(renderDailyKPIs());
    r.appendChild(renderDailyBankTable());
    r.appendChild(renderWeeklyView());
    r.appendChild(renderDailyPositionChart());
    r.appendChild(renderDailyInOutChart());
  } else {
    r.appendChild(renderKPIs());
    r.appendChild(renderRow2());
    r.appendChild(renderBankMatrix());
    const fx = renderFXRates();
    if(fx) r.appendChild(fx);
    r.appendChild(renderTrend());
    r.appendChild(renderCFSummary());
  }
}

// =============================================================================
// DAILY VIEW
// =============================================================================
function renderDailyKPIs(){
  const D = DATA.daily;
  if(!D || !D.as_of){
    return el(`<div class="card"><div class="empty">No daily data available.</div></div>`);
  }
  const div = el(`<div class="kpi-row"></div>`);
  const monthName = new Date(D.as_of + "T00:00:00").toLocaleDateString("en-US",{month:"long"});
  const totalCashCur = computeTotalCashByCurrency(D.current_position, D.current_position_usd);
  const totalCashStr = (CUR === "USD")
    ? fmtTotalCash(D.current_total, totalCashCur)
    : fmtBig(D.current_total);
  div.appendChild(el(`<div class="kpi pos">
    <div class="lbl">Cash Position - As of ${fmtDate(D.as_of)}</div>
    <div class="val">${totalCashStr}</div>
    <div class="sub">Across all bank accounts (real-time)</div></div>`));
  div.appendChild(el(`<div class="kpi pos">
    <div class="lbl">${monthName} - Inflow MTD</div>
    <div class="val">${fmtBig(D.mtd.inflow)}</div>
    <div class="sub">Month-to-date receipts</div></div>`));
  div.appendChild(el(`<div class="kpi neg">
    <div class="lbl">${monthName} - Outflow MTD</div>
    <div class="val">${fmtBig(D.mtd.outflow)}</div>
    <div class="sub">Month-to-date payments</div></div>`));
  const netCls = D.mtd.net >= 0 ? "pos" : "neg";
  div.appendChild(el(`<div class="kpi ${netCls}">
    <div class="lbl">${monthName} - Net MTD</div>
    <div class="val">${fmtBig(D.mtd.net)}</div>
    <div class="sub">${D.mtd.net >= 0 ? "Surplus this month so far" : "Deficit this month so far"}</div></div>`));
  return div;
}

function renderDailyBankTable(){
  const D = DATA.daily;
  const showDates = D.dates.slice(-7).reverse();
  const banks = D.banks;
  const usdMap = D.bank_position_usd || {};
  let headerCells = banks.map(b => {
    const cur = (DATA.bank_currencies && DATA.bank_currencies[b]) || "IDR";
    const tag = cur === "USD" ? ' <span class="muted" style="font-size:10px;font-weight:400">(USD)</span>' : "";
    return `<th>${escapeHtml(b)}${tag}</th>`;
  }).join("");
  let rows = showDates.map((d, idx) => {
    let total = 0;
    let totalUsd = 0;
    let totalUsdValid = (CUR === "USD");
    let cells = banks.map(b => {
      const idrV = D.bank_position[b][d] || 0;
      const usdV = (usdMap[b] && usdMap[b][d] !== undefined) ? usdMap[b][d] : null;
      total += idrV;
      if(totalUsdValid){
        if(usdV !== null) totalUsd += usdV;
        else totalUsd += idrV / 17000;
      }
      return `<td>${fmtBankAmt(idrV, usdV)}</td>`;
    }).join("");
    const isLatest = (idx === 0);
    const cls = isLatest ? "row-latest" : "";
    const totalDisplay = (CUR === "USD") ? fmtTotalCash(total, totalUsd) : fmtBig(total);
    return `<tr class="${cls}">
      <td class="date-cell">${fmtDate(d)}${isLatest ? ' <span class="latest-tag">Latest</span>' : ''}</td>
      ${cells}
      <td class="total-cell">${totalDisplay}</td>
    </tr>`;
  }).join("");
  return el(`<div class="card">
    <h2>Bank Position - Daily Ledger
      <span class="pill">Last ${showDates.length} active days</span>
    </h2>
    <div class="scroll-x">
      <table class="ledger">
        <thead><tr>
          <th>Date</th>
          ${headerCells}
          <th>Total</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div></div>`);
}

function renderWeeklyView(){
  const D = DATA.daily;
  const W = D && D.weekly;
  if(!W || !W.weeks || !W.weeks.length){
    return el(`<div class="card">
      <h2>Weekly Activity</h2>
      <div class="empty">No transactions in the current month.</div></div>`);
  }
  const weekItems = W.weeks.map((w, wi) => {
    const isCurrent = (D.as_of >= w.start && D.as_of <= w.end);
    const cats = w.by_category.map((c, ci) => {
      const txRows = c.transactions.map(t => {
        const cls = t.amount > 0 ? "pos" : "neg";
        return `<tr>
          <td>${fmtDate(t.date)}</td>
          <td>${escapeHtml(t.bank || "-")}</td>
          <td>${escapeHtml(t.detail || "-")}</td>
          <td class="party-cell" title="${escapeHtml(t.party || "")}">${escapeHtml(t.party || "-")}</td>
          <td class="amt ${cls}">${fmtBig(t.amount)}</td>
        </tr>`;
      }).join("");
      const kindCls = c.kind === "inflow" ? "pos" : "neg";
      return `
      <div class="subgroup">
        <div class="shead" onclick="toggleSub(this.parentElement)">
          <span class="arrow">&#9656;</span>
          <span class="sname">${escapeHtml(c.label)}<span class="scount">(${c.tx_count} tx)</span></span>
          <span class="samt amount ${kindCls}">${fmtBig(c.amount)}</span>
        </div>
        <div class="parties">
          <div class="scroll-x"><table class="tx">
            <thead><tr><th>Date</th><th>Bank</th><th>Detail</th><th>Party</th><th style="text-align:right">Amount</th></tr></thead>
            <tbody>${txRows || '<tr><td colspan="5" class="empty">No transactions.</td></tr>'}</tbody>
          </table></div>
        </div>
      </div>`;
    }).join("");
    const netCls = w.net >= 0 ? "pos" : "neg";
    const tag = isCurrent ? '<span class="latest-tag">Current</span>' : '';
    return `
    <div class="fgroup ${isCurrent ? 'open' : ''}" data-wi="${wi}">
      <div class="fhead" onclick="toggleFGroup(this.parentElement)">
        <div class="arrow">&#9656;</div>
        <div class="fname">${escapeHtml(w.label)} <span class="muted" style="font-weight:400">${escapeHtml(w.date_range)}</span> ${tag}
          <span class="muted" style="font-weight:500;font-size:11.5px">- ${w.tx_count} transactions</span>
        </div>
        <div class="weekly-summary">
          <span class="amount pos" title="Inflow">+${fmtBig(w.inflow)}</span>
          <span class="amount neg" title="Outflow">${fmtBig(w.outflow)}</span>
          <span class="amount ${netCls}" title="Net" style="font-weight:700;border-left:2px solid var(--line);padding-left:10px">Net ${fmtBig(w.net)}</span>
        </div>
      </div>
      <div class="fbody">${cats || '<div class="muted">No categorized transactions.</div>'}</div>
    </div>`;
  }).join("");

  return el(`<div class="card">
    <h2>Weekly Activity <span class="pill">${escapeHtml(W.month_label)}</span></h2>
    <div class="body">
      <div class="muted" style="margin-bottom:10px;font-size:12px">
        Click any week to expand and see transactions grouped by category. Click a category for detail.
      </div>
      <div class="flow">${weekItems}</div>
    </div></div>`);
}

function renderDailyPositionChart(){
  const D = DATA.daily;
  const card = el(`<div class="card">
    <h2>Daily Cash Position Trend</h2>
    <div class="body"><div class="chart-wrap tall"><canvas id="ch_dailypos"></canvas></div></div></div>`);
  setTimeout(()=>{
    if(CHARTS.dailypos) CHARTS.dailypos.destroy();
    const labels = D.totals.map(t=>t.date);
    const div = FORMATS[CUR].div;
    const data = D.totals.map(t => t.total / div);
    CHARTS.dailypos = new Chart(document.getElementById("ch_dailypos"), {
      type: "line",
      data: {labels, datasets:[{label:"Cash Position", data,
        borderColor:"#1f3864", backgroundColor:"#1f386422",
        borderWidth:2.5, tension:.2, pointRadius:2, pointHoverRadius:5, fill:true}]},
      options: {
        responsive:true, maintainAspectRatio:false,
        plugins:{legend:{display:false},
          tooltip:{callbacks:{
            title:(ctx)=>fmtDate(ctx[0].label),
            label:(c)=>` ${FORMATS[CUR].label} ${c.parsed.y.toLocaleString("en-US",{maximumFractionDigits:0})}`
          }}},
        scales:{
          x:{ticks:{maxTicksLimit:12, callback:function(v){
            const d = this.getLabelForValue(v);
            const dt = new Date(d + "T00:00:00");
            return dt.toLocaleDateString("en-US",{day:"numeric",month:"short"});
          }}},
          y:{ticks:{callback:(v)=>fmtCompact(v*div)}}
        }
      }
    });
  },10);
  return card;
}

function renderDailyInOutChart(){
  const D = DATA.daily;
  const active = D.inout.filter(io => io.inflow !== 0 || io.outflow !== 0).slice(-60);
  const card = el(`<div class="card">
    <h2>Daily Cash In / Out (last ${active.length} active days)</h2>
    <div class="legend-mini">
      <span><i style="background:#0a8754"></i>Inflow</span>
      <span><i style="background:#c0392b"></i>Outflow</span>
      <span><i style="background:#1f3864"></i>Net</span>
    </div>
    <div class="body"><div class="chart-wrap tall"><canvas id="ch_dailyio"></canvas></div></div></div>`);
  setTimeout(()=>{
    if(CHARTS.dailyio) CHARTS.dailyio.destroy();
    const labels = active.map(io=>io.date);
    const div = FORMATS[CUR].div;
    CHARTS.dailyio = new Chart(document.getElementById("ch_dailyio"), {
      type: "bar",
      data: {labels, datasets:[
        {label:"Inflow", data:active.map(io=>io.inflow/div),
         backgroundColor:"#0a8754cc", borderColor:"#0a8754", borderWidth:1, order:2},
        {label:"Outflow", data:active.map(io=>io.outflow/div),
         backgroundColor:"#c0392bcc", borderColor:"#c0392b", borderWidth:1, order:2},
        {label:"Net", type:"line", data:active.map(io=>io.net/div),
         borderColor:"#1f3864", borderWidth:2, tension:.15, pointRadius:3, order:1},
      ]},
      options: {
        responsive:true, maintainAspectRatio:false,
        plugins:{legend:{display:false},
          tooltip:{callbacks:{
            title:(ctx)=>fmtDate(ctx[0].label),
            label:(c)=>` ${c.dataset.label}: ${FORMATS[CUR].label} ${c.parsed.y.toLocaleString("en-US",{maximumFractionDigits:0})}`
          }}},
        scales:{
          x:{ticks:{maxTicksLimit:15, callback:function(v){
            const d = this.getLabelForValue(v);
            const dt = new Date(d + "T00:00:00");
            return dt.toLocaleDateString("en-US",{day:"numeric",month:"short"});
          }}},
          y:{ticks:{callback:(v)=>fmtCompact(v*div)}}
        }
      }
    });
  },10);
  return card;
}

// =============================================================================
// MONTHLY VIEW
// =============================================================================
function renderKPIs(){
  const D = DATA;
  const idx = D.periods.findIndex(p=>p.key===SELECTED_PERIOD);
  const p = D.periods[idx];
  const inflow = D.trend.inflow[idx];
  const outflow = D.trend.outflow[idx];
  const net = D.trend.net[idx];
  const ending = D.trend.ending[idx];
  const prevEnding = idx>0 ? D.trend.ending[idx-1] : null;
  const prevNet = idx>0 ? D.trend.net[idx-1] : null;
  const trendBadge = (now, prev) => {
    if(prev===null||prev===undefined) return "";
    const diff = now - prev;
    if(Math.abs(diff) < 1) return "";
    const cls = diff >= 0 ? "up" : "dn";
    const arr = diff >= 0 ? "&#9650;" : "&#9660;";
    return `<span class="trend ${cls}">${arr} ${fmtCompact(Math.abs(diff))}</span>`;
  };
  // For USD tab on the cash position card, use native USD when available
  let endingDisplay = fmtBig(ending);
  if(CUR === "USD" && D.bank_position_matrix){
    const m = D.bank_position_matrix;
    let totalUsd = 0;
    for(const b of m.banks){
      const cell = m.data[b][p.key];
      if(cell.ending_usd !== undefined) totalUsd += cell.ending_usd;
      else totalUsd += cell.ending / 17000;
    }
    endingDisplay = fmtTotalCash(ending, totalUsd);
  }
  const div = el(`<div class="kpi-row"></div>`);
  div.appendChild(el(`<div class="kpi pos">
    <div class="lbl">Cash Position - End of ${p.label_short}</div>
    <div class="val">${endingDisplay}${trendBadge(ending, prevEnding)}</div>
    <div class="sub">Total balance across all bank accounts</div></div>`));
  div.appendChild(el(`<div class="kpi pos">
    <div class="lbl">Inflow - ${p.label_short}</div>
    <div class="val">${fmtBig(inflow)}</div>
    <div class="sub">Customers + Bank Loans + Others</div></div>`));
  div.appendChild(el(`<div class="kpi neg">
    <div class="lbl">Outflow - ${p.label_short}</div>
    <div class="val">${fmtBig(outflow)}</div>
    <div class="sub">CAPEX + OPEX + Loan Repayments + Finance Cost</div></div>`));
  const netCls = net>=0 ? "pos" : "neg";
  div.appendChild(el(`<div class="kpi ${netCls}">
    <div class="lbl">Net (Inflow - Outflow) - ${p.label_short}</div>
    <div class="val">${fmtBig(net)}${trendBadge(net, prevNet)}</div>
    <div class="sub">${net>=0 ? "Surplus this month" : "Deficit this month"}</div></div>`));
  return div;
}

function renderRow2(){
  const div = el(`<div class="row2"></div>`);
  div.appendChild(renderIncoming());
  div.appendChild(renderOutflow());
  return div;
}

function renderIncoming(){
  const D = DATA;
  const data = D.incoming_drill[SELECTED_PERIOD];
  const periodLbl = D.periods.find(p=>p.key===SELECTED_PERIOD).label_long;
  const card = el(`<div class="card">
    <h2>Where Did the Money Come From? <span class="pill">${escapeHtml(periodLbl)}</span></h2>
    <div class="body" id="incBody"></div></div>`);
  if(!data || !data.groups.length){
    card.querySelector("#incBody").innerHTML = `<div class="empty">No data for this period.</div>`;
    return card;
  }
  const total = data.total;
  const max = Math.max(...data.groups.map(g=>Math.abs(g.amount)));
  const groups = data.groups.map((g,i)=>{
    const partyRows = g.parties.map(p=>`
      <div class="party pos">
        <span class="pname" title="${escapeHtml(p.label)}">${escapeHtml(p.label)}</span>
        <span class="pbar"><i style="width:${(Math.abs(p.amount)/Math.abs(g.amount)*100).toFixed(1)}%"></i></span>
        <span class="pamt">${fmtBig(p.amount)}</span>
      </div>`).join("");
    return `
    <div class="fgroup" data-i="${i}">
      <div class="fhead" onclick="toggleFGroup(this.parentElement)">
        <div class="arrow">&#9656;</div>
        <div class="fname">${escapeHtml(g.label)} <span class="fpct">${g.pct.toFixed(1)}%</span></div>
        <div class="famt amount pos">${fmtBig(g.amount)}</div>
      </div>
      <div class="fbar-wrap"><div class="fbar pos"><i style="width:${(Math.abs(g.amount)/max*100).toFixed(1)}%"></i></div></div>
      <div class="fbody">
        <div class="muted" style="margin-bottom:6px;font-size:11.5px">${g.party_count} parties (top ${g.parties.length}):</div>
        ${partyRows || '<div class="muted">No detail available.</div>'}
      </div>
    </div>`;
  }).join("");
  card.querySelector("#incBody").innerHTML = `
    <div class="flow">${groups}</div>
    <div style="margin-top:14px;padding:12px 16px;background:var(--pos-bg);border-radius:9px;font-weight:700;color:var(--pos);display:flex;justify-content:space-between">
      <span>TOTAL INFLOW</span><span>${fmtBig(total)}</span>
    </div>`;
  return card;
}

function renderOutflow(){
  const D = DATA;
  const data = D.outflow_drill[SELECTED_PERIOD];
  const periodLbl = D.periods.find(p=>p.key===SELECTED_PERIOD).label_long;
  const card = el(`<div class="card">
    <h2>Where Did the Money Go? <span class="pill">${escapeHtml(periodLbl)}</span></h2>
    <div class="body" id="outBody"></div></div>`);
  if(!data || !data.buckets.length){
    card.querySelector("#outBody").innerHTML = `<div class="empty">No data for this period.</div>`;
    return card;
  }
  const total = data.total;
  const maxBucket = Math.max(...data.buckets.map(b=>Math.abs(b.amount)));
  const buckets = data.buckets.map((b,bi)=>{
    const subItems = b.subgroups.map((s,si)=>{
      const maxParty = s.parties[0] ? Math.abs(s.parties[0].amount) : 1;
      const partyRows = s.parties.map(p=>`
        <div class="party neg">
          <span class="pname" title="${escapeHtml(p.label)}">${escapeHtml(p.label)}</span>
          <span class="pbar"><i style="width:${(Math.abs(p.amount)/maxParty*100).toFixed(1)}%"></i></span>
          <span class="pamt">${fmtBig(p.amount)}</span>
        </div>`).join("");
      return `
      <div class="subgroup" data-si="${si}">
        <div class="shead" onclick="toggleSub(this.parentElement)">
          <span class="arrow">&#9656;</span>
          <span class="sname">${escapeHtml(s.label)}<span class="scount">(${s.party_count} parties)</span></span>
          <span class="samt amount neg">${fmtBig(s.amount)}</span>
        </div>
        <div class="parties">${partyRows || '<div class="muted">No detail available.</div>'}</div>
      </div>`;
    }).join("");
    return `
    <div class="fgroup" data-bi="${bi}">
      <div class="fhead" onclick="toggleFGroup(this.parentElement)">
        <div class="arrow">&#9656;</div>
        <div class="fname">${escapeHtml(b.label)} <span class="fpct">${b.pct.toFixed(1)}%</span></div>
        <div class="famt amount neg">${fmtBig(b.amount)}</div>
      </div>
      <div class="fbar-wrap"><div class="fbar neg"><i style="width:${(Math.abs(b.amount)/maxBucket*100).toFixed(1)}%"></i></div></div>
      <div class="fbody">${subItems}</div>
    </div>`;
  }).join("");
  card.querySelector("#outBody").innerHTML = `
    <div class="flow">${buckets}</div>
    <div style="margin-top:14px;padding:12px 16px;background:var(--neg-bg);border-radius:9px;font-weight:700;color:var(--neg);display:flex;justify-content:space-between">
      <span>TOTAL OUTFLOW</span><span>${fmtBig(total)}</span>
    </div>`;
  return card;
}

function toggleFGroup(g){ g.classList.toggle("open"); }
function toggleSub(s){ s.classList.toggle("open"); }
window.toggleFGroup = toggleFGroup;
window.toggleSub = toggleSub;

function renderBankMatrix(){
  const D = DATA;
  const m = D.bank_position_matrix;
  const card = el(`<div class="card">
    <h2>Bank Position - End of Each Month</h2>
    <div class="scroll-x" id="bmBody"></div></div>`);
  const allEndings = m.banks.flatMap(b=>m.periods.map(p=>m.data[b][p].ending));
  const maxAbs = Math.max(...allEndings.map(Math.abs), 1);
  const heatColor = (v)=>{
    if(Math.abs(v) < 1) return "#fafbfd";
    const intensity = Math.min(Math.abs(v)/maxAbs, 1);
    const a = (0.10 + intensity*0.55).toFixed(2);
    return v>0 ? `rgba(10,135,84,${a})` : `rgba(192,57,43,${a})`;
  };
  const periodHeaders = D.periods.map(p=>`<th>${escapeHtml(p.label_long)}</th>`).join("");
  const rows = m.banks.map(b=>{
    const cur = (DATA.bank_currencies && DATA.bank_currencies[b]) || "IDR";
    const tag = cur === "USD" ? ' <span class="muted" style="font-size:10px;font-weight:400">(USD)</span>' : "";
    const cells = D.periods.map(p=>{
      const cell = m.data[b][p.key];
      const v = cell.ending;
      const usdV = cell.ending_usd !== undefined ? cell.ending_usd : null;
      const ch = cell.change;
      const ch_str = ch ? ` <span class="muted" style="font-size:10.5px">(Δ ${fmtCompact(ch)})</span>` : "";
      return `<td><span class="heat" style="background:${heatColor(v)}">${fmtBankAmt(v, usdV)}${ch_str}</span></td>`;
    }).join("");
    return `<tr><td>${escapeHtml(b)}${tag}</td>${cells}</tr>`;
  }).join("");
  const totalRow = D.periods.map(p=>{
    let totalUsd = 0;
    if(CUR === "USD"){
      for(const b of m.banks){
        const cell = m.data[b][p.key];
        if(cell.ending_usd !== undefined) totalUsd += cell.ending_usd;
        else totalUsd += cell.ending / 17000;
      }
    }
    const display = (CUR === "USD") ? fmtTotalCash(m.totals[p.key], totalUsd) : fmtBig(m.totals[p.key]);
    return `<td>${display}</td>`;
  }).join("");
  card.querySelector("#bmBody").innerHTML = `
    <table class="bank-matrix">
      <thead><tr><th>Bank</th>${periodHeaders}</tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr class="total"><td>TOTAL CASH POSITION</td>${totalRow}</tr></tfoot>
    </table>`;
  return card;
}

function renderTrend(){
  const D = DATA;
  const card = el(`<div class="card">
    <h2>Cash Flow Trend</h2>
    <div class="legend-mini">
      <span><i style="background:#0a8754"></i>Inflow</span>
      <span><i style="background:#c0392b"></i>Outflow</span>
      <span><i style="background:#1f3864"></i>Net</span>
      <span><i style="background:#f0a020"></i>Ending Cash</span>
    </div>
    <div class="body"><div class="chart-wrap tall"><canvas id="ch_trend"></canvas></div></div></div>`);
  setTimeout(()=>{
    if(CHARTS.trend) CHARTS.trend.destroy();
    const ctx = document.getElementById("ch_trend");
    const labels = D.periods.map(p=>p.label_short);
    const div = FORMATS[CUR].div;
    CHARTS.trend = new Chart(ctx,{
      type:"bar",
      data:{labels,datasets:[
        {label:"Inflow", data:D.trend.inflow.map(v=>v/div),
         backgroundColor:"#0a875499", borderColor:"#0a8754", borderWidth:1, order:2},
        {label:"Outflow", data:D.trend.outflow.map(v=>v/div),
         backgroundColor:"#c0392b99", borderColor:"#c0392b", borderWidth:1, order:2},
        {label:"Net", type:"line", data:D.trend.net.map(v=>v/div),
         borderColor:"#1f3864", backgroundColor:"#1f386422", borderWidth:2.5, tension:.25, pointRadius:5, order:1},
        {label:"Ending Cash Position", type:"line", data:D.trend.ending.map(v=>v/div),
         borderColor:"#f0a020", borderWidth:2.5, tension:.25, pointRadius:5, borderDash:[4,3], order:1},
      ]},
      options:{
        responsive:true, maintainAspectRatio:false,
        plugins:{legend:{display:false},
          tooltip:{callbacks:{label:(c)=>` ${c.dataset.label}: ${FORMATS[CUR].label} ${c.parsed.y.toLocaleString("en-US",{maximumFractionDigits:0})}`}}},
        scales:{y:{ticks:{callback:(v)=>fmtCompact(v*div)}}}
      }
    });
  },10);
  return card;
}

function renderFXRates(){
  const rates = DATA.monthly_fx_rates;
  if(!rates) return null;
  const periods = DATA.periods;
  const hasAny = periods.some(p => rates[p.key]);
  // Build cells for each period (always show, fallback if no data)
  const cells = periods.map(p => {
    const info = rates[p.key];
    if(info && info.rate){
      return `<div class="fx-chip">
        <div class="fx-month">${escapeHtml(p.label_short)}</div>
        <div class="fx-rate">Rp ${Math.round(info.rate).toLocaleString("en-US")}</div>
        <div class="fx-samples">${info.samples} tx</div>
      </div>`;
    }
    return `<div class="fx-chip fx-empty">
      <div class="fx-month">${escapeHtml(p.label_short)}</div>
      <div class="fx-rate muted">-</div>
      <div class="fx-samples muted">no data</div>
    </div>`;
  }).join("");
  const note = hasAny
    ? `Computed as weighted average from USD bank transactions (sum of IDR / sum of native USD).`
    : `<b>No native USD data found in column M of "All Banks".</b> Treasury can fill column M with native USD amounts for Mandiri USD / SBI USD entries to see actual FX rates here.`;
  return el(`<div class="card">
    <h2>USD/IDR Exchange Rates Used <span class="pill">per Month</span></h2>
    <div class="body">
      <div class="fx-chips">${cells}</div>
      <div class="muted" style="margin-top:10px;font-size:11.5px">${note}</div>
    </div></div>`);
}

function renderCFSummary(){
  const D = DATA;
  const card = el(`<div class="card">
    <h2>Cash Flow Summary - Detailed Table
      <button class="collapse-btn" id="cfToggle">Show Details</button>
    </h2>
    <div class="scroll-x hidden" id="cf_body"></div></div>`);
  card.querySelector("#cfToggle").onclick = (e) => {
    const body = card.querySelector("#cf_body");
    body.classList.toggle("hidden");
    e.target.textContent = body.classList.contains("hidden") ? "Show Details" : "Hide";
  };
  setTimeout(()=>{
    let html = `<table class="cf"><thead><tr><th>Particular</th>`;
    D.periods.forEach(p=>html += `<th>${escapeHtml(p.label_short)}</th>`);
    html += `<th>YTD</th></tr></thead><tbody>`;
    D.cf_summary.forEach(line=>{
      if(line.kind==="blank"){
        html += `<tr><td colspan="${D.periods.length+2}" style="border:0;padding:4px"></td></tr>`;
        return;
      }
      let cls;
      if(line.kind==="section_header") cls="section";
      else if(line.kind==="subsection") cls="subsection";
      else if(line.kind==="subtotal_section") cls="subtotal";
      else if(line.kind==="section_total") cls="section_total";
      else cls="leaf";
      const indent = line.indent ? `indent-${Math.min(3,line.indent)}` : "";
      html += `<tr class="${cls}"><td class="${indent}">${escapeHtml(line.label)}</td>`;
      let ytd = 0;
      D.periods.forEach(p=>{
        const v = (line.values && line.values[p.key]) || 0;
        ytd += v;
        const ac = v>0 ? "pos" : (v<0 ? "neg" : "zero");
        html += `<td class="amount ${ac}">${fmt(v)}</td>`;
      });
      const ac = ytd>0 ? "pos" : (ytd<0 ? "neg" : "zero");
      html += `<td class="amount ${ac}">${fmt(ytd)}</td></tr>`;
    });
    html += `</tbody></table>`;
    document.getElementById("cf_body").innerHTML = html;
  }, 10);
  return card;
}

document.getElementById("curgrp").addEventListener("click", (e)=>{
  const b = e.target.closest("button"); if(!b) return;
  CUR = b.dataset.cur;
  localStorage.setItem("psi_cur", CUR);
  document.querySelectorAll("#curgrp button").forEach(x=>x.classList.toggle("active", x.dataset.cur===CUR));
  if(DATA) render();
});
document.querySelectorAll("#curgrp button").forEach(x=>x.classList.toggle("active", x.dataset.cur===CUR));
document.getElementById("logoutBtn").addEventListener("click", logout);
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    TAB = btn.dataset.tab;
    localStorage.setItem("psi_tab", TAB);
    if(DATA) render();
  });
});
load();
