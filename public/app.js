// PSI Cash Flow Dashboard - app logic

const FORMATS = {
  IDR:{label:"Rp", div:1, decimals:0, hint:"Rupiah"},
  USD:{label:"US$", div:17000, decimals:0, hint:"US Dollar"},
  INR:{label:"Rs", div:189, decimals:0, hint:"Indian Rupee"},
};
let CUR = localStorage.getItem("psi_cur") || "IDR";
let DATA = null;
let SELECTED_PERIOD = null;
let CHARTS = {};

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
  const v = n / f.div;
  return f.label + " " + fmt(n, cur);
}
function fmtCompact(n, cur){
  if(n===null||n===undefined||isNaN(n)) return "-";
  const f = FORMATS[cur||CUR];
  const v = Math.abs(n / f.div);
  let s; if(v>=1e9) s=(v/1e9).toFixed(2)+" M";
  else if(v>=1e6) s=(v/1e6).toFixed(1)+" jt";
  else if(v>=1e3) s=(v/1e3).toFixed(0)+" rb";
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

// ----- Load -----
function applyData(d){
  DATA = d;
  if(!SELECTED_PERIOD){
    SELECTED_PERIOD = d.periods[d.periods.length-1].key;
  }
  document.getElementById("company").textContent = d.company;
  document.getElementById("stamp").textContent =
    "Update terakhir: " + new Date(d.generated_at).toLocaleString("id-ID");
  populatePeriodSelect();
  render();
}

function load(){
  // 1) If data is embedded via data.js (works on file://), use it directly.
  if (window.PSI_DATA) {
    try { applyData(window.PSI_DATA); return; }
    catch(e){ console.error("Embedded data error:", e); }
  }
  // 2) Otherwise, fetch data.json (works when served via Vercel / HTTP).
  fetch("data.json?ts="+Date.now()).then(r=>r.json()).then(applyData).catch(e=>{
    document.getElementById("root").innerHTML =
      `<div class="empty"><b>Gagal memuat data dashboard.</b><br><br>` +
      `<small>${escapeHtml(e.message)}</small><br><br>` +
      `Pastikan <code>refresh.bat</code> sudah dijalankan dan file ` +
      `<code>public/data.js</code> serta <code>public/data.json</code> sudah ada di folder.</div>`;
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
  r.appendChild(renderKPIs());
  r.appendChild(renderRow2());
  r.appendChild(renderBankMatrix());
  r.appendChild(renderTrend());
  r.appendChild(renderCFSummary());
}

// ----- KPIs -----
function renderKPIs(){
  const D = DATA;
  const idx = D.periods.findIndex(p=>p.key===SELECTED_PERIOD);
  const p = D.periods[idx];
  const inflow = D.trend.inflow[idx];
  const outflow = D.trend.outflow[idx];
  const net = D.trend.net[idx];
  const ending = D.trend.ending[idx];
  // Compare vs previous month
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
  const div = el(`<div class="kpi-row"></div>`);
  div.appendChild(el(`<div class="kpi pos">
    <div class="lbl">Posisi Kas Akhir ${p.label_short}</div>
    <div class="val">${fmtBig(ending)}${trendBadge(ending, prevEnding)}</div>
    <div class="sub">Total saldo seluruh rekening bank</div></div>`));
  div.appendChild(el(`<div class="kpi pos">
    <div class="lbl">Uang Masuk - ${p.label_short}</div>
    <div class="val">${fmtBig(inflow)}</div>
    <div class="sub">Customer + Pinjaman + Lain-lain</div></div>`));
  div.appendChild(el(`<div class="kpi neg">
    <div class="lbl">Uang Keluar - ${p.label_short}</div>
    <div class="val">${fmtBig(outflow)}</div>
    <div class="sub">CAPEX + OPEX + Pinjaman + Biaya Bank</div></div>`));
  const netCls = net>=0 ? "pos" : "neg";
  div.appendChild(el(`<div class="kpi ${netCls}">
    <div class="lbl">Net (Masuk - Keluar) - ${p.label_short}</div>
    <div class="val">${fmtBig(net)}${trendBadge(net, prevNet)}</div>
    <div class="sub">${net>=0 ? "Surplus bulan ini" : "Defisit bulan ini"}</div></div>`));
  return div;
}

// ----- Row 2: Incoming + Outflow accordions -----
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
    <h2>Uang Masuk Dari Mana? <span class="pill">${escapeHtml(periodLbl)}</span></h2>
    <div class="body" id="incBody"></div></div>`);
  if(!data || !data.groups.length){
    card.querySelector("#incBody").innerHTML = `<div class="empty">Tidak ada data untuk bulan ini.</div>`;
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
        <div class="muted" style="margin-bottom:6px;font-size:11.5px">${g.party_count} pihak (top ${g.parties.length}):</div>
        ${partyRows || '<div class="muted">Tidak ada detail.</div>'}
      </div>
    </div>`;
  }).join("");
  card.querySelector("#incBody").innerHTML = `
    <div class="flow">${groups}</div>
    <div style="margin-top:14px;padding:12px 16px;background:var(--pos-bg);border-radius:9px;font-weight:700;color:var(--pos);display:flex;justify-content:space-between">
      <span>TOTAL UANG MASUK</span><span>${fmtBig(total)}</span>
    </div>`;
  return card;
}

function renderOutflow(){
  const D = DATA;
  const data = D.outflow_drill[SELECTED_PERIOD];
  const periodLbl = D.periods.find(p=>p.key===SELECTED_PERIOD).label_long;
  const card = el(`<div class="card">
    <h2>Uang Keluar Ke Mana? <span class="pill">${escapeHtml(periodLbl)}</span></h2>
    <div class="body" id="outBody"></div></div>`);
  if(!data || !data.buckets.length){
    card.querySelector("#outBody").innerHTML = `<div class="empty">Tidak ada data untuk bulan ini.</div>`;
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
          <span class="sname">${escapeHtml(s.label)}<span class="scount">(${s.party_count} pihak)</span></span>
          <span class="samt amount neg">${fmtBig(s.amount)}</span>
        </div>
        <div class="parties">
          ${partyRows || '<div class="muted">Tidak ada detail.</div>'}
        </div>
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
      <span>TOTAL UANG KELUAR</span><span>${fmtBig(total)}</span>
    </div>`;
  return card;
}

function toggleFGroup(g){ g.classList.toggle("open"); }
function toggleSub(s){ s.classList.toggle("open"); }
window.toggleFGroup = toggleFGroup;
window.toggleSub = toggleSub;

// ----- Bank Position Matrix -----
function renderBankMatrix(){
  const D = DATA;
  const m = D.bank_position_matrix;
  const div = FORMATS[CUR].div;
  const card = el(`<div class="card">
    <h2>Posisi Kas di Tiap Bank (per akhir bulan)</h2>
    <div class="scroll-x" id="bmBody"></div></div>`);
  // Heatmap calc
  const allEndings = m.banks.flatMap(b=>m.periods.map(p=>m.data[b][p].ending));
  const maxAbs = Math.max(...allEndings.map(Math.abs), 1);
  const heatColor = (v)=>{
    if(Math.abs(v) < 1) return "#fafbfd";
    const intensity = Math.min(Math.abs(v)/maxAbs, 1);
    if(v>0){
      const a = (0.10 + intensity*0.55).toFixed(2);
      return `rgba(10,135,84,${a})`;
    } else {
      const a = (0.10 + intensity*0.55).toFixed(2);
      return `rgba(192,57,43,${a})`;
    }
  };
  const periodHeaders = D.periods.map(p=>`<th>${escapeHtml(p.label_long)}</th>`).join("");
  const rows = m.banks.map(b=>{
    const cells = D.periods.map(p=>{
      const v = m.data[b][p.key].ending;
      const ch = m.data[b][p.key].change;
      const ch_str = ch ? ` <span class="muted" style="font-size:10.5px">(Δ ${fmtCompact(ch)})</span>` : "";
      return `<td><span class="heat" style="background:${heatColor(v)}">${fmtBig(v)}${ch_str}</span></td>`;
    }).join("");
    return `<tr><td>${escapeHtml(b)}</td>${cells}</tr>`;
  }).join("");
  const totalRow = D.periods.map(p=>`<td>${fmtBig(m.totals[p.key])}</td>`).join("");
  card.querySelector("#bmBody").innerHTML = `
    <table class="bank-matrix">
      <thead><tr><th>Bank</th>${periodHeaders}</tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr class="total"><td>TOTAL POSISI KAS</td>${totalRow}</tr></tfoot>
    </table>`;
  return card;
}

// ----- Trend chart -----
function renderTrend(){
  const D = DATA;
  const card = el(`<div class="card">
    <h2>Tren Arus Kas</h2>
    <div class="legend-mini">
      <span><i style="background:#0a8754"></i>Uang Masuk</span>
      <span><i style="background:#c0392b"></i>Uang Keluar</span>
      <span><i style="background:#1f3864"></i>Net</span>
      <span><i style="background:#f0a020"></i>Posisi Kas Akhir</span>
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
        {label:"Uang Masuk", data:D.trend.inflow.map(v=>v/div),
         backgroundColor:"#0a875499", borderColor:"#0a8754", borderWidth:1, order:2},
        {label:"Uang Keluar", data:D.trend.outflow.map(v=>v/div),
         backgroundColor:"#c0392b99", borderColor:"#c0392b", borderWidth:1, order:2},
        {label:"Net", type:"line", data:D.trend.net.map(v=>v/div),
         borderColor:"#1f3864", backgroundColor:"#1f386422", borderWidth:2.5, tension:.25, pointRadius:5, order:1},
        {label:"Posisi Kas Akhir", type:"line", data:D.trend.ending.map(v=>v/div),
         borderColor:"#f0a020", borderWidth:2.5, tension:.25, pointRadius:5, borderDash:[4,3], order:1},
      ]},
      options:{
        responsive:true, maintainAspectRatio:false,
        plugins:{
          legend:{display:false},
          tooltip:{callbacks:{label:(c)=>` ${c.dataset.label}: ${FORMATS[CUR].label} ${c.parsed.y.toLocaleString("en-US",{maximumFractionDigits:0})}`}}
        },
        scales:{y:{ticks:{callback:(v)=>fmtCompact(v*div)}}}
      }
    });
  },10);
  return card;
}

// ----- CF Summary detail (collapsible) -----
function renderCFSummary(){
  const D = DATA;
  const card = el(`<div class="card">
    <h2>Cash Flow Summary - Detail
      <button class="collapse-btn" id="cfToggle">Tampilkan Detail</button>
    </h2>
    <div class="scroll-x hidden" id="cf_body"></div></div>`);
  card.querySelector("#cfToggle").onclick = (e) => {
    const body = card.querySelector("#cf_body");
    body.classList.toggle("hidden");
    e.target.textContent = body.classList.contains("hidden") ? "Tampilkan Detail" : "Sembunyikan";
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

// ----- Currency toggle -----
document.getElementById("curgrp").addEventListener("click", (e)=>{
  const b = e.target.closest("button"); if(!b) return;
  CUR = b.dataset.cur;
  localStorage.setItem("psi_cur", CUR);
  document.querySelectorAll("#curgrp button").forEach(x=>x.classList.toggle("active", x.dataset.cur===CUR));
  if(DATA) render();
});
document.querySelectorAll("#curgrp button").forEach(x=>x.classList.toggle("active", x.dataset.cur===CUR));
load();
