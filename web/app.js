// Threads CMS v2 — dashboard logic
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
let accounts = [], curFilter = "", uploads = [], curPage = "dashboard";

function toast(msg, kind="") { const t=$("#toast"); t.textContent=msg; t.className="show "+kind; setTimeout(()=>t.className="",3000); }
async function api(path, opts) { const r=await fetch(path,opts); const j=await r.json(); if(!r.ok||j.error) throw new Error(j.error||("HTTP "+r.status)); return j; }
function esc(s){ return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function fmtNum(n){ n=n||0; if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'K'; return ''+n; }
function curAccount(){ return $("#global-account").value; }

// ── SVG icons (monoline, Lucide-style) ──
const ICO = {
  eye:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>',
  heart:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 12 5 5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/></svg>',
  chat:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z"/></svg>',
  repeat:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/></svg>',
  quote:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21c3 0 7-1 7-8V5a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h4"/><path d="M13 21c3 0 7-1 7-8V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h4"/></svg>',
};

// ── THEME ──
const MOON='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>';
const SUN='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
function initTheme(){
  const saved = localStorage.getItem("cms-theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  $("#theme-btn").innerHTML = saved==="dark" ? MOON : SUN;
}
$("#theme-btn").addEventListener("click", ()=>{
  const cur = document.documentElement.getAttribute("data-theme");
  const next = cur==="dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("cms-theme", next);
  $("#theme-btn").innerHTML = next==="dark" ? MOON : SUN;
  if(curPage==="dashboard") loadDashboard();
});

// ── NAV ──
function gotoPage(page){
  curPage = page;
  $$(".nav-item").forEach(n=>n.classList.toggle("on", n.dataset.page===page));
  $$(".page").forEach(p=>p.classList.remove("on"));
  $("#page-"+page).classList.add("on");
  $("#crumb-page").textContent = {dashboard:"Dashboard",analytics:"Analytics",compose:"Compose",instant:"Instant Content",autopost:"Auto-Post",persona:"Persona AI",akun:"Kelola Akun",hooks:"Hook Library"}[page]||page;
  if(page==="dashboard") loadDashboard();
  if(page==="compose") loadPosts();
  if(page==="instant") loadInstant();
  if(page==="persona") loadPersonas();
  if(page==="autopost") loadAutopost();
  if(page==="akun") loadAkun();
  if(page==="analytics") loadAnalyticsOverview();
  if(page==="hooks") loadHooks();
}
$$(".nav-item[data-page]").forEach(n=> n.addEventListener("click", ()=>gotoPage(n.dataset.page)));

// ── ACCOUNTS ──
function fillAccountSelects(){
  const opts = accounts.map(a=>`<option value="${a.handle}">@${a.handle}</option>`).join("");
  ["#global-account","#ap-handle"].forEach(s=>{ if($(s)) $(s).innerHTML=opts; });
  // sidebar account list
  $("#side-accounts").innerHTML = accounts.map(a=>
    `<div class="nav-acc" data-acc="${a.handle}"><span class="dot"></span> @${esc(a.handle)}</div>`).join("");
  $$(".nav-acc[data-acc]").forEach(el=> el.addEventListener("click", ()=>{
    $("#global-account").value = el.dataset.acc;
    $$(".nav-acc").forEach(x=>x.classList.toggle("on", x===el));
    // samain perilaku sama dropdown #global-account: reload semua halaman yg account-scoped
    $("#global-account").dispatchEvent(new Event("change"));
  }));
}
async function loadAccounts(){
  accounts = await api("/api/accounts");
  fillAccountSelects();
  $("#status-txt").textContent = accounts.length+" akun · online";
}
$("#global-account").addEventListener("change", ()=>{
  loadGenPersonas();
  if(curPage==="dashboard") loadDashboard();
  if(curPage==="autopost") loadAutopost();
  if(curPage==="persona") loadPersonas();
});

// ══════════ DASHBOARD ══════════
async function loadDashboard(){
  const h = curAccount();
  if(!h) return;
  $("#dash-sub").textContent = "Ringkasan performa @"+h;
  // queue stats (instan, dari DB lokal)
  loadQueueStat(h);
  loadDashList(h);
  // analytics (dari Threads, agak lama)
  $("#dash-stats").innerHTML = statCards({views:0,likes:0,replies:0,reposts:0}, true);
  $("#dash-chart").innerHTML = '<div class="empty"><span class="spin"></span> ambil data Threads...</div>';
  $("#dash-donut").innerHTML = '<div class="empty"><span class="spin"></span></div>';
  try {
    const a = await api(`/api/analytics?handle=${h}&limit=15`);
    const t = a.totals;
    $("#dash-stats").innerHTML = statCards(t);
    renderChart("#dash-chart", a.all_posts||[], "views");
    renderDonut("#dash-donut", t);
  } catch(e){
    $("#dash-stats").innerHTML = statCards({views:0,likes:0,replies:0,reposts:0});
    $("#dash-chart").innerHTML = `<div class="empty">Data Threads gak kebaca buat @${h}<br><span class="hint">${esc(e.message.slice(0,80))}</span></div>`;
    $("#dash-donut").innerHTML = '<div class="empty">—</div>';
  }
}
function statCards(t, loading){
  const cards = [
    {ico:ICO.eye, val:t.views, lbl:"Total Views"},
    {ico:ICO.heart, val:t.likes, lbl:"Total Likes"},
    {ico:ICO.chat, val:t.replies, lbl:"Total Replies"},
    {ico:ICO.repeat, val:t.reposts, lbl:"Total Reposts"},
  ];
  return cards.map(c=>`<div class="stat">
    <div class="ico">${c.ico}</div>
    <div class="val">${loading?'<span class="spin"></span>':fmtNum(c.val)}</div>
    <div class="lbl">${c.lbl}</div>
  </div>`).join("");
}
async function loadQueueStat(h){
  try {
    const posts = await api("/api/posts?handle="+h);
    const by = {draft:0,scheduled:0,posted:0,failed:0};
    posts.forEach(p=> by[p.status]=(by[p.status]||0)+1);
    $("#dash-queue-stat").innerHTML = `<div class="ins">
      <div class="box"><div class="n">${by.scheduled}</div><div class="l">Terjadwal</div></div>
      <div class="box"><div class="n">${by.draft}</div><div class="l">Draft</div></div>
      <div class="box"><div class="n">${by.posted}</div><div class="l">Terkirim</div></div>
      <div class="box"><div class="n" style="color:var(--err)">${by.failed}</div><div class="l">Gagal</div></div>
    </div>`;
  } catch(e){ $("#dash-queue-stat").innerHTML='<div class="empty">—</div>'; }
}
async function loadDashList(h){
  try {
    const url = "/api/posts?handle="+encodeURIComponent(h)+(dashFilter?`&status=${dashFilter}`:"");
    const posts = await api(url);
    const el = $("#dash-list");
    if(!posts.length){ el.innerHTML='<div class="empty">belum ada post buat @'+esc(h)+'</div>'; return; }
    // terjadwal dulu (urut waktu), lalu sisanya terbaru
    const order = {scheduled:0, draft:1, posted:2, failed:3};
    posts.sort((a,b)=>{
      const oa=order[a.status]??9, ob=order[b.status]??9;
      if(oa!==ob) return oa-ob;
      return (b.scheduled_at||b.posted_at||"").localeCompare(a.scheduled_at||a.posted_at||"");
    });
    el.innerHTML = posts.map(renderPost).join("");
  } catch(e){ $("#dash-list").innerHTML=`<div class="empty">error: ${esc(e.message)}</div>`; }
}
let dashFilter = "";

// ── CHART (SVG area, gridlines + axis) ──
function renderChart(sel, posts, key){
  const el = $(sel);
  const data = (posts||[]).map(p=>p[key]||0).reverse();
  if(!data.length || data.every(v=>v===0)){
    el.innerHTML='<div class="empty" style="padding:60px 20px">Belum ada data '+key+'<br><span class="hint">metrik muncul beberapa jam setelah post tayang</span></div>';
    return;
  }
  const w=600,h=200,padL=38,padR=10,padT=12,padB=22;
  const max=Math.max(...data,1);
  const iw=w-padL-padR, ih=h-padT-padB;
  const step = data.length>1 ? iw/(data.length-1) : 0;
  const pts = data.map((v,i)=>[padL+i*step, padT+ih-(v/max)*ih]);
  const line = pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const area = line+` L${(padL+(data.length-1)*step).toFixed(1)} ${padT+ih} L${padL} ${padT+ih} Z`;
  // gridlines (4 levels)
  let grid='', ylab='';
  for(let g=0; g<=3; g++){
    const y = padT + (ih/3)*g;
    const val = Math.round(max - (max/3)*g);
    grid += `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${w-padR}" y2="${y.toFixed(1)}" stroke="var(--chart-grid)" stroke-width="1"/>`;
    ylab += `<text x="${padL-8}" y="${(y+3).toFixed(1)}" text-anchor="end" font-size="9" fill="var(--faint)" font-family="var(--mono)">${fmtNum(val)}</text>`;
  }
  el.innerHTML = `<svg class="chart" viewBox="0 0 ${w} ${h}">
    <defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--accent)" stop-opacity=".22"/>
      <stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>
    ${grid}${ylab}
    <path d="${area}" fill="url(#ag)"/>
    <path d="${line}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    ${pts.map(p=>`<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="2.5" fill="var(--bg)" stroke="var(--accent)" stroke-width="1.5"/>`).join('')}
  </svg>`;
}
// ── DONUT (SVG) ──
function renderDonut(sel, t){
  const el = $(sel);
  const parts = [
    {lbl:"Likes", v:t.likes||0, c:"#ff5c8a"},
    {lbl:"Replies", v:t.replies||0, c:"var(--accent)"},
    {lbl:"Reposts", v:t.reposts||0, c:"var(--ok)"},
    {lbl:"Quotes", v:t.quotes||0, c:"var(--gold)"},
  ];
  const total = parts.reduce((s,p)=>s+p.v,0);
  if(!total){ el.innerHTML='<div class="empty">belum ada engagement</div>'; return; }
  const R=54, C=2*Math.PI*R; let off=0;
  const segs = parts.filter(p=>p.v>0).map(p=>{
    const frac=p.v/total, len=frac*C;
    const s=`<circle cx="70" cy="70" r="${R}" fill="none" stroke="${p.c}" stroke-width="18"
      stroke-dasharray="${len.toFixed(2)} ${(C-len).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}" transform="rotate(-90 70 70)"/>`;
    off+=len; return s;
  }).join("");
  el.innerHTML = `<div style="display:flex; align-items:center; gap:20px; flex-wrap:wrap">
    <svg width="140" height="140" viewBox="0 0 140 140">${segs}
      <text x="70" y="66" text-anchor="middle" font-size="20" font-weight="700" fill="var(--fg)">${fmtNum(total)}</text>
      <text x="70" y="84" text-anchor="middle" font-size="10" fill="var(--muted)">total eng.</text></svg>
    <div class="donut-legend">${parts.map(p=>`<div class="li"><span class="sw" style="background:${p.c}"></span>${p.lbl}<span class="v">${fmtNum(p.v)}</span></div>`).join("")}</div>
  </div>`;
}

// ══════════ ANALYTICS (overview semua akun, snapshot-based) ══════════
// Palet serasi (1 famili: teal -> cyan -> biru -> indigo -> ungu -> pink).
// Tiap warna punya pasangan gradient [terang, gelap] biar bar punya depth.
const ANA_GRAD = [
  ["#2dd4a7","#13a07a"], // teal (juara)
  ["#38bdf8","#1d7fd1"], // cyan
  ["#818cf8","#5457e0"], // indigo
  ["#c084fc","#9333ea"], // ungu
  ["#f472b6","#db4f91"], // pink
  ["#fbbf24","#e08b0f"], // gold
  ["#5eead4","#2bb3a0"], // mint
  ["#93c5fd","#5b93e8"], // biru muda
  ["#d8b4fe","#a855f7"], // lavender
  ["#fda4af","#f43f5e"], // rose
];

// state garis yg disembunyiin (per handle) + data terakhir buat re-render legend
const _anaHidden = new Set();
let _lastAna = null;

async function loadAnalyticsOverview(){
  $("#ana-updated").textContent = "memuat snapshot...";
  try {
    const j = await api("/api/analytics/overview");
    renderAnalytics(j);
  } catch(e){
    $("#ana-updated").textContent = "";
    $("#ana-rank").innerHTML = `<div class="empty">error: ${esc(e.message)}</div>`;
  }
}

function renderAnalytics(j){
  const snap = j.snapshot;
  if(!j.has_data || !snap){
    $("#ana-updated").textContent = "belum ada data";
    $("#ana-bar").innerHTML = '<div class="empty" style="padding:50px 20px">Belum ada snapshot<br><span class="hint">klik Update Data buat narik metrik semua akun</span></div>';
    $("#ana-rank").innerHTML = '<div class="empty">—</div>';
    $("#ana-stats").innerHTML = statCards({views:0,likes:0,replies:0,reposts:0});
    return;
  }
  const accs = (snap.accounts||[]).filter(a=>!a.error);
  const when = snap.collected_at ? new Date(snap.collected_at).toLocaleString("id-ID",{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}) : snap.date;
  $("#ana-updated").textContent = `terakhir update: ${when}`;
  const tot = accs.reduce((s,a)=>({views:s.views+(a.views||0),likes:s.likes+(a.likes||0),replies:s.replies+(a.replies||0),reposts:s.reposts+(a.reposts||0)}),{views:0,likes:0,replies:0,reposts:0});
  $("#ana-stats").innerHTML = statCards(tot);
  _lastAna = {trend: j.trend||[], accounts: snap.accounts||[]};
  renderMultiTrend("#ana-bar", j.trend||[], snap.accounts||[]);
  renderRankTable("#ana-rank", snap.accounts||[]);
}

// inisial akun buat badge/legend
function _initials(h){ return (h||"?").replace(/[^a-z0-9]/gi,"").slice(0,2).toUpperCase(); }

// ── MULTI-LINE TREND: tiap akun 1 garis views harian, legend toggle. Scalable 50 akun ──
function renderMultiTrend(sel, trend, accounts){
  const el = $(sel);
  // kumpulin semua handle dari accounts (urut views desc), warna per handle konsisten
  const handles = (accounts||[]).filter(a=>!a.error).sort((a,b)=>(b.views||0)-(a.views||0)).map(a=>a.handle);
  if(!handles.length){ el.innerHTML='<div class="empty">belum ada akun ber-data</div>'; return; }
  const colorOf = {}; handles.forEach((h,i)=>colorOf[h]=ANA_GRAD[i%ANA_GRAD.length][0]);

  // butuh min 2 titik tanggal buat garis
  if(!trend || trend.length<2){
    el.innerHTML = `<div class="empty" style="padding:44px 20px">Grafik tren butuh 2+ hari data<br>
      <span class="hint">sekarang baru ${trend?trend.length:0} titik. Tiap Update Data / auto jam 7 nambah 1 titik per hari</span></div>
      <div id="${sel.slice(1)}-legend" class="ana-legend"></div>`;
    renderLegend(sel, handles, colorOf);
    return;
  }

  const w=640, h=320, padL=48, padR=18, padT=18, padB=34;
  const iw=w-padL-padR, ih=h-padT-padB;
  // max views lintas semua akun+hari (buat skala Y), abaikan yg di-hide
  let max=1;
  trend.forEach(t=>handles.forEach(h=>{ if(!_anaHidden.has(h)) max=Math.max(max,(t.per_handle||{})[h]||0); }));
  const step = trend.length>1 ? iw/(trend.length-1) : 0;
  const xAt = i => padL + i*step;
  const yAt = v => padT + ih - (v/max)*ih;

  // gridlines + y-label
  let grid='',ylab='';
  for(let g=0;g<=4;g++){ const y=padT+(ih/4)*g; const val=Math.round(max-(max/4)*g);
    grid+=`<line x1="${padL}" y1="${y.toFixed(1)}" x2="${w-padR}" y2="${y.toFixed(1)}" stroke="var(--chart-grid)" stroke-width="1" stroke-dasharray="${g===4?'0':'2 4'}"/>`;
    ylab+=`<text x="${padL-10}" y="${(y+3).toFixed(1)}" text-anchor="end" font-size="10" fill="var(--faint)" font-family="var(--mono)">${fmtNum(val)}</text>`; }
  // x-label tanggal
  let xlab='';
  trend.forEach((t,i)=>{ const d=(t.date||"").slice(5);
    xlab+=`<text x="${xAt(i).toFixed(1)}" y="${(padT+ih+18).toFixed(1)}" text-anchor="middle" font-size="8.5" fill="var(--faint)">${d}</text>`; });

  // garis per akun (skip yg di-hide)
  let lines='', dots='';
  handles.forEach(h=>{
    if(_anaHidden.has(h)) return;
    const c=colorOf[h];
    const pts=trend.map((t,i)=>[xAt(i), yAt((t.per_handle||{})[h]||0)]);
    const d=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
    lines+=`<path d="${d}" fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" opacity="0.92"/>`;
    // titik + hover area per tanggal
    pts.forEach((p,i)=>{ const t=trend[i]; const v=(t.per_handle||{})[h]||0;
      dots+=`<g class="dot-g" data-h="${esc(h)}" data-d="${esc(t.date||"")}" data-v="${v}">
        <circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="8" fill="transparent"/>
        <circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="2.6" fill="var(--bg)" stroke="${c}" stroke-width="1.6"/></g>`; });
  });

  el.innerHTML = `<svg class="chart" viewBox="0 0 ${w} ${h}">${grid}${ylab}${xlab}${lines}${dots}</svg>
    <div class="chart-tip" style="display:none"></div>
    <div id="${sel.slice(1)}-legend" class="ana-legend"></div>`;
  wireTip(el, el.querySelectorAll(".dot-g"), (g)=>{
    const dt=new Date(g.dataset.d).toLocaleDateString("id-ID",{weekday:'short',day:'2-digit',month:'short'});
    return `<div class="tip-head"><span class="tip-dot" style="background:${colorOf[g.dataset.h]||'var(--accent)'};box-shadow:0 0 8px ${colorOf[g.dataset.h]||'var(--accent)'}"></span>@${g.dataset.h}</div>
      <div class="tip-big">${fmtNum(+g.dataset.v)} <span>views</span></div>
      <div class="tip-foot">${dt}</div>`;
  });
  renderLegend(sel, handles, colorOf);
}

// legend interaktif: klik buat toggle garis on/off
function renderLegend(sel, handles, colorOf){
  const lg = $(sel+"-legend"); if(!lg) return;
  lg.innerHTML = handles.map(h=>{
    const off=_anaHidden.has(h);
    return `<button class="leg-item${off?' off':''}" data-h="${esc(h)}">
      <span class="leg-dot" style="background:${colorOf[h]}"></span>@${esc(h)}</button>`;
  }).join("");
  lg.querySelectorAll(".leg-item").forEach(b=>{
    b.addEventListener("click",()=>{
      const h=b.dataset.h;
      if(_anaHidden.has(h)) _anaHidden.delete(h); else _anaHidden.add(h);
      // re-render pakai data terakhir yg disimpan
      if(_lastAna) renderMultiTrend(sel, _lastAna.trend, _lastAna.accounts);
    });
  });
}

// ── tooltip helper: muncul di ATAS elemen yg di-hover (center), gak ngikut cursor
//    biar gak nutup bar sebelah. Clamp ke dalam wadah. ──
function wireTip(wrap, nodes, htmlFn){
  const tip = wrap.querySelector(".chart-tip");
  if(!tip) return;
  const place = (g)=>{
    tip.innerHTML = htmlFn(g);
    tip.style.display = "block";
    const wr = wrap.getBoundingClientRect();
    const gr = g.getBoundingClientRect();
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    // center horizontal di atas elemen
    let x = (gr.left - wr.left) + gr.width/2 - tw/2;
    let y = (gr.top - wr.top) - th - 10;
    // clamp horizontal biar gak kepotong
    x = Math.max(4, Math.min(x, wr.width - tw - 4));
    // kalau mepet atas, taruh di bawah elemen
    if(y < 2) y = (gr.bottom - wr.top) + 10;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  };
  nodes.forEach(g=>{
    g.style.cursor="pointer";
    g.addEventListener("mouseenter",()=>place(g));
    g.addEventListener("mousemove",()=>place(g));
    g.addEventListener("mouseleave",()=>{ tip.style.display="none"; });
  });
}

// ── RANKING TABLE ──
function renderRankTable(sel, accs){
  const el=$(sel);
  if(!accs.length){ el.innerHTML='<div class="empty">belum ada akun</div>'; return; }
  const medal=r=>r===1?"🥇":r===2?"🥈":r===3?"🥉":("#"+r);
  const rows=accs.map(a=>{
    if(a.error){ return `<tr style="opacity:.55"><td>${medal(a.rank)}</td><td>@${esc(a.handle)}</td><td colspan="6" style="color:var(--err);font-size:12px">⚠ ${esc(a.error)}</td></tr>`; }
    return `<tr><td>${medal(a.rank)}</td><td>@${esc(a.handle)}</td><td>${fmtNum(a.views)}</td><td>${fmtNum(a.likes)}</td><td>${fmtNum(a.replies)}</td><td>${fmtNum(a.reposts)}</td><td>${a.engagement_rate}%</td><td>${fmtNum(a.avg_views)}</td></tr>`;
  }).join("");
  el.innerHTML=`<div style="overflow-x:auto"><table class="cmp-table" style="width:100%;border-collapse:collapse;font-size:13px">
    <thead><tr style="text-align:left;color:var(--muted);border-bottom:1px solid var(--border)">
      <th style="padding:8px 6px">#</th><th>Akun</th><th>Views</th><th>Likes</th><th>Replies</th><th>Reposts</th><th>Eng.Rate</th><th>Avg Views</th>
    </tr></thead><tbody>${rows}</tbody></table></div>`;
}

// ── tombol Update Data: narik fresh semua akun + simpan snapshot ──
$("#btn-ana-refresh").addEventListener("click", async ()=>{
  const btn=$("#btn-ana-refresh"),old=btn.innerHTML; btn.disabled=true;
  btn.innerHTML='<span class="spin"></span> narik metrik semua akun (1-2 menit)...';
  try {
    const j=await api("/api/analytics/refresh",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({limit:20})});
    renderAnalytics({has_data:true, snapshot:j.snapshot, trend:j.trend});
    toast("data terupdate ✓","ok");
  } catch(e){ toast("gagal: "+e.message,"err"); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
});

// ══════════ COMPOSE ══════════
async function loadGenPersonas(){
  try {
    const ps = await api("/api/personas?handle="+curAccount());
    // isi dropdown hidden (dipake logic generate)
    $("#gen-persona").innerHTML='<option value="">tanpa persona</option>'+ps.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join("");
    // render card picker
    const cont = $("#persona-cards");
    if(!ps.length){ cont.innerHTML='<div class="hint">belum ada persona buat @'+esc(curAccount())+'. Bikin dulu di menu Persona AI.</div>'; $("#gen-persona").value=""; return; }
    const def = ps.find(p=>p.is_default) || null;
    const cards = [`<button class="pcard${!def?' on':''}" data-pid="" onclick="pickPersona(this,'')">
        <div class="pc-name">✍️ Tanpa persona</div><div class="pc-desc">nulis bebas tanpa gaya khusus</div></button>`]
      .concat(ps.map(p=>`<button class="pcard${def&&p.id===def.id?' on':''}" data-pid="${p.id}" onclick="pickPersona(this,'${p.id}')">
        <div class="pc-name">${esc(p.name)}${p.is_default?' <span class="pc-def">default</span>':''}</div>
        <div class="pc-desc">${esc(p.description||'gaya '+p.name)}</div></button>`));
    cont.innerHTML = cards.join("");
    // set dropdown ke default kalau ada
    $("#gen-persona").value = def ? String(def.id) : "";
  } catch(e){ $("#persona-cards").innerHTML='<div class="hint">gagal muat persona</div>'; }
}
window.pickPersona=(el,pid)=>{
  $("#gen-persona").value = pid;
  document.querySelectorAll("#persona-cards .pcard").forEach(b=>b.classList.toggle("on", b===el));
};
function updateCount(){ const t=$("#text").value; const parts=t.split(/\n\s*---\s*\n/).filter(p=>p.trim()).length||1; $("#charc").textContent=`${t.length} karakter · ${parts} part`; }
$("#text").addEventListener("input", updateCount);
$("#btn-gen").addEventListener("click", async ()=>{
  const topic=$("#gen-topic").value.trim(); if(!topic) return toast("isi topik","err");
  const btn=$("#btn-gen"), old=btn.innerHTML; btn.disabled=true; btn.innerHTML='<span class="spin"></span> generating...';
  try {
    const p={topic, num_parts:parseInt($("#gen-parts").value)||1};
    const pid=$("#gen-persona").value; if(pid) p.persona_id=parseInt(pid);
    p.lang=$("#gen-lang").value||"id";  // dropdown bahasa selalu override (user milih sendiri)
    p.has_link=!!$("#ss-link").value.trim();
    const brief=$("#gen-brief").value.trim(); if(brief) p.brief=brief;
    const j=await api("/api/generate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
    $("#text").value=j.text; updateCount(); toast("digenerate ✓","ok");
  } catch(e){ toast("gagal: "+e.message,"err"); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
});
const drop=$("#drop"), fileInput=$("#file");
drop.addEventListener("click",()=>fileInput.click());
drop.addEventListener("dragover",e=>{e.preventDefault();drop.classList.add("over");});
drop.addEventListener("dragleave",()=>drop.classList.remove("over"));
drop.addEventListener("drop",e=>{e.preventDefault();drop.classList.remove("over");handleFiles(e.dataTransfer.files);});
fileInput.addEventListener("change",()=>handleFiles(fileInput.files));
async function handleFiles(files){
  for(const f of files){
    if(!f.type.startsWith("image/")){ toast("bukan gambar","err"); continue; }
    const fd=new FormData(); fd.append("file",f); toast("upload...");
    try{ const j=await api("/api/upload",{method:"POST",body:fd}); uploads.push({r2_key:j.r2_key,public_url:j.public_url,filename:j.filename}); renderThumbs(); toast("uploaded ✓","ok"); }
    catch(e){ toast("gagal: "+e.message,"err"); }
  }
}
function renderThumbs(){ $("#thumbs").innerHTML=uploads.map((u,i)=>`<div class="thumb"><img src="${u.public_url}"><div class="idx">#${i}</div><div class="x" onclick="rmUpload(${i})">×</div></div>`).join(""); }

// ── slot kedua: gambar produk buat REPLY soft-sell (1 gambar) ──
let ssUpload = null;
const dropSs=$("#drop-ss"), fileSs=$("#file-ss");
if(dropSs){
  dropSs.addEventListener("click",()=>fileSs.click());
  dropSs.addEventListener("dragover",e=>{e.preventDefault();dropSs.classList.add("over");});
  dropSs.addEventListener("dragleave",()=>dropSs.classList.remove("over"));
  dropSs.addEventListener("drop",e=>{e.preventDefault();dropSs.classList.remove("over");handleSsFile(e.dataTransfer.files);});
  fileSs.addEventListener("change",()=>handleSsFile(fileSs.files));
}
async function handleSsFile(files){
  const f=files[0]; if(!f) return;
  if(!f.type.startsWith("image/")){ toast("bukan gambar","err"); return; }
  const fd=new FormData(); fd.append("file",f); toast("upload gambar produk...");
  try{ const j=await api("/api/upload",{method:"POST",body:fd}); ssUpload={r2_key:j.r2_key,public_url:j.public_url,filename:j.filename}; renderSsThumb(); toast("gambar produk ✓","ok"); }
  catch(e){ toast("gagal: "+e.message,"err"); }
}
function renderSsThumb(){ $("#thumbs-ss").innerHTML=ssUpload?`<div class="thumb"><img src="${ssUpload.public_url}"><div class="idx">reply</div><div class="x" onclick="rmSsUpload()">×</div></div>`:""; }
window.rmSsUpload=()=>{ ssUpload=null; renderSsThumb(); };
window.rmUpload=i=>{ uploads.splice(i,1); renderThumbs(); };
$("#btn-save").addEventListener("click", async ()=>{
  const handle=curAccount(), text=$("#text").value.trim();
  if(!text) return toast("teks kosong","err");
  const schedRaw=$("#sched").value; const btn=$("#btn-save"); btn.disabled=true;
  try {
    const p={handle,text}; if(schedRaw) p.scheduled_at=schedRaw;
    const ssL=$("#ss-link").value.trim(); if(ssL){ p.softsell_link=ssL; p.softsell_text=$("#ss-text").value.trim(); }
    const j=await api("/api/post",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
    // gambar utas (part_index 0,1,2...)
    for(let i=0;i<uploads.length;i++){ await api("/api/post/attach",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:j.id,part_index:i,r2_key:uploads[i].r2_key,public_url:uploads[i].public_url,filename:uploads[i].filename})}); }
    // gambar reply soft-sell (part_index -1, dipisah dari utas)
    if(ssUpload){ await api("/api/post/attach",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:j.id,part_index:-1,r2_key:ssUpload.r2_key,public_url:ssUpload.public_url,filename:ssUpload.filename})}); }
    toast(schedRaw?"terjadwal ✓":"draft ✓","ok"); clearForm(); loadPosts();
  } catch(e){ toast("gagal: "+e.message,"err"); }
  finally{ btn.disabled=false; }
});
$("#btn-clear").addEventListener("click", clearForm);
function clearForm(){ ["#text","#sched","#gen-topic","#gen-brief","#ss-link","#ss-text"].forEach(s=>$(s).value=""); uploads=[]; ssUpload=null; renderThumbs(); renderSsThumb(); updateCount(); }
$("#filters").addEventListener("click", e=>{ if(e.target.tagName!=="BUTTON")return; curFilter=e.target.dataset.f; $$("#filters button").forEach(b=>b.classList.toggle("on",b===e.target)); loadPosts(); });
async function loadPosts(){
  try{
    const posts=await api("/api/posts"+(curFilter?`?status=${curFilter}`:""));
    const el=$("#list");
    if(!posts.length){ el.innerHTML='<div class="empty">belum ada post</div>'; return; }
    el.innerHTML=posts.map(renderPost).join("");
  }catch(e){ $("#list").innerHTML=`<div class="empty">error: ${e.message}</div>`; }
}
function renderPost(p){
  const media=(p.media||[]);
  const utasImgs=media.filter(m=>m.part_index>=0).map(m=>`<img src="${m.public_url}">`).join("");
  const ssImg=media.find(m=>m.part_index===-1);
  const when=p.scheduled_at?new Date(p.scheduled_at).toLocaleString("id-ID"):"";
  const posted=p.posted_at?new Date(p.posted_at).toLocaleString("id-ID"):"";
  // waktu jadwal bisa diklik buat reschedule (kecuali udah posted)
  const canEdit = p.status!=="posted";
  const schedChip = when
    ? (canEdit
        ? `<button class="sched-chip" onclick="editSched('${p.id}')" title="klik buat ganti jadwal">⏰ ${when} ✎</button>`
        : `⏰ ${when}`)
    : (canEdit
        ? `<button class="sched-chip empty-chip" onclick="editSched('${p.id}')">⏰ atur jadwal</button>`
        : "");
  return `<div class="post" id="post-${p.id}"><div class="top">
    <span class="handle">@${p.handle} ${p.source==="auto"?'<span class="tag auto">auto</span>':''}</span><span class="st ${p.status}">${p.status}</span></div>
    <div class="txt">${esc(p.text)}</div>
    ${utasImgs?`<div class="mini-img">${utasImgs}</div>`:""}
    ${p.softsell_link||ssImg?`<div class="meta" style="color:var(--gold)">🔗 reply soft-sell${ssImg?' + 🖼 gambar produk':''}${p.softsell_link?`<br>${esc(p.softsell_link)}`:''}</div>`:""}
    <div class="meta">${schedChip} ${posted?`✅ ${posted}`:""}${p.error?`<br>⚠ ${esc(p.error)}`:""}</div>
    <div class="sched-edit" id="sched-edit-${p.id}" style="display:none;margin-top:8px;align-items:center;gap:8px;flex-wrap:wrap">
      <input type="datetime-local" id="sched-in-${p.id}" value="${p.scheduled_at?_toLocalInput(p.scheduled_at):""}" style="width:auto;max-width:210px">
      <button class="sm" onclick="saveSched('${p.id}')">Simpan</button>
      <button class="sm ghost" onclick="cancelSched('${p.id}')">Batal</button>
      ${p.scheduled_at?`<button class="sm ghost" onclick="unsetSched('${p.id}')">Jadiin draft</button>`:""}
    </div>
    <div class="actions">
      ${p.status!=="posted"?`<button class="sm" onclick="pub('${p.id}')">Post sekarang</button>`:""}
      <button class="sm danger" onclick="del('${p.id}')">Hapus</button></div></div>`;
}
// ISO -> value datetime-local (YYYY-MM-DDTHH:MM) di waktu lokal
function _toLocalInput(iso){
  const d=new Date(iso); if(isNaN(d)) return "";
  const pad=n=>String(n).padStart(2,"0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
window.editSched=id=>{ const e=document.getElementById("sched-edit-"+id); if(e) e.style.display="flex"; };
window.cancelSched=id=>{ const e=document.getElementById("sched-edit-"+id); if(e) e.style.display="none"; };
window.saveSched=async id=>{
  const inp=document.getElementById("sched-in-"+id); if(!inp||!inp.value) return toast("pilih tanggal/jam dulu","err");
  try{ await api("/api/post/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id, scheduled_at:inp.value})});
    toast("jadwal diubah ✓","ok"); _refreshPostLists();
  }catch(e){ toast("gagal: "+e.message,"err"); }
};
window.unsetSched=async id=>{
  try{ await api("/api/post/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id, unset_time:true})});
    toast("jadi draft ✓","ok"); _refreshPostLists();
  }catch(e){ toast("gagal: "+e.message,"err"); }
};
// refresh daftar post di halaman yg lagi aktif (compose atau dashboard)
function _refreshPostLists(){
  const active = document.querySelector(".page.on");
  const id = active ? active.id : "";
  if(id === "page-dashboard"){ const h=curAccount(); if(h) loadDashList(h); }
  else loadPosts();
}
window.pub=async id=>{ if(!confirm("Post sekarang ke Threads?"))return; toast("posting..."); try{ await api("/api/post/publish",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})}); toast("terkirim ✓","ok"); _refreshPostLists(); }catch(e){ toast("gagal: "+e.message,"err"); _refreshPostLists(); } };
window.del=async id=>{ if(!confirm("Hapus post?"))return; try{ await api("/api/post/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})}); toast("dihapus","ok"); _refreshPostLists(); }catch(e){ toast("gagal: "+e.message,"err"); } };

// filter tab dashboard
(function(){
  const f = document.getElementById("dash-filters");
  if(f) f.addEventListener("click", e=>{
    if(e.target.tagName!=="BUTTON") return;
    dashFilter = e.target.dataset.f || "";
    f.querySelectorAll("button").forEach(b=>b.classList.toggle("on", b===e.target));
    const h=curAccount(); if(h) loadDashList(h);
  });
})();

// ══════════ INSTANT CONTENT ══════════
async function loadInstant(){
  // isi akun
  const accSel = $("#inst-account");
  if(accSel && !accSel.options.length){
    accSel.innerHTML = accounts.map(a=>`<option value="${a.handle}">@${a.handle}</option>`).join("");
  }
  // isi persona cards (universal, sama buat semua akun)
  try {
    const ps = await api("/api/personas");
    $("#inst-persona").innerHTML = ps.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join("");
    const cont = $("#inst-persona-cards");
    if(!ps.length){ cont.innerHTML='<div class="hint">belum ada persona. Bikin dulu di Persona AI.</div>'; return; }
    const def = ps.find(p=>p.is_default) || ps[0];
    cont.innerHTML = ps.map(p=>`<button class="pcard${p.id===def.id?' on':''}" data-pid="${p.id}" onclick="pickInstPersona(this,'${p.id}')">
      <div class="pc-name">${esc(p.name)}${p.is_default?' <span class="pc-def">default</span>':''}</div>
      <div class="pc-desc">${esc(p.description||'gaya '+p.name)}</div></button>`).join("");
    $("#inst-persona").value = String(def.id);
  } catch(e){ $("#inst-persona-cards").innerHTML='<div class="hint">gagal muat persona</div>'; }
}
window.pickInstPersona=(el,pid)=>{
  $("#inst-persona").value = pid;
  document.querySelectorAll("#inst-persona-cards .pcard").forEach(b=>b.classList.toggle("on", b===el));
};
function instPreview(text){
  const parts = text.split(/\n\s*---\s*\n/).map(s=>s.trim()).filter(Boolean);
  $("#inst-preview").innerHTML = parts.map((p,i)=>`<div class="post" style="margin-bottom:8px">
    <div class="top"><span class="handle">part ${i+1}/${parts.length}</span></div>
    <div class="txt">${esc(p)}</div></div>`).join("");
  $("#inst-charc").textContent = `${text.length} karakter · ${parts.length} part`;
}
$("#inst-text") && $("#inst-text").addEventListener("input", ()=>instPreview($("#inst-text").value));
$("#inst-gen") && $("#inst-gen").addEventListener("click", async ()=>{
  const pid=$("#inst-persona").value, title=$("#inst-title").value.trim();
  if(!pid) return toast("pilih persona dulu","err");
  if(!title) return toast("isi judul/ide dulu","err");
  const btn=$("#inst-gen"), old=btn.innerHTML; btn.disabled=true; btn.innerHTML='<span class="spin"></span> AI bikin konten...';
  try{
    const j=await api("/api/instant",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({persona_id:parseInt(pid), title, desc:$("#inst-desc").value.trim(), lang:$("#inst-lang").value, preview:true})});
    $("#inst-text").value=j.text; instPreview(j.text); toast("digenerate ✓","ok");
  }catch(e){ toast("gagal: "+e.message,"err"); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
});
async function instSubmit(scheduled){
  const text=$("#inst-text").value.trim(), handle=$("#inst-account").value;
  if(!text) return toast("generate / isi teks dulu","err");
  if(!handle) return toast("pilih akun","err");
  const sched = scheduled ? $("#inst-sched").value : "";
  try{
    // pakai endpoint /api/post biasa (teks udah jadi), source instant
    const p={handle, text, source:"instant"}; if(sched) p.scheduled_at=sched;
    const j=await api("/api/post",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
    if(scheduled && !sched){ // post sekarang
      await api("/api/post/publish",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:j.id})});
      toast("diposting ✓","ok");
    } else {
      toast(sched?"terjadwal ✓":"draft tersimpan ✓","ok");
    }
    $("#inst-title").value=""; $("#inst-desc").value=""; $("#inst-text").value=""; $("#inst-sched").value="";
    $("#inst-preview").innerHTML='<div class="empty">generate dulu buat lihat preview</div>'; $("#inst-charc").textContent="";
  }catch(e){ toast("gagal: "+e.message,"err"); }
}
$("#inst-save-draft") && $("#inst-save-draft").addEventListener("click", ()=>instSubmit(false));
$("#inst-post") && $("#inst-post").addEventListener("click", ()=>instSubmit(true));

// ══════════ PERSONA ══════════
async function loadPersonas(){
  try{
    const ps=await api("/api/personas"); const el=$("#persona-list");
    if(!ps.length){ el.innerHTML='<div class="empty">belum ada persona</div>'; return; }
    el.innerHTML=ps.map(p=>`<div class="persona-item">
      <div class="row" style="justify-content:space-between">
        <span class="pn">${esc(p.name)} <span class="tag">@${p.handle}</span> ${p.is_default?'<span class="tag def">default</span>':''}</span></div>
      <div class="pd">${esc(p.description||"")}</div>
      ${p.learned_style?`<div class="pstyle">📚 ${esc(p.learned_style.slice(0,150))}...</div>`:'<div class="pd" style="color:var(--warn)">belum belajar gaya</div>'}
      <div class="actions" style="margin-top:9px"><button class="sm ghost" onclick="editPersona(${p.id})">Edit</button><button class="sm danger" onclick="delPersona(${p.id})">Hapus</button></div>
    </div>`).join("");
  }catch(e){ $("#persona-list").innerHTML=`<div class="empty">error: ${e.message}</div>`; }
}
window.editPersona=async id=>{
  const p=await api("/api/persona?id="+id);
  $("#p-id").value=p.id; $("#p-handle").value=p.handle; $("#p-name").value=p.name; $("#p-desc").value=p.description||"";
  $("#p-lang").value=p.lang||"id"; $("#p-sys").value=p.system_prompt||""; $("#p-urls").value=(p.reference_urls||[]).join("\n");
  $("#p-default").checked=!!p.is_default; $("#pf-title").textContent="Edit Persona"; $("#learn-status").textContent="";
};
window.delPersona=async id=>{ if(!confirm("Hapus persona?"))return; await api("/api/persona/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})}); toast("dihapus","ok"); loadPersonas(); };
$("#btn-pnew").addEventListener("click",()=>{ ["#p-id","#p-name","#p-desc","#p-sys","#p-urls"].forEach(s=>$(s).value=""); $("#p-default").checked=false; $("#pf-title").textContent="Buat Persona"; $("#learn-status").textContent=""; });
function personaPayload(){ const urls=$("#p-urls").value.split("\n").map(s=>s.trim()).filter(Boolean); const p={handle:$("#p-handle").value,name:$("#p-name").value.trim(),description:$("#p-desc").value.trim(),system_prompt:$("#p-sys").value.trim(),lang:$("#p-lang").value,reference_urls:urls,is_default:$("#p-default").checked}; if($("#p-id").value)p.id=parseInt($("#p-id").value); return p; }
$("#btn-psave").addEventListener("click", async ()=>{ const p=personaPayload(); if(!p.name)return toast("isi nama","err"); try{ const j=await api("/api/persona/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)}); $("#p-id").value=j.id; $("#pf-title").textContent="Edit Persona"; toast("tersimpan ✓","ok"); loadPersonas(); loadGenPersonas(); }catch(e){ toast("gagal: "+e.message,"err"); } });
$("#btn-plearn").addEventListener("click", async ()=>{
  let pid=$("#p-id").value;
  if(!pid){ const p=personaPayload(); if(!p.name)return toast("isi nama & simpan dulu","err"); try{ const j=await api("/api/persona/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)}); pid=j.id; $("#p-id").value=pid; }catch(e){ return toast("gagal: "+e.message,"err"); } }
  const urls=$("#p-urls").value.split("\n").map(s=>s.trim()).filter(Boolean);
  const btn=$("#btn-plearn"),old=btn.innerHTML; btn.disabled=true; btn.innerHTML='<span class="spin"></span> belajar...';
  $("#learn-status").textContent="fetch link + analisis (20-40 detik)...";
  try{ const j=await api("/api/persona/learn",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:parseInt(pid),reference_urls:urls})}); $("#learn-status").innerHTML=`✅ belajar dari ${j.samples_found} post`; toast("gaya dipelajari ✓","ok"); loadPersonas(); }
  catch(e){ $("#learn-status").textContent="⚠ "+e.message; toast("gagal: "+e.message,"err"); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
});

// ══════════ AUTO-POST ══════════
async function loadAutopostHookCats(){
  const sel=$("#ap-hookcat"); if(!sel) return;
  try{
    if(!window._hookCatsFull){ window._hookCatsFull = await api("/api/hooks"); }
    sel.innerHTML='<option value="">— pilih kategori hook —</option>'+
      window._hookCatsFull.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join("");
  }catch(e){}
}
async function loadAutopostPersonas(){ try{ const ps=await api("/api/personas?handle="+curAccount()); $("#ap-persona").innerHTML='<option value="">— tanpa persona —</option>'+ps.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join(""); }catch(e){} }
async function loadAutopost(){
  const h=curAccount(); if(!h)return;
  $("#ap-preview-box").innerHTML='<div class="empty">klik Preview buat contoh</div>';
  await loadAutopostPersonas();
  await loadAutopostHookCats();
  try{
    const c=await api("/api/autopost?handle="+h);
    setApState(c.enabled); $("#ap-lang").value=c.lang||"id"; $("#ap-niches").value=(c.niches||[]).join("\n");
    $("#ap-styleurls").value=(c.style_urls||[]).join("\n"); $("#ap-guide").value=c.style_guide||"";
    $("#ap-ppd").value=c.posts_per_day||3; $("#ap-pmin").value=c.num_parts_min||1; $("#ap-pmax").value=c.num_parts_max||3;
    $("#ap-hours").value=(c.best_hours||[8,12,18,21]).join(", "); if(c.persona_id)$("#ap-persona").value=c.persona_id;
  }catch(e){ toast("gagal load: "+e.message,"err"); }
}
function setApState(on){ $("#ap-state-label").textContent=on?"ON ✅":"OFF"; $("#ap-state-label").style.color=on?"var(--ok)":"var(--muted)"; }
function apPayload(){ return {handle:curAccount(),lang:$("#ap-lang").value,niches:$("#ap-niches").value.split("\n").map(s=>s.trim()).filter(Boolean),style_urls:$("#ap-styleurls").value.split("\n").map(s=>s.trim()).filter(Boolean),style_guide:$("#ap-guide").value.trim(),posts_per_day:parseInt($("#ap-ppd").value)||3,num_parts_min:parseInt($("#ap-pmin").value)||1,num_parts_max:parseInt($("#ap-pmax").value)||3,best_hours:$("#ap-hours").value.split(",").map(s=>parseInt(s.trim())).filter(n=>!isNaN(n)&&n>=0&&n<=23),persona_id:$("#ap-persona").value?parseInt($("#ap-persona").value):null}; }
$("#ap-save").addEventListener("click", async ()=>{ const p=apPayload(); if(!p.niches.length)return toast("isi niche","err"); try{ await api("/api/autopost/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)}); toast("config tersimpan ✓","ok"); }catch(e){ toast("gagal: "+e.message,"err"); } });
$("#ap-toggle").addEventListener("click", async ()=>{ const p=apPayload(); if(!p.niches.length)return toast("isi niche dulu","err"); try{ await api("/api/autopost/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)}); const j=await api("/api/autopost/toggle",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({handle:curAccount()})}); setApState(j.enabled); toast(j.enabled?"Auto-post ON ✅":"Auto-post OFF","ok"); }catch(e){ toast("gagal: "+e.message,"err"); } });
$("#ap-preview").addEventListener("click", async ()=>{
  const p=apPayload(); if(!p.niches.length)return toast("isi niche","err");
  await api("/api/autopost/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)}).catch(()=>{});
  const btn=$("#ap-preview"),old=btn.innerHTML; btn.disabled=true; btn.innerHTML='<span class="spin"></span>';
  $("#ap-preview-box").innerHTML='<div class="empty"><span class="spin"></span> AI bikin utas...</div>';
  try{ const j=await api("/api/autopost/generate_now",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({handle:curAccount(),num_parts:parseInt($("#ap-pmax").value)||2,lang:$("#ap-lang").value})}); $("#ap-preview-box").innerHTML=`<div class="post"><div class="top"><span class="handle">niche: ${esc(j.niche)}</span><span class="tag">preview</span></div><div class="txt">${esc(j.text)}</div></div>`; toast("preview ✓","ok"); }
  catch(e){ $("#ap-preview-box").innerHTML=`<div class="empty">error: ${e.message}</div>`; toast("gagal: "+e.message,"err"); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
});
// inject contoh hook kategori ke panduan gaya (LLM belajar gaya ngawali)
$("#ap-hook-add").addEventListener("click", ()=>{
  const id=$("#ap-hookcat").value; if(!id) return toast("pilih kategori hook dulu","err");
  const cat=(window._hookCatsFull||[]).find(c=>c.id===id); if(!cat) return;
  const block=`\n\nGaya hook "${cat.name}" (${cat.desc}). Contoh pembuka:\n`+cat.examples.map(e=>"- "+e).join("\n");
  const ta=$("#ap-guide");
  if(ta.value.includes(`Gaya hook "${cat.name}"`)){ return toast("kategori ini udah dimasukin","err"); }
  ta.value=(ta.value.trimEnd()+block).trim();
  toast(`hook "${cat.name}" dimasukin ✓`,"ok");
});
async function loadAkun(){
  try{ const accs=await api("/api/accounts"); const el=$("#akun-list");
    if(!accs.length){ el.innerHTML='<div class="empty">belum ada akun</div>'; return; }
    el.innerHTML=accs.map(a=>`<div class="persona-item"><div class="row" style="justify-content:space-between"><span class="pn">@${esc(a.handle)}</span><button class="sm danger" onclick="delAkun('${esc(a.handle)}')">Hapus</button></div><div class="pd">${a.user_id?'id: '+esc(a.user_id):'terhubung'}</div></div>`).join("");
  }catch(e){ $("#akun-list").innerHTML=`<div class="empty">error: ${e.message}</div>`; }
}
$("#acc-oauth").addEventListener("click", ()=>{
  $("#oauth-status").innerHTML='buka popup login Meta... (kalau warning sertifikat, klik lanjut)';
  const before=accounts.map(a=>a.handle);
  const w=window.open("https://localhost:8456/oauth/start","oauth","width=600,height=720");
  let tries=0; const iv=setInterval(async ()=>{ tries++;
    try{ const accs=await api("/api/accounts"); const added=accs.map(a=>a.handle).filter(h=>!before.includes(h));
      if(added.length){ clearInterval(iv); $("#oauth-status").innerHTML=`✅ @${esc(added[0])} terhubung!`; toast("connected ✓","ok"); accounts=accs; fillAccountSelects(); loadAkun(); try{w&&w.close();}catch(e){} } }catch(e){}
    if(tries>150) clearInterval(iv);
  },2000);
});
$("#acc-add").addEventListener("click", async ()=>{
  const token=$("#acc-token").value.trim(); if(!token)return toast("paste token","err");
  const btn=$("#acc-add"),old=btn.innerHTML; btn.disabled=true; btn.innerHTML='<span class="spin"></span>';
  $("#acc-status").textContent="validasi...";
  try{ const j=await api("/api/account/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token,exchange:$("#acc-exchange").checked})}); $("#acc-status").innerHTML=`✅ @${esc(j.handle)} ditambah${j.exchanged?' (60 hari)':''}`; $("#acc-token").value=""; toast("ditambah ✓","ok"); await loadAccounts(); loadAkun(); }
  catch(e){ $("#acc-status").innerHTML=`⚠ ${esc(e.message)}`; toast("gagal: "+e.message,"err"); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
});
window.delAkun=async handle=>{ if(!confirm(`Hapus @${handle}?`))return; try{ await api("/api/account/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({handle})}); toast("dihapus","ok"); await loadAccounts(); loadAkun(); }catch(e){ toast("gagal: "+e.message,"err"); } };

// ══════════ HOOK LIBRARY ══════════
let hookCat = "";
async function loadHooks(){
  try {
    const cats = await api("/api/hooks");
    window._hookCats = {};
    cats.forEach(c=> window._hookCats[c.id]=c.name);
    $("#hook-cats").innerHTML = cats.map(c=>`<div class="persona-item hook-cat" data-cat="${c.id}" style="cursor:pointer">
      <div class="pn">${esc(c.name)} <span class="tag">${c.count} contoh</span></div>
      <div class="pd">${esc(c.desc)}</div>
      <div class="pstyle">${c.examples.map(e=>'• '+esc(e)).join("<br>")}</div>
    </div>`).join("");
  } catch(e){ $("#hook-cats").innerHTML=`<div class="empty">error: ${e.message}</div>`; }
}
// event delegation: klik di mana aja dalam kartu kategori tetap kepilih
$("#hook-cats").addEventListener("click", e=>{
  const card = e.target.closest(".hook-cat");
  if(!card) return;
  hookCat = card.dataset.cat;
  $$(".hook-cat").forEach(x=> x.style.borderColor = x===card ? "var(--accent)" : "");
  $("#hook-selected").innerHTML = `kategori: <b style="color:var(--accent)">${esc(window._hookCats[hookCat]||hookCat)}</b>`;
  $("#hook-gen").disabled = false;
});
$("#hook-gen").addEventListener("click", async ()=>{
  if(!hookCat) return toast("pilih kategori dulu","err");
  const topic = $("#hook-topic").value.trim();
  if(!topic) return toast("isi topik","err");
  const btn=$("#hook-gen"),old=btn.innerHTML; btn.disabled=true; btn.innerHTML='<span class="spin"></span> bikin hook...';
  $("#hook-result").innerHTML='<div class="empty"><span class="spin"></span></div>';
  try {
    const j = await api("/api/hooks/generate",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({category:hookCat, topic, lang:$("#hook-lang").value})});
    const lines = j.text.split("\n").map(l=>l.trim()).filter(l=>l && /\d/.test(l[0]||l));
    $("#hook-result").innerHTML = `<div class="post"><div class="top"><span class="handle">Hook baru</span><span class="tag auto">AI</span></div>` +
      lines.map(l=>{ const clean=l.replace(/^\d+[\.\)]\s*/,''); return `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid var(--border-subtle)"><span style="font-size:13px">${esc(clean)}</span><button class="sm ghost" onclick="useHook('${esc(clean).replace(/'/g,"\\'")}')">Pakai</button></div>`; }).join("") +
      `</div>`;
    toast("hook digenerate ✓","ok");
  } catch(e){ $("#hook-result").innerHTML=`<div class="empty">error: ${esc(e.message)}</div>`; toast("gagal: "+e.message,"err"); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
});
window.useHook = hook => {
  gotoPage("compose");
  const t=$("#text"); t.value = hook + "\n\n" + t.value; updateCount();
  toast("hook dimasukin ke Compose ✓","ok");
};

// ══════════ INIT ══════════
(async()=>{
  initTheme();
  try{ await loadAccounts(); await loadGenPersonas(); }catch(e){ toast("gagal load akun: "+e.message,"err"); }
  updateCount();
  gotoPage("dashboard");
})();
