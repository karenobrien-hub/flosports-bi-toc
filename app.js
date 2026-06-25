// FloSports BI Table of Contents — app.js v4
// TOC structure driven by Google Sheets:
// https://docs.google.com/spreadsheets/d/e/2PACX-1vQvGFskXEdcIoCADczZH2SREWOHJ6U6T8ZDwzgKJOk_q1yRyCUsOJD2buOtlmaPe1d8MIgZjpJqg_cC/pub?output=csv

const SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQvGFskXEdcIoCADczZH2SREWOHJ6U6T8ZDwzgKJOk_q1yRyCUsOJD2buOtlmaPe1d8MIgZjpJqg_cC/pub?output=csv";

const state = {
  data: null,
  category: "All", action: "All", usage: "All", search: "",
  reviewCategory: "All", reviewFlag: "All", reviewSearch: "",
};

const $ = (id) => document.querySelector(id);
const els = {
  sourceMeta:    $("#sourceMeta"),
  kpiStrip:      $("#kpiStrip"),
  healthStrip:   $("#healthStrip"),
  healthLegend:  $("#healthLegend"),
  areaCount:     $("#areaCount"),
  areaList:      $("#areaList"),
  categoryFilter:$("#categoryFilter"),
  actionFilter:  $("#actionFilter"),
  usageFilter:   $("#usageFilter"),
  searchInput:   $("#searchInput"),
  pageBars:      $("#pageBars"),
  staleBuckets:  $("#staleBuckets"),
  viewBuckets:   $("#viewBuckets"),
  tocAreaGrid:   $("#tocAreaGrid"),
  quickWins:     $("#quickWins"),
  resultCount:   $("#resultCount"),
  inventoryRows: $("#inventoryRows"),
  clearFilters:  $("#clearFilters"),
  reviewRows:    $("#reviewRows"),
  reviewCount:   $("#reviewCount"),
  reviewSearch:  $("#reviewSearch"),
  reviewCategoryFilter: $("#reviewCategoryFilter"),
  reviewFlagFilter:     $("#reviewFlagFilter"),
};

const nf = new Intl.NumberFormat("en-US");
function esc(v){ return String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;"); }
const fmt = v => nf.format(v??0);
const pct = v => `${Number(v??0).toFixed(1)}%`;

function actionCls(a){ a=String(a).toLowerCase(); if(a.includes("keep"))return"keep"; if(a.includes("merge"))return"merge"; if(a.includes("retire"))return"retire"; return""; }
function flagCls(f){ f=String(f).toLowerCase(); if(f.includes("stale"))return"stale"; if(f.includes("dup"))return"merge"; if(f.includes("noise")||f.includes("orphan"))return"retire"; return""; }
function usageCls(t){ return t==="High"?"keep":t==="Medium"?"document":t==="Low"?"stale":"retire"; }
function legendColor(cls){ return{"hs-keep":"var(--green)","hs-merge":"var(--plum)","hs-doc":"#8a9ea4","hs-triage":"var(--blue)","hs-review":"var(--amber)","hs-retire":"var(--red)"}[cls]||"#ccc"; }

// ── KPI strip ──────────────────────────────────────────────
function renderKpis(){
  const t = state.data.totals;
  const kpis = [
    ["Active Cards",  t.tocCards,           `cards with usage in 389-day window`],
    ["For Review",    t.forReviewCards,      `zero views · noise · orphan/shared`],
    ["Duplicates",    t.duplicateTitleCards, `same title living on multiple pages`],
  ];
  els.kpiStrip.innerHTML = kpis.map(([label,value,note])=>`
    <article class="kpi"><span>${esc(label)}</span><strong>${fmt(value)}</strong><small>${esc(note)}</small></article>`).join("");
}

// ── Health bar ─────────────────────────────────────────────
function renderHealthStrip(){
  const actions = state.data.actions;
  const total = actions.reduce((s,a)=>s+a.count,0);
  const config = [
    {s:"Keep",   cls:"hs-keep",   label:"Keep"},
    {s:"Merge",  cls:"hs-merge",  label:"Merge"},
    {s:"Retire", cls:"hs-retire", label:"Retire"},
  ];
  const segs = config.map(c=>({ ...c, count:(actions.find(a=>a.name===c.s)||{count:0}).count }));
  els.healthStrip.innerHTML = segs.filter(s=>s.count>0).map(s=>{
    const w=((s.count/total)*100).toFixed(1);
    return `<div class="health-segment ${s.cls}" style="flex-basis:${w}%" title="${esc(s.label)}: ${fmt(s.count)}">${w>5?fmt(s.count):""}</div>`;
  }).join("");
  els.healthLegend.innerHTML = segs.filter(s=>s.count>0).map(s=>
    `<span style="display:inline-flex;align-items:center;gap:5px;">
      <span style="width:10px;height:10px;border-radius:2px;background:${legendColor(s.cls)}"></span>
      ${esc(s.label)} (${fmt(s.count)})</span>`).join("");
}

// ── Quick wins ─────────────────────────────────────────────
function renderQuickWins(){
  const t = state.data.totals;
  const wins = [
    { emoji:"👻", title:"Zero-view cards (389 days)", big:fmt(t.forReviewCards),
      sub:`Cards unseen for the entire activity window. Moved to For Review tab — not in the go-forward TOC.` },
    { emoji:"✅", title:"Active go-forward cards", big:fmt(t.tocCards),
      sub:`Cards with at least 1 view since May 2025. These form the basis of the new Domo TOC.` },
    { emoji:"🗑", title:"Personal notebooks removed", big:fmt(t.personalRemoved),
      sub:`Joe's Cards, Charles C. Sandbox, Cooper's Graveyard, etc. — stripped entirely, no review needed.` },
    { emoji:"🔀", title:"Duplicate titles to merge", big:fmt(t.duplicateTitleCards),
      sub:`Same card living on multiple pages. Pick one canonical home per metric.` },
    { emoji:"⏱", title:"Stale 2+ years", big:fmt(t.stale730),
      sub:`${pct(t.stale730Pct)} of remaining inventory untouched since before Jun 2024.` },
    { emoji:"📝", title:"Need descriptions", big:pct(t.missingDescriptionsPct),
      sub:`Add a one-liner to every card that survives into the new TOC before launch.` },
  ];
  els.quickWins.innerHTML = wins.map(w=>`
    <div class="qw-card"><h4>${w.emoji} ${esc(w.title)}</h4><strong class="big">${esc(w.big)}</strong><p>${esc(w.sub)}</p></div>`).join("");
}

// ── Page bars / buckets ────────────────────────────────────
function renderPageBars(){
  const toc = state.data.inventory.filter(i=>!i.isForReview && !i.isNoisePage);
  const pageCounter = {};
  toc.forEach(i=>{ pageCounter[i.page]=(pageCounter[i.page]||0)+1; });
  const top = Object.entries(pageCounter).sort((a,b)=>b[1]-a[1]).slice(0,12);
  const max = top[0]?.[1]||1;
  const cat = {};
  toc.forEach(i=>{ if(!cat[i.page]) cat[i.page]=i.category; });
  els.pageBars.innerHTML = top.map(([page,count])=>`
    <div class="bar-row">
      <div class="bar-label">
        <strong title="${esc(page)}">${esc(page)}</strong>
        <span>${esc(cat[page]||"")}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(count/max)*100}%"></div></div>
      </div>
      <div class="bar-count">${fmt(count)}</div>
    </div>`).join("");
}

function renderBuckets(){
  // Stale buckets from full inventory
  const inv = state.data.inventory;
  const buckets = [
    {bucket:"0–90 days",    count:inv.filter(i=>i.ageDays!=null&&i.ageDays<=90).length},
    {bucket:"91–365 days",  count:inv.filter(i=>i.ageDays!=null&&i.ageDays>90&&i.ageDays<=365).length},
    {bucket:"1–2 years",    count:inv.filter(i=>i.ageDays!=null&&i.ageDays>365&&i.ageDays<=730).length},
    {bucket:"2+ years",     count:inv.filter(i=>i.ageDays!=null&&i.ageDays>730).length},
  ];
  els.staleBuckets.innerHTML = buckets.map(r=>`
    <div class="bucket-row"><span>${esc(r.bucket)}</span><strong>${fmt(r.count)}</strong></div>`).join("");
  els.viewBuckets.innerHTML = state.data.viewBuckets.map(r=>`
    <div class="bucket-row"><span>${esc(r.bucket)}</span><strong>${fmt(r.count)}</strong></div>`).join("");
}

// ── Rail ───────────────────────────────────────────────────
function renderRail(){
  const cats = state.data.categoryStats;
  const toc = cats.filter(c=>c.category!=="For Review");
  const rev = cats.find(c=>c.category==="For Review");
  els.areaCount.textContent = `${toc.length} areas`;
  const allCount = toc.reduce((s,c)=>s+c.cards,0);
  els.areaList.innerHTML = [
    { category:"All", cards: allCount },
    ...toc,
  ].map(area=>`
    <button class="area-button ${state.category===area.category?"active":""}" type="button" data-area="${esc(area.category)}">
      <span>${esc(area.category)}</span><small>${fmt(area.cards)}</small>
    </button>`).join("") + (rev ? `
    <div style="border-top:2px solid var(--line);margin-top:4px;">
      <button class="area-button ${state.category==="For Review"?"active":""}" type="button" data-area="For Review" style="opacity:0.7;">
        <span>For Review</span><small>${fmt(rev.cards)}</small>
      </button>
    </div>` : "");
}

// ── New Domo TOC (interactive accordion) ──────────────────
function renderTocAreaGrid(){
  const structure = state.data.tocStructure;
  els.tocAreaGrid.innerHTML = structure.map((area,idx)=>`
    <div class="toc-area-block" id="toc-block-${idx}">
      <button class="toc-area-header" data-idx="${idx}" type="button">
        <span class="toc-area-icon">${esc(area.icon)}</span>
        <span class="toc-area-name">${esc(area.area)}</span>
        <span class="toc-area-desc">${esc(area.description)}</span>
        <span class="toc-area-count">${fmt(getAreaCardCount(area.area))} cards</span>
        <span class="toc-chevron">▶</span>
      </button>
      <div class="toc-area-metrics" id="toc-metrics-${idx}" style="display:none;">
        ${area.metrics.map(m=>`
          <div class="toc-metric-row">
            <span class="toc-metric-name">${esc(m.name)}</span>
            <span class="toc-metric-notes">${esc(m.notes)}</span>
          </div>`).join("")}
      </div>
    </div>`).join("");

  document.querySelectorAll(".toc-area-header").forEach(btn=>{
    btn.addEventListener("click",()=>{
      const idx = btn.dataset.idx;
      const panel = document.querySelector(`#toc-metrics-${idx}`);
      const chevron = btn.querySelector(".toc-chevron");
      const open = panel.style.display !== "none";
      panel.style.display = open ? "none" : "block";
      chevron.textContent = open ? "▶" : "▼";
      btn.classList.toggle("open", !open);
    });
  });
}

function getAreaCardCount(areaName){
  const cat = state.data.categoryStats.find(c=>c.category===areaName);
  return cat ? cat.cards : 0;
}

// ── Inventory table ────────────────────────────────────────
function filteredInventory(){
  const term = state.search.trim().toLowerCase();
  return state.data.inventory.filter(i=>{
    if (i.isForReview) return false;
    if (state.category!=="All" && i.category!==state.category) return false;
    if (state.action!=="All" && i.action!==state.action) return false;
    if (state.usage!=="All" && i.usageTier!==state.usage) return false;
    if (!term) return true;
    return [i.title,i.page,i.category,i.owner,i.dataset].join(" ").toLowerCase().includes(term);
  });
}

function renderTable(){
  const rows = filteredInventory();
  const visible = rows.slice(0,200);
  els.resultCount.textContent = `${fmt(rows.length)} cards · showing ${fmt(visible.length)}`;
  els.inventoryRows.innerHTML = visible.map(i=>`
    <tr>
      <td><div class="truncate"><strong>${esc(i.title||"Untitled")}</strong><br><span class="muted">#${esc(i.id)}</span></div></td>
      <td><div class="truncate">${esc(i.page)}</div></td>
      <td>${esc(i.category)}</td>
      <td><span class="tag ${actionCls(i.action)}">${esc(i.action)}</span></td>
      <td><span class="tag ${usageCls(i.usageTier)}" title="${i.views} views · ${i.uniqueViewers} viewers">${esc(i.usageTier)} (${fmt(i.views)})</span></td>
      <td><div class="truncate">${esc(i.owner)}</div></td>
      <td><div class="truncate muted">${esc(i.dataset)}</div></td>
      <td style="white-space:nowrap;">${esc(i.lastModified||"—")}</td>
      <td><div class="tag-list">${(i.flags||[]).map(f=>`<span class="tag ${flagCls(f)}">${esc(f)}</span>`).join("")||'<span class="tag">—</span>'}</div></td>
    </tr>`).join("");
}

// ── For Review table ───────────────────────────────────────
function filteredReview(){
  const term = state.reviewSearch.trim().toLowerCase();
  return state.data.inventory.filter(i=>{
    if (!i.isForReview) return false;
    if (state.reviewCategory!=="All" && i.category!==state.reviewCategory) return false;
    if (state.reviewFlag!=="All" && !(i.flags||[]).includes(state.reviewFlag)) return false;
    if (!term) return true;
    return [i.title,i.page,i.category,i.owner].join(" ").toLowerCase().includes(term);
  });
}

function renderReviewTable(){
  const rows = filteredReview();
  const visible = rows.slice(0,200);
  els.reviewCount.textContent = `${fmt(rows.length)} cards · showing ${fmt(visible.length)}`;
  els.reviewRows.innerHTML = visible.map(i=>`
    <tr style="opacity:0.75;">
      <td><div class="truncate"><strong>${esc(i.title||"Untitled")}</strong><br><span class="muted">#${esc(i.id)}</span></div></td>
      <td><div class="truncate">${esc(i.page)}</div></td>
      <td>${esc(i.category)}</td>
      <td><div class="truncate">${esc(i.owner)}</div></td>
      <td><div class="truncate muted">${esc(i.dataset)}</div></td>
      <td style="white-space:nowrap;">${esc(i.lastModified||"—")}</td>
      <td><div class="tag-list">${(i.flags||[]).map(f=>`<span class="tag ${flagCls(f)}">${esc(f)}</span>`).join("")||'<span class="tag">—</span>'}</div></td>
    </tr>`).join("");
}

// ── Filters ────────────────────────────────────────────────
function renderFilters(){
  const tocCats = state.data.categoryStats.filter(c=>c.category!=="For Review");
  const allCats = ["All",...tocCats.map(c=>c.category)];
  const actions = ["All",...state.data.actions.map(a=>a.name)];
  els.categoryFilter.innerHTML = allCats.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join("");
  els.actionFilter.innerHTML = actions.map(a=>`<option value="${esc(a)}">${esc(a)}</option>`).join("");
  const revCats = ["All",...[...new Set(state.data.inventory.filter(i=>i.isForReview).map(i=>i.category))].sort()];
  els.reviewCategoryFilter.innerHTML = revCats.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join("");
}

// ── Tabs ───────────────────────────────────────────────────
function initTabs(){
  document.querySelectorAll(".tab-btn").forEach(btn=>{
    btn.addEventListener("click",()=>{
      document.querySelectorAll(".tab-btn").forEach(b=>b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p=>p.classList.remove("active"));
      btn.classList.add("active");
      document.querySelector(`#tab-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

function setCategory(cat){
  if(cat==="For Review"){
    document.querySelectorAll(".tab-btn").forEach(b=>b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(p=>p.classList.remove("active"));
    document.querySelector('[data-tab="review"]').classList.add("active");
    document.querySelector("#tab-review").classList.add("active");
  } else {
    state.category = cat;
    els.categoryFilter.value = cat;
    renderRail(); renderTable();
    document.querySelectorAll(".tab-btn").forEach(b=>b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(p=>p.classList.remove("active"));
    document.querySelector('[data-tab="inventory"]').classList.add("active");
    document.querySelector("#tab-inventory").classList.add("active");
  }
  state.category = cat;
  renderRail();
}

// ── CSV parser ─────────────────────────────────────────────
function parseCSV(text){
  const lines = text.trim().split("\n");
  const headers = lines[0].split(",").map(h=>h.trim().replace(/^"|"$/g,""));
  return lines.slice(1).map(line=>{
    const cols = [];
    let cur = "", inQ = false;
    for(let i=0;i<line.length;i++){
      const ch = line[i];
      if(ch==='"'){ inQ=!inQ; }
      else if(ch===","&&!inQ){ cols.push(cur); cur=""; }
      else { cur+=ch; }
    }
    cols.push(cur);
    const row = {};
    headers.forEach((h,i)=>{ row[h]=(cols[i]||"").trim(); });
    return row;
  });
}

function csvToTocStructure(rows){
  const areaMap = new Map();
  rows.filter(r=>r.status==="Active").forEach(r=>{
    if(!areaMap.has(r.area)){
      areaMap.set(r.area,{
        area: r.area,
        icon: r.area_icon,
        description: r.area_description,
        metrics: [],
      });
    }
    areaMap.get(r.area).metrics.push({
      name: r.metric_name,
      notes: r.metric_notes,
    });
  });
  return Array.from(areaMap.values());
}

// ── Init ───────────────────────────────────────────────────
async function init(){
  // Load inventory data and TOC sheet in parallel
  const [invRes, sheetRes] = await Promise.all([
    fetch("./data/site-data.json"),
    fetch(SHEET_URL),
  ]);
  if(!invRes.ok) throw new Error(`Cannot load inventory data: ${invRes.status}`);
  state.data = await invRes.json();

  if(sheetRes.ok){
    const csv = await sheetRes.text();
    state.data.tocStructure = csvToTocStructure(parseCSV(csv));
  } else {
    console.warn("Google Sheet unavailable — falling back to local toc_structure.json");
  }

  els.sourceMeta.innerHTML = `<strong>${esc(state.data.sourceFile)}</strong><br>Activity: ${esc(state.data.activityWindow)}`;

  renderKpis(); renderHealthStrip(); renderQuickWins();
  renderPageBars(); renderBuckets();
  renderTocAreaGrid();
  renderFilters(); renderRail();
  renderTable(); renderReviewTable();
  initTabs();

  els.areaList.addEventListener("click",e=>{ const b=e.target.closest("button[data-area]"); if(b) setCategory(b.dataset.area); });
  els.categoryFilter.addEventListener("change",e=>{ state.category=e.target.value; renderRail(); renderTable(); });
  els.actionFilter.addEventListener("change",e=>{ state.action=e.target.value; renderTable(); });
  els.usageFilter.addEventListener("change",e=>{ state.usage=e.target.value; renderTable(); });
  els.searchInput.addEventListener("input",e=>{ state.search=e.target.value; renderTable(); });
  els.clearFilters.addEventListener("click",()=>{
    state.category="All"; state.action="All"; state.usage="All"; state.search="";
    els.categoryFilter.value="All"; els.actionFilter.value="All"; els.usageFilter.value="All"; els.searchInput.value="";
    renderRail(); renderTable();
  });
  els.reviewSearch.addEventListener("input",e=>{ state.reviewSearch=e.target.value; renderReviewTable(); });
  els.reviewCategoryFilter.addEventListener("change",e=>{ state.reviewCategory=e.target.value; renderReviewTable(); });
  els.reviewFlagFilter.addEventListener("change",e=>{ state.reviewFlag=e.target.value; renderReviewTable(); });
}

init().catch(err=>{
  document.body.innerHTML=`<main class="app-shell"><section class="panel">
    <h1>Data did not load</h1><p class="muted">${esc(err.message)}</p>
  </section></main>`;
});
