// Threads CMS v2 — dashboard logic
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
let accounts = [], curFilter = "", uploads = [], curPage = "dashboard";

function toast(msg, kind="") { const t=$("#toast"); t.textContent=msg; t.className="show "+kind; setTimeout(()=>t.className="",3000); }
async function api(path, opts) { const r=await fetch(path,opts); const j=await r.json(); if(!r.ok||j.error) throw new Error(j.error||("HTTP "+r.status)); return j; }
function esc(s){ return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function fmtNum(n){ n=n||0; if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'K'; return ''+n; }
function curAccount(){ return $("#global-account").value; }

// ── THEME ──
function initTheme(){
  const saved = localStorage.getItem("cms-theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  $("#theme-btn").textContent = saved==="dark" ? "🌙" : "☀️";
}
$("#theme-btn").addEventListener("click", ()=>{
  const cur = document.documentElement.getAttribute("data-theme");
  const next = cur==="dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("cms-theme", next);
  $("#theme-btn").textContent = next==="dark" ? "🌙" : "☀️";
  if(curPage==="dashboard") loadDashboard();  // repaint chart warna
});

// ── NAV ──
function gotoPage(page){
  curPage = page;
  $$(".nav-item").forEach(n=>n.classList.toggle("on", n.dataset.page===page));
  $$(".page").forEach(p=>p.classList.remove("on"));
  $("#page-"+page).classList.add("on");
  $("#crumb-page").textContent = {dashboard:"Dashboard",analytics:"Analytics",compose:"Compose",autopost:"Auto-Post",persona:"Persona AI",akun:"Kelola Akun"}[page]||page;
  if(page==="dashboard") loadDashboard();
  if(page==="compose") loadPosts();
  if(page==="persona") loadPersonas();
  if(page==="autopost") loadAutopost();
  if(page==="akun") loadAkun();
}
$$(".nav-item[data-page]").forEach(n=> n.addEventListener("click", ()=>gotoPage(n.dataset.page)));

// ── ACCOUNTS ──
function fillAccountSelects(){
  const opts = accounts.map(a=>`<option value="${a.handle}">@${a.handle}</option>`).join("");
  ["#global-account","#p-handle","#ap-handle"].forEach(s=>{ if($(s)) $(s).innerHTML=opts; });
  // sidebar account list
  $("#side-accounts").innerHTML = accounts.map(a=>
    `<div class="nav-acc" data-acc="${a.handle}"><span class="dot"></span> @${esc(a.handle)}</div>`).join("");
  $$(".nav-acc[data-acc]").forEach(el=> el.addEventListener("click", ()=>{
    $("#global-account").value = el.dataset.acc;
    $$(".nav-acc").forEach(x=>x.classList.toggle("on", x===el));
    if(curPage==="dashboard") loadDashboard();
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
  loadUpcoming(h);
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
    {ico:"👁", val:t.views, lbl:"Total Views"},
    {ico:"❤️", val:t.likes, lbl:"Total Likes"},
    {ico:"💬", val:t.replies, lbl:"Total Replies"},
    {ico:"🔁", val:t.reposts, lbl:"Total Reposts"},
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
async function loadUpcoming(h){
  try {
    const posts = await api("/api/posts?status=scheduled&handle="+h);
    const up = posts.filter(p=>p.scheduled_at).sort((a,b)=>a.scheduled_at.localeCompare(b.scheduled_at)).slice(0,5);
    if(!up.length){ $("#dash-upcoming").innerHTML='<div class="empty">gak ada jadwal</div>'; return; }
    $("#dash-upcoming").innerHTML = up.map(p=>`<div class="post" style="margin-bottom:8px;padding:11px">
      <div class="top"><span class="handle">${p.source==='auto'?'<span class="tag auto">auto</span> ':''}${new Date(p.scheduled_at).toLocaleString("id-ID",{weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</span></div>
      <div class="txt" style="max-height:44px">${esc(p.text.slice(0,90))}...</div>
    </div>`).join("");
  } catch(e){ $("#dash-upcoming").innerHTML='<div class="empty">—</div>'; }
}

// ── CHART (SVG area) ──
function renderChart(sel, posts, key){
  const el = $(sel);
  const data = (posts||[]).map(p=>p[key]||0).reverse();
  if(!data.length || data.every(v=>v===0)){ el.innerHTML='<div class="empty">belum ada data '+key+'<br><span class="hint">metrik muncul beberapa jam setelah post</span></div>'; return; }
  const w=600,h=200,pad=10;
  const max=Math.max(...data,1);
  const step = data.length>1 ? (w-pad*2)/(data.length-1) : 0;
  const pts = data.map((v,i)=>[pad+i*step, h-pad-(v/max)*(h-pad*2)]);
  const line = pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const area = line+` L${pad+(data.length-1)*step} ${h-pad} L${pad} ${h-pad} Z`;
  el.innerHTML = `<svg class="chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--accent)" stop-opacity=".35"/>
      <stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>
    <path d="${area}" fill="url(#ag)"/>
    <path d="${line}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round"/>
    ${pts.map(p=>`<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3" fill="var(--accent)"/>`).join('')}
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

// ══════════ ANALYTICS ══════════
$("#btn-ana-load").addEventListener("click", async ()=>{
  const h = curAccount();
  $("#ana-note").textContent="(ambil metrik, 20-40 detik)";
  $("#ana-stats").innerHTML = statCards({views:0,likes:0,replies:0,reposts:0}, true);
  $("#ana-chart").innerHTML='<div class="empty"><span class="spin"></span></div>';
  $("#ana-donut").innerHTML='<div class="empty"><span class="spin"></span></div>';
  $("#ana-top").innerHTML='<div class="empty"><span class="spin"></span> ngitung...</div>';
  try {
    const a = await api(`/api/analytics?handle=${h}&limit=20`);
    $("#ana-note").textContent = `${a.posts_analyzed} post · eng.rate ${a.engagement_rate}% · avg ${fmtNum(a.avg_views)} views`;
    $("#ana-stats").innerHTML = statCards(a.totals);
    renderChart("#ana-chart", a.all_posts||[], "views");
    renderDonut("#ana-donut", a.totals);
    if(!a.top_posts||!a.top_posts.length){ $("#ana-top").innerHTML='<div class="empty">belum ada post</div>'; return; }
    $("#ana-top").innerHTML = a.top_posts.map((p,i)=>`<div class="post">
      <div class="top"><span class="handle">#${i+1} · ${fmtNum(p.views)} views</span>
        <span class="meta">${p.timestamp?new Date(p.timestamp).toLocaleDateString("id-ID"):""}</span></div>
      <div class="txt">${esc(p.text)}</div>
      <div class="ins" style="margin-top:8px;gap:8px">
        <div class="box" style="min-width:56px;padding:5px 9px"><div class="n" style="font-size:13px">${fmtNum(p.likes)}</div><div class="l">❤️</div></div>
        <div class="box" style="min-width:56px;padding:5px 9px"><div class="n" style="font-size:13px">${fmtNum(p.replies)}</div><div class="l">💬</div></div>
        <div class="box" style="min-width:56px;padding:5px 9px"><div class="n" style="font-size:13px">${fmtNum(p.reposts)}</div><div class="l">🔁</div></div>
      </div>
      ${p.permalink?`<div class="actions"><a href="${p.permalink}" target="_blank"><button class="sm ghost">Buka</button></a></div>`:""}
    </div>`).join("");
  } catch(e){
    $("#ana-note").textContent="";
    $("#ana-stats").innerHTML = statCards({views:0,likes:0,replies:0,reposts:0});
    $("#ana-top").innerHTML=`<div class="empty">error: ${esc(e.message)}</div>`;
    $("#ana-chart").innerHTML='<div class="empty">—</div>'; $("#ana-donut").innerHTML='<div class="empty">—</div>';
  }
});

// ══════════ COMPOSE ══════════
async function loadGenPersonas(){
  try {
    const ps = await api("/api/personas?handle="+curAccount());
    $("#gen-persona").innerHTML='<option value="">— tanpa persona —</option>'+ps.map(p=>`<option value="${p.id}" ${p.is_default?"selected":""}>${esc(p.name)}</option>`).join("");
  } catch(e){}
}
function updateCount(){ const t=$("#text").value; const parts=t.split(/\n\s*---\s*\n/).filter(p=>p.trim()).length||1; $("#charc").textContent=`${t.length} karakter · ${parts} part`; }
$("#text").addEventListener("input", updateCount);
$("#btn-gen").addEventListener("click", async ()=>{
  const topic=$("#gen-topic").value.trim(); if(!topic) return toast("isi topik","err");
  const btn=$("#btn-gen"), old=btn.innerHTML; btn.disabled=true; btn.innerHTML='<span class="spin"></span> generating...';
  try {
    const p={topic, num_parts:parseInt($("#gen-parts").value)||1};
    const pid=$("#gen-persona").value; if(pid) p.persona_id=parseInt(pid); else p.lang="id";
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
window.rmUpload=i=>{ uploads.splice(i,1); renderThumbs(); };
$("#btn-save").addEventListener("click", async ()=>{
  const handle=curAccount(), text=$("#text").value.trim();
  if(!text) return toast("teks kosong","err");
  const schedRaw=$("#sched").value; const btn=$("#btn-save"); btn.disabled=true;
  try {
    const p={handle,text}; if(schedRaw) p.scheduled_at=schedRaw;
    const ssL=$("#ss-link").value.trim(); if(ssL){ p.softsell_link=ssL; p.softsell_text=$("#ss-text").value.trim(); }
    const j=await api("/api/post",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
    for(let i=0;i<uploads.length;i++){ await api("/api/post/attach",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:j.id,part_index:i,r2_key:uploads[i].r2_key,public_url:uploads[i].public_url,filename:uploads[i].filename})}); }
    toast(schedRaw?"terjadwal ✓":"draft ✓","ok"); clearForm(); loadPosts();
  } catch(e){ toast("gagal: "+e.message,"err"); }
  finally{ btn.disabled=false; }
});
$("#btn-clear").addEventListener("click", clearForm);
function clearForm(){ ["#text","#sched","#gen-topic","#gen-brief","#ss-link","#ss-text"].forEach(s=>$(s).value=""); uploads=[]; renderThumbs(); updateCount(); }
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
  const imgs=(p.media||[]).map(m=>`<img src="${m.public_url}">`).join("");
  const when=p.scheduled_at?new Date(p.scheduled_at).toLocaleString("id-ID"):"";
  const posted=p.posted_at?new Date(p.posted_at).toLocaleString("id-ID"):"";
  return `<div class="post"><div class="top">
    <span class="handle">@${p.handle} ${p.source==="auto"?'<span class="tag auto">auto</span>':''}</span><span class="st ${p.status}">${p.status}</span></div>
    <div class="txt">${esc(p.text)}</div>
    ${imgs?`<div class="mini-img">${imgs}</div>`:""}
    ${p.softsell_link?`<div class="meta" style="color:var(--gold)">🔗 ${esc(p.softsell_link)}</div>`:""}
    <div class="meta">${when?`⏰ ${when}`:""} ${posted?`✅ ${posted}`:""}${p.error?`<br>⚠ ${esc(p.error)}`:""}</div>
    <div class="actions">
      ${p.status!=="posted"?`<button class="sm" onclick="pub('${p.id}')">Post sekarang</button>`:""}
      <button class="sm danger" onclick="del('${p.id}')">Hapus</button></div></div>`;
}
window.pub=async id=>{ if(!confirm("Post sekarang ke Threads?"))return; toast("posting..."); try{ await api("/api/post/publish",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})}); toast("terkirim ✓","ok"); loadPosts(); }catch(e){ toast("gagal: "+e.message,"err"); loadPosts(); } };
window.del=async id=>{ if(!confirm("Hapus post?"))return; try{ await api("/api/post/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})}); toast("dihapus","ok"); loadPosts(); }catch(e){ toast("gagal: "+e.message,"err"); } };

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
async function loadAutopostPersonas(){ try{ const ps=await api("/api/personas?handle="+curAccount()); $("#ap-persona").innerHTML='<option value="">— tanpa persona —</option>'+ps.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join(""); }catch(e){} }
async function loadAutopost(){
  const h=curAccount(); if(!h)return;
  $("#ap-preview-box").innerHTML='<div class="empty">klik Preview buat contoh</div>';
  await loadAutopostPersonas();
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
  try{ const j=await api("/api/autopost/generate_now",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({handle:curAccount(),num_parts:parseInt($("#ap-pmax").value)||2})}); $("#ap-preview-box").innerHTML=`<div class="post"><div class="top"><span class="handle">niche: ${esc(j.niche)}</span><span class="tag">preview</span></div><div class="txt">${esc(j.text)}</div></div>`; toast("preview ✓","ok"); }
  catch(e){ $("#ap-preview-box").innerHTML=`<div class="empty">error: ${e.message}</div>`; toast("gagal: "+e.message,"err"); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
});

// ══════════ AKUN ══════════
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

// ══════════ INIT ══════════
(async()=>{
  initTheme();
  try{ await loadAccounts(); await loadGenPersonas(); }catch(e){ toast("gagal load akun: "+e.message,"err"); }
  updateCount();
  gotoPage("dashboard");
})();
