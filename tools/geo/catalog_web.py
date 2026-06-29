#!/usr/bin/env python3
"""Interactive web grid for the tile catalog: verify entries, browse the FULL
packs, and add new tiles — all in the browser.

    uv run python tools/geo/catalog_web.py            # write out/catalog.html (open it)
    uv run python tools/geo/catalog_web.py --serve    # live: edits Save back to the JSON

Two panels:
  1. "Catalog" — every named object as a card you can flip verified/unverified.
  2. "Browse packs" — every tile on every sheet (franuka/school/bath/kenney),
     catalog regions outlined; click any cell to add it as a new entry.

Static mode (default) embeds the sheets as data URIs so the file is portable;
"Save" downloads an updated furniture_catalog.json. Serve mode keeps the same UI
but "Save" POSTs straight to furniture_catalog.json on disk — no copy step.

LLM option-count guidance lives in the catalog's "_llm_guidance" block and is
shown in the page header (see that field for the recommended thresholds + why).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tile_presets

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAPS = os.path.join(REPO, "godot-generative-agents", "maps")
CATALOG_PATH = os.path.join(HERE, "furniture_catalog.json")
TILE = 16  # every sheet is 16px tiles

# Fallback guidance if the catalog has no "_llm_guidance" block.
DEFAULT_GUIDANCE = {
    "options_per_category": 12,
    "max_per_prompt": 30,
    "note": "Show an LLM at most ~12 options per decision and ~30 total per "
    "prompt; pre-filter to the task and prefer verified tiles.",
}


def load_catalog() -> dict:
    with open(CATALOG_PATH) as fh:
        return json.load(fh)


def data_uri(filename: str) -> str:
    with open(os.path.join(MAPS, filename), "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def build_html(catalog: dict, served: bool) -> str:
    sheets = {
        name: {
            "uri": data_uri(meta["file"]),
            "cols": meta["cols"],
            "rows": meta["rows"],
        }
        for name, meta in catalog["sheets"].items()
    }
    guidance = catalog.get("_llm_guidance", DEFAULT_GUIDANCE)
    presets = tile_presets.load_presets()
    app = {
        "raw": catalog,
        "sheets": sheets,
        "guidance": guidance,
        "served": served,
        "tile": TILE,
        "presets": presets.get("presets", {}),
        "active": presets.get("active"),
    }
    return _TEMPLATE.replace("__DATA__", json.dumps(app))


# --------------------------------------------------------------------------- #
# The page. Plain string (NOT an f-string) so JS/CSS braces survive untouched;
# only the __DATA__ token is substituted.
# --------------------------------------------------------------------------- #
_TEMPLATE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Tile catalog</title>
<style>
  :root{--bg:#16161c;--panel:#20202a;--line:#3a3a48;--ink:#e6e6ee;--mut:#9a9ab0;
        --ok:#5dd17a;--no:#e6c84b;--add:#6fb3ff;--warn:#ff6b6b;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:13px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
  header{position:sticky;top:0;z-index:5;background:#12121a;
         border-bottom:1px solid var(--line);padding:10px 16px}
  h1{font-size:16px;margin:0 0 6px}
  .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .guidance{background:#1b2330;border:1px solid #2c3b52;border-radius:8px;
            padding:8px 12px;margin:8px 0;color:#cfe0f5}
  .guidance b{color:#9fd0ff}
  .pill{border:1px solid var(--line);border-radius:999px;padding:2px 9px;
        background:#2a2a36;color:var(--ink);cursor:pointer;font-size:12px}
  .pill.ok{border-color:var(--ok);color:var(--ok)}
  .pill.no{border-color:var(--no);color:var(--no)}
  button,select,input{font:inherit;color:var(--ink);background:var(--panel);
        border:1px solid var(--line);border-radius:6px;padding:4px 8px}
  button{cursor:pointer}
  button.primary{background:#2b4a6b;border-color:#3f6da0}
  .tabs{display:flex;gap:6px;margin:10px 0}
  .tab{padding:4px 12px;border-radius:6px 6px 0 0}
  .tab.sel{background:#2b4a6b;border-color:#3f6da0}
  main{padding:14px 16px}
  .sec{display:none} .sec.show{display:block}
  .grouphdr{margin:16px 0 6px;font-weight:700;color:#cdd;display:flex;gap:8px;align-items:center}
  .grouphdr .cnt{color:var(--mut);font-weight:400}
  .over{color:var(--warn);font-weight:700}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:10px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:8px;
        padding:8px;display:flex;flex-direction:column;gap:4px}
  .card.added{border-color:var(--add)}
  .crop-wrap{height:132px;display:flex;align-items:center;justify-content:center;
             border-radius:6px;overflow:hidden;
             /* checkerboard so transparent areas are obvious vs filled ones */
             background-color:#3a3a46;
             background-image:linear-gradient(45deg,#2c2c38 25%,transparent 25%),
               linear-gradient(-45deg,#2c2c38 25%,transparent 25%),
               linear-gradient(45deg,transparent 75%,#2c2c38 75%),
               linear-gradient(-45deg,transparent 75%,#2c2c38 75%);
             background-size:16px 16px;
             background-position:0 0,0 8px,8px -8px,-8px 0}
  .crop{image-rendering:pixelated}
  .nm{font-weight:600;font-size:12px;word-break:break-all}
  .lb{color:var(--mut);font-size:11px;min-height:14px}
  .meta{color:#7c7c92;font-size:10px}
  .card .row{justify-content:space-between}
  .del{color:#ff8a8a;border-color:#5a2a2a}
  /* browser */
  .legend{color:var(--mut);margin:6px 0}
  .sheetbox{position:relative;display:inline-block;border:1px solid var(--line);
            overflow:auto;max-width:100%}
  .sheetimg{display:block;image-rendering:pixelated;cursor:crosshair}
  .gridlines{position:absolute;inset:0;pointer-events:none}
  .obox{position:absolute;border:2px solid rgba(111,179,255,.9);pointer-events:none}
  .obox.v{border-color:rgba(93,209,122,.95)}
  .obox span{position:absolute;left:0;top:-13px;font-size:9px;color:#cfe0f5;
             background:#12121a;padding:0 2px;white-space:nowrap}
  .addform{background:var(--panel);border:1px solid var(--add);border-radius:8px;
           padding:10px;margin:10px 0;display:none;gap:8px;align-items:end;flex-wrap:wrap}
  .addform.show{display:flex}
  .addform label{display:flex;flex-direction:column;font-size:11px;color:var(--mut);gap:2px}
  .addform input{width:90px}
  .toast{position:fixed;bottom:16px;right:16px;background:#2b4a6b;color:#fff;
         padding:10px 14px;border-radius:8px;opacity:0;transition:.2s;pointer-events:none}
  .toast.show{opacity:1}
  /* presets */
  .presetbar{background:#1a2230;border:1px solid #2c3b52;border-radius:8px;
             padding:6px 10px;margin-top:6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .presetbar b{color:#9fd0ff}
  .card.inset{outline:2px solid var(--add);outline-offset:-2px}
  .nmrow{display:flex;justify-content:space-between;align-items:flex-start;gap:4px}
  .pstar{border:none;background:none;cursor:pointer;font-size:16px;line-height:1;
         color:var(--add);padding:0}
  .pnote{width:100%;font-size:11px;margin-top:2px}
  .modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;
         align-items:center;justify-content:center;z-index:20}
  .modal.show{display:flex}
  .modal .box{background:var(--panel);border:1px solid var(--line);border-radius:10px;
              padding:14px;width:min(760px,92vw);max-height:86vh;
              display:flex;flex-direction:column;gap:8px}
  .modal textarea{width:100%;height:52vh;background:#12121a;color:var(--ink);
                  border:1px solid var(--line);border-radius:6px;padding:8px;
                  font:12px ui-monospace,SFMono-Regular,monospace}
</style></head>
<body>
<header>
  <h1>Tile catalog &mdash; verify &amp; browse</h1>
  <div id="guidance" class="guidance"></div>
  <div class="row">
    <div class="tabs">
      <div class="tab sel" data-sec="catalog" onclick="showSec('catalog')">Catalog</div>
      <div class="tab" data-sec="browse" onclick="showSec('browse')">Browse packs</div>
    </div>
    <input id="search" placeholder="filter by name/label" oninput="render()">
    <select id="vfilter" onchange="render()">
      <option value="all">all</option>
      <option value="true">verified only</option>
      <option value="false">unverified only</option>
      <option value="added">added by me</option>
      <option value="inpreset">in this preset</option>
    </select>
    <span style="flex:1"></span>
    <span id="stats" class="meta"></span>
    <button class="primary" onclick="save()">Save catalog</button>
    <button onclick="revert()">Revert to file</button>
  </div>
  <div class="presetbar">
    <b>LLM preset:</b>
    <select id="presetSel" onchange="selectPreset(this.value)"></select>
    <button onclick="newPreset()">New</button>
    <input id="presetName" placeholder="preset name" style="width:130px">
    <input id="presetDesc" placeholder="description" style="width:200px">
    <label><input type="checkbox" id="presetActive"> active for LLM</label>
    <span id="presetCount" class="meta"></span>
    <span style="flex:1"></span>
    <button class="primary" onclick="savePreset()">Save preset</button>
    <button onclick="deletePreset()">Delete</button>
    <button onclick="showMenu()">Preview LLM menu</button>
  </div>
</header>
<main>
  <section id="sec-catalog" class="sec show"></section>
  <section id="sec-browse" class="sec">
    <div class="legend">Click any cell to add it as a new entry. Green = verified
      catalog tile, blue = unverified. Multi-tile objects are outlined.</div>
    <div id="tabs-browse" class="tabs"></div>
    <div id="addform" class="addform"></div>
    <div id="sheetview"></div>
  </section>
</main>
<div id="modal" class="modal"><div class="box">
  <div class="row"><b style="flex:1">LLM tile menu &mdash; this preset</b>
    <button onclick="copyMenu()">Copy</button><button onclick="closeMenu()">Close</button></div>
  <textarea id="menuText" readonly></textarea>
  <div class="meta">Same output as <code>tile_presets.py --menu</code> &mdash; paste into a furnishing prompt.</div>
</div></div>
<div id="toast" class="toast"></div>

<script>
const APP = __DATA__;
const TILE = APP.tile, BSCALE = 2;
// Catalog cards: fit the WHOLE object in the crop box (zoom small tiles up,
// shrink big ones down) so nothing is clipped. Integer scale = crisp pixels.
const CARD_MAXW = 116, CARD_MAXH = 124, CARD_MAXSCALE = 4;
function fitScale(o){
  const s = Math.min(CARD_MAXW/(o.w*TILE), CARD_MAXH/(o.h*TILE), CARD_MAXSCALE);
  return Math.max(1, Math.floor(s));
}
const SHEETS = APP.sheets, RAW = APP.raw, G = APP.guidance;
const ORIG = Object.keys(RAW.objects);            // preserves order incl _comment_

// ---- state ---------------------------------------------------------------
function freshState(){
  const byKey = {}; const order = [];
  for(const k of ORIG){ if(k.startsWith('_')) continue;
    byKey[k] = Object.assign({key:k, origKey:k, added:false}, RAW.objects[k]); order.push(k); }
  return {byKey, order, added:[]};
}
let state = freshState();
loadLocal();

function loadLocal(){
  try{
    const s = JSON.parse(localStorage.getItem('tilecatalog')||'null');
    if(!s) return;
    for(const [k,v] of Object.entries(s.verified||{})) if(state.byKey[k]) state.byKey[k].verified=v;
    for(const e of (s.added||[])){ state.byKey[e.key]=Object.assign({added:true},e);
      state.order.push(e.key); state.added.push(e.key); }
  }catch(_){}
}
function saveLocal(){
  const verified={}; for(const k of state.order) if(!state.byKey[k].added) verified[k]=state.byKey[k].verified;
  const added = state.added.map(k=>state.byKey[k]);
  localStorage.setItem('tilecatalog', JSON.stringify({verified, added}));
}

// ---- preset state (named tile subsets the LLM should use) ----------------
let PRESETS = JSON.parse(JSON.stringify(APP.presets||{}));
let ACTIVE = APP.active||null;
let editing = {name:'', desc:'', tiles:new Set(), notes:{}};
(function loadLocalPresets(){
  try{ const s=JSON.parse(localStorage.getItem('tilepresets')||'null');
    if(s){ PRESETS=s.presets||PRESETS; if('active'in s) ACTIVE=s.active; } }catch(_){}
})();
function saveLocalPresets(){
  localStorage.setItem('tilepresets', JSON.stringify({presets:PRESETS, active:ACTIVE}));
}

// ---- sprite crop ---------------------------------------------------------
function cropStyle(o, scale){
  const s = SHEETS[o.sheet];
  return `width:${o.w*TILE*scale}px;height:${o.h*TILE*scale}px;`+
    `background-image:url(${s.uri});`+
    `background-size:${s.cols*TILE*scale}px ${s.rows*TILE*scale}px;`+
    `background-position:-${o.col*TILE*scale}px -${o.row*TILE*scale}px;`;
}

// ---- catalog panel -------------------------------------------------------
function render(){
  renderGuidance();
  const q = document.getElementById('search').value.toLowerCase();
  const vf = document.getElementById('vfilter').value;
  const sec = document.getElementById('sec-catalog');
  sec.innerHTML='';
  // group by sheet -> category
  const groups = {};
  for(const k of state.order){
    const o = state.byKey[k];
    if(q && !(k.toLowerCase().includes(q)||(o.label||'').toLowerCase().includes(q))) continue;
    if(vf==='true'&&!o.verified) continue;
    if(vf==='false'&&o.verified) continue;
    if(vf==='added'&&!o.added) continue;
    if(vf==='inpreset'&&!editing.tiles.has(k)) continue;
    const g = o.sheet+' / '+o.category;
    (groups[g]=groups[g]||[]).push(o);
  }
  const cap = G.options_per_category;
  for(const g of Object.keys(groups).sort()){
    const list = groups[g];
    const hdr = document.createElement('div'); hdr.className='grouphdr';
    const over = list.length>cap;
    hdr.innerHTML = `${g} <span class="cnt">${list.length} tiles`+
      (over?` &middot; <span class="over">over the ${cap}/menu guideline</span>`:``)+`</span>`;
    sec.appendChild(hdr);
    const grid = document.createElement('div'); grid.className='grid';
    for(const o of list) grid.appendChild(card(o));
    sec.appendChild(grid);
  }
  renderStats();
  saveLocal();
}

function card(o){
  const inset = editing.tiles.has(o.key);
  const c = document.createElement('div'); c.className='card'+(o.added?' added':'')+(inset?' inset':'');
  const wrap=document.createElement('div'); wrap.className='crop-wrap';
  const cr=document.createElement('div'); cr.className='crop'; cr.style=cropStyle(o,fitScale(o));
  wrap.appendChild(cr); c.appendChild(wrap);
  const nmrow=document.createElement('div'); nmrow.className='nmrow';
  const nm=document.createElement('div'); nm.className='nm'; nm.textContent=o.key;
  const star=document.createElement('button'); star.className='pstar';
  star.title='add/remove from the LLM preset'; star.textContent=inset?'★':'☆';
  star.onclick=()=>togglePreset(o.key);
  nmrow.appendChild(nm); nmrow.appendChild(star); c.appendChild(nmrow);
  const lb=document.createElement('div'); lb.className='lb'; lb.textContent=o.label||''; c.appendChild(lb);
  const meta=document.createElement('div'); meta.className='meta';
  meta.textContent=`${o.sheet} (${o.col},${o.row}) ${o.w}x${o.h}`; c.appendChild(meta);
  if(inset){ const note=document.createElement('input'); note.className='pnote';
    note.placeholder='note for LLM (optional)'; note.value=editing.notes[o.key]||'';
    note.oninput=()=>{ editing.notes[o.key]=note.value; }; c.appendChild(note); }
  const row=document.createElement('div'); row.className='row';
  const pill=document.createElement('button');
  pill.className='pill '+(o.verified?'ok':'no');
  pill.textContent=o.verified?'✓ verified':'? unverified';
  pill.onclick=()=>{o.verified=!o.verified; render();};
  row.appendChild(pill);
  if(o.added){ const d=document.createElement('button'); d.className='pill del'; d.textContent='delete';
    d.onclick=()=>{ delete state.byKey[o.key];
      state.order=state.order.filter(k=>k!==o.key);
      state.added=state.added.filter(k=>k!==o.key); render(); drawSheet(curSheet); };
    row.appendChild(d); }
  c.appendChild(row);
  return c;
}

function renderStats(){
  const all=state.order.length, v=state.order.filter(k=>state.byKey[k].verified).length;
  document.getElementById('stats').textContent=`${v}/${all} verified · ${state.added.length} added`;
}
function renderGuidance(){
  const byCat={}; for(const k of state.order){const c=state.byKey[k].category; byCat[c]=(byCat[c]||0)+1;}
  const over=Object.entries(byCat).filter(([c,n])=>n>G.options_per_category)
    .map(([c,n])=>`${c} (${n})`);
  document.getElementById('guidance').innerHTML =
    `<b>LLM option budget:</b> ≤ ${G.options_per_category} per category, `+
    `≤ ${G.max_per_prompt} total per prompt. ${G.note}` +
    (over.length?`<br><span class="over">Categories above the per-menu cap: ${over.join(', ')} `+
      `— split or pre-filter these before handing to an LLM.</span>`:``);
}

// ---- browse panel --------------------------------------------------------
let curSheet = Object.keys(SHEETS)[0];
function buildTabs(){
  const t=document.getElementById('tabs-browse'); t.innerHTML='';
  for(const name of Object.keys(SHEETS)){
    const d=document.createElement('div'); d.className='tab'+(name===curSheet?' sel':'');
    d.textContent=`${name} (${SHEETS[name].cols}×${SHEETS[name].rows})`;
    d.onclick=()=>{curSheet=name; buildTabs(); drawSheet(name); closeAdd();};
    t.appendChild(d);
  }
}
function drawSheet(name){
  const s=SHEETS[name]; const W=s.cols*TILE*BSCALE, H=s.rows*TILE*BSCALE;
  const view=document.getElementById('sheetview');
  view.innerHTML='';
  const box=document.createElement('div'); box.className='sheetbox';
  const img=document.createElement('img'); img.className='sheetimg'; img.src=s.uri;
  img.style.width=W+'px'; img.style.height=H+'px';
  const lines=document.createElement('div'); lines.className='gridlines';
  const cell=TILE*BSCALE;
  lines.style.backgroundImage=
    `linear-gradient(to right,rgba(255,255,255,.10) 1px,transparent 1px),`+
    `linear-gradient(to bottom,rgba(255,255,255,.10) 1px,transparent 1px)`;
  lines.style.backgroundSize=`${cell}px ${cell}px`;
  box.appendChild(img); box.appendChild(lines);
  for(const k of state.order){ const o=state.byKey[k]; if(o.sheet!==name) continue;
    const b=document.createElement('div'); b.className='obox'+(o.verified?' v':'');
    b.style.left=o.col*cell+'px'; b.style.top=o.row*cell+'px';
    b.style.width=o.w*cell+'px'; b.style.height=o.h*cell+'px';
    const sp=document.createElement('span'); sp.textContent=o.key; b.appendChild(sp);
    box.appendChild(b);
  }
  img.addEventListener('click',e=>{
    const r=img.getBoundingClientRect();
    const col=Math.floor((e.clientX-r.left)/cell), row=Math.floor((e.clientY-r.top)/cell);
    openAdd(name,col,row);
  });
  view.appendChild(box);
}
function openAdd(sheet,col,row){
  const f=document.getElementById('addform'); f.className='addform show';
  f.innerHTML=`
    <div style="font-weight:700;color:var(--add)">Add ${sheet} (${col},${row})</div>
    <label>name<input id="a_name" placeholder="snake_case"></label>
    <label>label<input id="a_label" style="width:160px" placeholder="what it is"></label>
    <label>category<select id="a_cat">
      ${['furniture','floor','wall','window','door','prop','tree']
        .map(c=>`<option>${c}</option>`).join('')}</select></label>
    <label>w<input id="a_w" type="number" value="1" min="1"></label>
    <label>h<input id="a_h" type="number" value="1" min="1"></label>
    <button class="primary" onclick="addEntry('${sheet}',${col},${row})">Add</button>
    <button onclick="closeAdd()">Cancel</button>`;
  f.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function closeAdd(){const f=document.getElementById('addform'); f.className='addform';}
function addEntry(sheet,col,row){
  const name=document.getElementById('a_name').value.trim();
  if(!name){toast('name required');return;}
  if(state.byKey[name]){toast('name already exists');return;}
  const o={key:name, sheet, col, row,
    w:+document.getElementById('a_w').value||1, h:+document.getElementById('a_h').value||1,
    category:document.getElementById('a_cat').value,
    label:document.getElementById('a_label').value.trim(), verified:false, added:true};
  state.byKey[name]=o; state.order.push(name); state.added.push(name);
  closeAdd(); drawSheet(curSheet); render(); toast('added '+name);
}

// ---- export / save -------------------------------------------------------
function buildCatalog(){
  // map each surviving original by its ORIGINAL key so renames are found
  const byOrig={};
  for(const k of state.order){ const o=state.byKey[k]; if(!o.added) byOrig[o.origKey]=o; }
  const objs={};
  for(const k of ORIG){
    if(k.startsWith('_')){ objs[k]=RAW.objects[k]; continue; }
    const o=byOrig[k];                 // undefined only if somehow removed
    if(o) objs[o.key]=toObj(o);        // o.key may differ from k after a rename
  }
  if(state.added.length){
    objs['_comment_user_added']='--- added via catalog_web.py ---';
    for(const k of state.added){ const o=state.byKey[k]; if(o) objs[o.key]=toObj(o); }
  }
  const out={}; if(RAW._README)out._README=RAW._README;
  if(RAW._llm_guidance)out._llm_guidance=RAW._llm_guidance;
  out.sheets=RAW.sheets; out.objects=objs;
  return out;
}
function toObj(o){const r={sheet:o.sheet,col:o.col,row:o.row,w:o.w,h:o.h,category:o.category};
  if(o.room)r.room=o.room; r.label=o.label||''; r.verified=!!o.verified; return r;}

async function save(){
  const data=buildCatalog(); saveLocal();
  if(APP.served){
    try{const res=await fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(data)});
      toast(res.ok?'saved to furniture_catalog.json':'save failed');}
    catch(e){toast('save failed: '+e);}
  }else{
    const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download='furniture_catalog.json'; a.click();
    toast('downloaded — replace tools/geo/furniture_catalog.json');
  }
}
function revert(){ if(!confirm('Discard local edits and reload the saved file?'))return;
  localStorage.removeItem('tilecatalog'); state=freshState(); render(); drawSheet(curSheet); }

function showSec(name){
  document.querySelectorAll('.tab[data-sec]').forEach(t=>
    t.classList.toggle('sel',t.dataset.sec===name));
  document.getElementById('sec-catalog').classList.toggle('show',name==='catalog');
  document.getElementById('sec-browse').classList.toggle('show',name==='browse');
}
let _t; function toast(m){const e=document.getElementById('toast'); e.textContent=m;
  e.className='toast show'; clearTimeout(_t); _t=setTimeout(()=>e.className='toast',1800);}

// ---- presets -------------------------------------------------------------
function refreshPresetSel(){
  const sel=document.getElementById('presetSel');
  const names=Object.keys(PRESETS).sort();
  sel.innerHTML='<option value="">(none / new)</option>'+names.map(n=>
    `<option value="${n}"${n===editing.name?' selected':''}>${n}${n===ACTIVE?' ★':''}</option>`).join('');
}
function updatePresetCount(){
  const cap=G.max_per_prompt, n=editing.tiles.size;
  document.getElementById('presetCount').textContent=
    `${n} tiles${n>cap?` ⚠ over ${cap}/prompt`:''}`;
}
function selectPreset(name){
  if(!name){ newPreset(); return; }
  const p=PRESETS[name]||{};
  editing={name, desc:p.description||'', tiles:new Set(p.tiles||[]), notes:Object.assign({},p.notes||{})};
  document.getElementById('presetName').value=name;
  document.getElementById('presetDesc').value=editing.desc;
  document.getElementById('presetActive').checked=(ACTIVE===name);
  refreshPresetSel(); updatePresetCount(); render();
}
function newPreset(){
  editing={name:'',desc:'',tiles:new Set(),notes:{}};
  document.getElementById('presetName').value='';
  document.getElementById('presetDesc').value='';
  document.getElementById('presetActive').checked=false;
  refreshPresetSel(); updatePresetCount(); render();
}
function togglePreset(key){
  if(editing.tiles.has(key)){ editing.tiles.delete(key); delete editing.notes[key]; }
  else editing.tiles.add(key);
  updatePresetCount(); render();
}
function savePreset(){
  const name=document.getElementById('presetName').value.trim();
  if(!name){ toast('preset name required'); return; }
  editing.name=name; editing.desc=document.getElementById('presetDesc').value.trim();
  PRESETS[name]={description:editing.desc, tiles:[...editing.tiles],
    notes:Object.fromEntries(Object.entries(editing.notes).filter(([k,v])=>editing.tiles.has(k)&&v))};
  if(document.getElementById('presetActive').checked) ACTIVE=name;
  else if(ACTIVE===name) ACTIVE=null;
  saveLocalPresets(); persistPresets(); refreshPresetSel();
}
function deletePreset(){
  const name=document.getElementById('presetName').value.trim();
  if(!name||!PRESETS[name]){ toast('select a saved preset first'); return; }
  if(!confirm('Delete preset '+name+'?')) return;
  delete PRESETS[name]; if(ACTIVE===name) ACTIVE=null;
  saveLocalPresets(); persistPresets(); newPreset();
}
async function persistPresets(){
  const payload={active:ACTIVE, presets:PRESETS};
  if(APP.served){
    try{const r=await fetch('/save-presets',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      toast(r.ok?'saved to tile_presets.json':'save failed');}catch(e){toast('save failed: '+e);}
  }else{
    const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download='tile_presets.json'; a.click();
    toast('downloaded — replace tools/geo/tile_presets.json');
  }
}
// LLM tile menu (mirrors tile_presets.py --menu)
function buildMenu(){
  const cap=G.options_per_category, max=G.max_per_prompt;
  const tiles=[...editing.tiles].filter(k=>state.byKey[k]);
  const byCat={}; tiles.forEach(k=>{(byCat[state.byKey[k].category]=byCat[state.byKey[k].category]||[]).push(k);});
  const L=[`# Tile menu — preset: ${editing.name||'(unsaved)'}`];
  if(editing.desc) L.push(editing.desc);
  L.push('','Use ONLY these tiles when furnishing/parsing the tilemap; reference each by its `name`.',
    `Option budget: <= ${cap} per category, <= ${max} total.`,'');
  if(!tiles.length) L.push('_(no tiles in this preset yet)_');
  Object.keys(byCat).sort().forEach(cat=>{
    const ks=byCat[cat]; L.push(`## ${cat} (${ks.length})${ks.length>cap?'  !! over budget':''}`);
    ks.forEach(k=>{const o=state.byKey[k]; const n=editing.notes[k]?`  | note: ${editing.notes[k]}`:'';
      L.push(`- ${k} [${o.w}x${o.h}] — ${o.label||''}${n}`);}); L.push('');
  });
  if(tiles.length>max) L.push(`> ${tiles.length} tiles exceeds the ${max}/prompt budget — split before use.`);
  return L.join('\n');
}
function showMenu(){ document.getElementById('menuText').value=buildMenu();
  document.getElementById('modal').className='modal show'; }
function closeMenu(){ document.getElementById('modal').className='modal'; }
function copyMenu(){ const t=document.getElementById('menuText'); t.select();
  navigator.clipboard.writeText(t.value).then(()=>toast('copied'),()=>toast('press Cmd/Ctrl+C')); }

// ---- boot ----------------------------------------------------------------
buildTabs(); drawSheet(curSheet);
if(ACTIVE&&PRESETS[ACTIVE]) selectPreset(ACTIVE); else newPreset();
</script>
</body></html>"""


def serve(port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send(200, build_html(load_catalog(), served=True))
            else:
                self._send(204, b"")

        def do_POST(self):  # noqa: N802
            if self.path not in ("/save", "/save-presets"):
                self._send(404, b"")
                return
            n = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(n))
                if self.path == "/save":
                    with open(CATALOG_PATH, "w") as fh:
                        json.dump(data, fh, indent=2)
                        fh.write("\n")
                    print(f"saved {CATALOG_PATH}")
                else:  # /save-presets
                    tile_presets.write_presets(data)
                    print(f"saved {tile_presets.PRESETS_PATH}")
                self._send(200, '{"ok":true}', "application/json")
            except Exception as e:  # noqa: BLE001
                self._send(
                    500, json.dumps({"ok": False, "error": str(e)}), "application/json"
                )

        def log_message(self, *a):  # quiet
            pass

    url = f"http://localhost:{port}/"
    print(f"serving catalog editor at {url}  (Ctrl-C to stop; Save writes the JSON)")
    webbrowser.open(url)
    ThreadingHTTPServer(("localhost", port), Handler).serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--serve",
        action="store_true",
        help="run a local server; Save writes furniture_catalog.json directly",
    )
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--out", default=os.path.join(HERE, "out", "catalog.html"))
    args = ap.parse_args()

    if args.serve:
        serve(args.port)
        return
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        fh.write(build_html(load_catalog(), served=False))
    print(f"wrote {args.out}  (open in a browser; Save downloads an updated catalog)")


if __name__ == "__main__":
    main()
