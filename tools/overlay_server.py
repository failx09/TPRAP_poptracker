#!/usr/bin/env python3
"""ER graph overlay viewer (debug tool).

Reads "[overlay] {json}" lines from stdin (PopTracker stdout, printed by
scripts/overlay.lua) and serves a live SVG graph at http://localhost:8123.

Usage:
    ~/Downloads/PopTracker-*.appimage /path/to/pack 2>&1 \
        | python3 tools/overlay_server.py

Python stdlib only. Node colors = accessibility level; edge colors = category
flag. Toggle edge categories in the page. Polls /state every 500ms.
"""
import json
import os
import pty
import select
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8123
LEVEL_COLORS = {0: "#c0392b", 1: "#c0392b", 3: "#c0392b", 5: "#f1c40f", 6: "#2ecc71"}
LEVEL_NAMES = {0: "None", 3: "Inspect", 5: "SequenceBreak", 6: "Normal"}
CATEGORY_COLORS = {
    "TO": "#888888", "EXT": "#3498db", "INT": "#e67e22", "OOW": "#27ae60",
    "CAV": "#16a085", "GRO": "#8e44ad", "DUN": "#c0392b", "BRE": "#7f1a1a",
    "DHC": "#d35400", "BOS": "#2c3e50",
}

state = {"nodes": [], "edges": [], "levels": {}, "spawn": "", "dirty": None}
lock = threading.Lock()

import os
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "node_positions.json")) as fh:
        ANCHORS = json.load(fh)
    print(f"anchors loaded: {len(ANCHORS)}", file=sys.stderr)
except OSError:
    ANCHORS = {}
    print("no node_positions.json - run tools/derive_positions.py", file=sys.stderr)
PACK_DIR = None  # set in main() from argv
EDGE_RULES = {}  # "From__FLAG__To" -> cleaned Lua rule source
FUNCS = {}  # control.lua function name -> {"expr": tree|None, "src": str}

# edit-mode overrides (renderer only): dragged positions, ghost nodes and
# user-created edges. Survives node_positions.json regeneration.
EDITS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "overlay_edits.json")


def load_edits():
    try:
        with open(EDITS_PATH) as fh:
            d = json.load(fh)
    except Exception:
        d = {}
    return {"positions": d.get("positions") or {},
            "ghosts": d.get("ghosts") or [],
            "edges": d.get("edges") or []}


EDITS = load_edits()


def parse_edge_rules(path):
    global EDGE_RULES
    import rule_parser
    EDGE_RULES = rule_parser.parse_edge_rules(path)


def read_stream_fd(fd, tag):
    """Line-buffered reader over a file descriptor."""
    buf = b""
    while True:
        data = os.read(fd, 65536)
        if not data:
            break
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            handle_line(line.decode(errors="replace"))


def handle_line(line):
    if not line.startswith("[overlay] "):
        print(line, file=sys.stderr, end="")  # tracker chatter -> server log
        return
    try:
        snap = json.loads(line[len("[overlay] "):])
    except json.JSONDecodeError:
        return
    with lock:
        if snap.get("nodes") is not None:
            state.update(snap)


def read_stdin():
    for line in sys.stdin:
        if not line.startswith("[overlay] "):
            continue
        handle_line(line)


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>ER graph overlay</title><style>
html,body{width:100%;height:100%;margin:0;background:#111;color:#ccc;font-family:monospace;overflow:hidden}
#wrap{width:100vw;height:100vh}
#bar{position:fixed;top:0;left:0;right:0;padding:6px 10px;background:rgba(26,26,26,0.85);white-space:nowrap;z-index:2}
label{margin-right:10px;cursor:pointer}
svg{display:block}
svg circle[data-node]{cursor:pointer;transition:r .08s}
svg circle[data-node]:hover{stroke:#fff;stroke-width:2.5;filter:drop-shadow(0 0 3px #fff) drop-shadow(0 0 10px #6fd3ff) brightness(1.5)}
#bar input{vertical-align:middle}
#info{display:none;position:fixed;top:36px;right:8px;width:440px;max-height:82vh;overflow:auto;background:rgba(20,20,20,0.95);border:1px solid #444;padding:8px;font-size:12px;z-index:3}
#info .head{font-size:13px;margin-bottom:2px}
#info .sub{color:#888;font-size:11px;padding:3px 0}
#info .row{padding:4px 0;border-top:1px solid #333;cursor:pointer}
#info .mark{font-weight:bold}
#info .ok .mark{color:#4caf50}
#info .no .mark{color:#e05555}
#info .cat{color:#888}
#info .lvl{color:#777;font-size:11px}
#info .rule{color:#9ab;font-size:11px;white-space:pre-wrap;word-break:break-word;margin-top:2px}
#info .grant{color:#4caf50;font-size:11px}
#info .ruleup{color:#e8c04a;font-size:11px}
#info .sect{color:#aaa;font-size:11px;margin-top:8px;border-top:1px solid #444;padding-top:6px}
#info .tag{color:#999}
#info .op{color:#888}
#info .grp{margin:2px 0}
#info .oplabel{color:#e8c04a;font-size:11px}
#info .grp ul{list-style:none;margin:2px 0;padding-left:10px;border-left:1px dotted #555}
#info .grp li{padding:1px 0}
#info .grp li::before{content:"– ";color:#666}
#info .grp li.subgrp{padding:0}
#info .grp li.subgrp::before{content:none}
#info .fntok{cursor:pointer;text-decoration:underline dotted #888}
#info .back{cursor:pointer;color:#7ab;margin-left:10px;font-size:11px}
</style></head><body>
<div id="bar"></div>
<div id="wrap"></div>
<div id="info"></div>
<script>
let state=null, pos=null, posKey=null, viewBox=null, baseVb=null, bg=null;
let contentKey=null, svgEl=null, dragging=null, lastWantBg=null;
// --- edit mode (renderer only) ---
let ED={positions:{},ghosts:[],edges:[],rev:0}, edKey=null, editmode=false;
let dragNode=null, linkFrom=null, movedPx=0;
function saveEdits(){
  ED.rev++; contentKey=null;
  fetch('/edits',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({positions:ED.positions,ghosts:ED.ghosts,edges:ED.edges})});
}
function nearestNode(vx,vy,th){
  let best=null,bd=th;
  for(const n of state.nodes){ const p=pos[n]; if(!p) continue;
    const d=Math.hypot(p[0]-vx,p[1]-vy); if(d<bd){bd=d;best={type:'node',id:n};} }
  for(const g of ED.ghosts){ const d=Math.hypot(g.x-vx,g.y-vy);
    if(d<bd){bd=d;best={type:'ghost',id:g.id};} }
  return best;
}
function segDist(px,py,ax,ay,bx,by){
  const dx=bx-ax,dy=by-ay,L2=dx*dx+dy*dy;
  if(!L2) return Math.hypot(px-ax,py-ay);
  const t=Math.max(0,Math.min(1,((px-ax)*dx+(py-ay)*dy)/L2));
  return Math.hypot(px-(ax+t*dx),py-(ay+t*dy));
}
function nearestEdge(vx,vy,th){
  let best=null,bd=th;
  for(const e of state.edges){ const a=pos[e.f],b=pos[e.t]; if(!a||!b) continue;
    const d=segDist(vx,vy,a[0],a[1],b[0],b[1]);
    if(d<bd){bd=d;best={kind:'graph',key:e.k,f:e.f,t:e.t,x:vx,y:vy};} }
  for(const ce of ED.edges){ const a=pos[ce.a],b=pos[ce.b]; if(!a||!b) continue;
    const d=segDist(vx,vy,a[0],a[1],b[0],b[1]); if(d<bd){bd=d;best={kind:'user',id:ce.id,x:vx,y:vy};} }
  return best;
}
// ghosts apply to a node PAIR: most connections exist twice in region_rules
// (A__FLAG__B and B__FLAG2__A) and the two lines overlap, so splitting one
// must split both. Legacy ghosts (edge key only) get their pair parsed.
function ghostsFor(f,t){
  const out=[];
  for(const g of ED.ghosts){
    if(!g.a){
      const m=/^(.*)__(.*)__(.*)$/.exec(g.edge||'');
      if(m){ g.a=m[1]; g.b=m[3]; }
    }
    if(g.edge===undefined || g.edge===null ||
       (g.a===f&&g.b===t)||(g.a===t&&g.b===f)) out.push(g);
  }
  return out;
}
// force-directed layout seeded from anchors; anchors are pinned at map coords
function doLayout(){
  const s=state; if(!s||!s.nodes) return;
  const nodeKey = s.nodes.length+':'+s.edges.length+':'+(s.spawn||'');
  if (pos && nodeKey===posKey) return;   // keep stable across polls
  posKey = nodeKey;
  const pinned = s.pos||{};
  pos = {};
  // adjacency for BFS seeding
  const adjMap={};
  for(const e of s.edges){
    (adjMap[e.f]=adjMap[e.f]||[]).push(e.t);
    (adjMap[e.t]=adjMap[e.t]||[]).push(e.f);
  }
  // seed: pinned anchors at map coords, their neighbors nearby (BFS),
  // only truly disconnected nodes fall back to random center scatter
  for(const n of s.nodes){
    if(pinned[n]) pos[n]=[pinned[n][0], pinned[n][1]];
  }
  const queue=s.nodes.filter(n=>pinned[n]);
  const seen=new Set(queue);
  while(queue.length){
    const n=queue.shift();
    for(const m of (adjMap[n]||[])){
      if(seen.has(m)) continue;
      seen.add(m);
      const p=pos[n];
      const a=Math.random()*2*Math.PI, r=250+Math.random()*250;
      pos[m]=[p[0]+r*Math.cos(a), p[1]+r*Math.sin(a)];
      queue.push(m);
    }
  }
  let maxX=0, maxY=0;
  for(const n of s.nodes){
    if(!pos[n]) pos[n]=[4000+3000*(Math.random()-0.5), 4000+3000*(Math.random()-0.5)];
    maxX=Math.max(maxX,pos[n][0]); maxY=Math.max(maxY,pos[n][1]);
  }
  // relax: springs along edges + node repulsion, anchors fixed
  const N=s.nodes.length, idx={}, xs=[], ys=[], fixed=[];
  s.nodes.forEach((n,i)=>{ idx[n]=i; xs[i]=pos[n][0]; ys[i]=pos[n][1]; fixed[i]=!!pinned[n]; });
  const adj=[]; s.edges.forEach(e=>{ const a=idx[e.f], b=idx[e.t]; if(a!==undefined&&b!==undefined&&a!==b) adj.push([a,b]); });
  for(let it=0; it<250; it++){
    const fx=new Float64Array(N), fy=new Float64Array(N);
    for(const [a,b] of adj){
      let dx=xs[b]-xs[a], dy=ys[b]-ys[a];
      const d=Math.sqrt(dx*dx+dy*dy)+0.01;
      const f=(d-250)*0.02/d;
      fx[a]+=dx*f; fy[a]+=dy*f; fx[b]-=dx*f; fy[b]-=dy*f;
    }
    for(let i=0;i<N;i++) for(let j=i+1;j<N;j++){
      let dx=xs[j]-xs[i], dy=ys[j]-ys[i];
      const d2=dx*dx+dy*dy;
      if(d2<250*250 && d2>0.01){
        const d=Math.sqrt(d2), f=600/d2;
        fx[i]-=dx*f; fy[i]-=dy*f; fx[j]+=dx*f; fy[j]+=dy*f;
      }
    }
    for(let i=0;i<N;i++){
      if(fixed[i]) continue;
      xs[i]+=Math.max(-40,Math.min(40,fx[i]));
      ys[i]+=Math.max(-40,Math.min(40,fy[i]));
    }
  }
  s.nodes.forEach((n,i)=>{ pos[n]=[xs[i],ys[i]]; });
  // fit viewBox
  let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;
  for(const n of s.nodes){ x0=Math.min(x0,pos[n][0]); y0=Math.min(y0,pos[n][1]); x1=Math.max(x1,pos[n][0]); y1=Math.max(y1,pos[n][1]); }
  const m=150; baseVb=[x0-m,y0-m,(x1-x0)+2*m,(y1-y0)+2*m];
  viewBox=baseVb.slice();
}
const CAT_COLORS=%(cats)s, LEVEL_COLORS=%(levels)s, LEVEL_NAMES=%(lnames)s;
async function poll(){
  try{ const r=await fetch('/state'); state=await r.json();
    if(state.edits && !dragNode){
      const j=JSON.stringify([state.edits.positions,state.edits.ghosts,state.edits.edges]);
      if(j!==edKey){ edKey=j; ED={positions:state.edits.positions||{},
        ghosts:state.edits.ghosts||[], edges:state.edits.edges||[], rev:(ED.rev||0)+1};
        contentKey=null; }
    }
    render(); }catch(e){}
}
function render(){
  const s=state; if(!s||!s.nodes) return;
  doLayout();
  const active=new Set(Object.keys(s.levels||{}).filter(k=>s.levels[k]>0));
  const boxes=[...document.querySelectorAll('#bar input[type=checkbox]')];
  const show={}; boxes.forEach(b=>show[b.dataset.cat]=b.checked);
  const onlyReach=document.querySelector('#onlyreach').checked;
  const wantBg=document.querySelector('#mapbg').checked;
  const showLabels=document.querySelector('#labels').checked;
  let edges=s.edges.filter(e=>{
     const c=e.c.replace(/_[AB]$/,'');
     if(!show[c]) return false;
     if(onlyReach && !(active.has(e.f)&&active.has(e.t))) return false;
     return true;
  });
  let lines='', dots='', labels='';
  const pairGh=(f,t)=>{                       // both directions + legacy backfill
    const out=[];
    for(const g of ED.ghosts){
      if(!g.a){ const m=/^(.*)__(.*)__(.*)$/.exec(g.edge||''); if(m){ g.a=m[1]; g.b=m[3]; } }
      if((g.a===f&&g.b===t)||(g.a===t&&g.b===f)) out.push(g);
    }
    return out;
  };
  for(const e of edges){
    let a=pos[e.f]; if(!a) continue;
    const col=CAT_COLORS[e.c.replace(/_[AB]$/,'')]||'#555';
    const gs=pairGh(e.f,e.t);
    for(const g of gs){                       // ghost-split edge: A -> X ... -> B
      lines+=`<line x1="${a[0]}" y1="${a[1]}" x2="${g.x}" y2="${g.y}" `+
        `stroke="${col}" stroke-opacity="0.55" stroke-width="3.5"><title>${e.f} -> ${g.id} -> ${e.t} (${e.c})</title></line>`;
      a=[g.x,g.y];
    }
    const b=pos[e.t]; if(!b) continue;
    lines+=`<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" `+
      `stroke="${col}" stroke-opacity="0.55" stroke-width="3.5"><title>${e.f} -> ${e.t} (${e.c})</title></line>`;
  }
  for(const ce of ED.edges){                  // user-created edges (art only)
    const a=pos[ce.a], b=pos[ce.b]; if(!a||!b) continue;
    lines+=`<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" `+
      `stroke="#777" stroke-opacity="0.8" stroke-width="3" stroke-dasharray="10 6">`+
      `<title>created: ${ce.a} -> ${ce.b} (right-click to remove)</title></line>`;
  }
  for(const n of s.nodes){
    const p=pos[n]; if(!p) continue;
    const lvl=(s.levels||{})[n]||0;
    const col=LEVEL_COLORS[lvl]||'#c0392b';
    const r=(n===s.spawn)?18:10;
    dots+=`<circle cx="${p[0]}" cy="${p[1]}" r="${r}" fill="${col}" data-node="${n}" stroke="${(s.pos||{})[n]?'#fff':'none'}" stroke-width="${(s.pos||{})[n]?2:0}"><title>${n} = ${LEVEL_NAMES[lvl]||lvl}${n===s.spawn?' [SPAWN]':''}${(s.pos||{})[n]?' [MAP ANCHOR]':''}</title></circle>`;
    if(showLabels||n===s.spawn) labels+=
      `<text x="${p[0]}" y="${p[1]-r-4}" font-size="10" text-anchor="middle" data-lab="${n}" `+
      `fill="${(lvl>0||n===s.spawn)?'#ccc':'#666'}" stroke="#111" stroke-width="0.3" paint-order="stroke">${n}</text>`;
  }
  if(editmode){                               // ghost nodes: edit mode only
    for(const g of ED.ghosts){
      dots+=`<rect x="${g.x-7}" y="${g.y-7}" width="14" height="14" `+
        `transform="rotate(45 ${g.x} ${g.y})" data-ghost="${g.id}" `+
        `fill="#12303a" stroke="#6fd3ff" stroke-width="2" cursor="move">`+
        `<title>ghost ${g.id} (splits ${g.edge}) — drag to move, right-click to remove</title></rect>`;
      labels+=`<text x="${g.x}" y="${g.y-11}" font-size="9" text-anchor="middle" `+
        `fill="#6fd3ff" stroke="#111" stroke-width="0.3" paint-order="stroke">X</text>`;
    }
    if(linkFrom){
      const p=pos[linkFrom];
      if(p) dots+=`<circle cx="${p[0]}" cy="${p[1]}" r="14" fill="none" stroke="#fff" stroke-width="2.5" stroke-dasharray="4 3" pointer-events="none"/>`;
    }
  }
  if(wantBg!==lastWantBg){ lastWantBg=wantBg; viewBox=null; }
  if(wantBg&&bg) baseVb=[0,0,bg.naturalWidth,bg.naturalHeight];
  if(!viewBox) viewBox=baseVb||[0,0,800,800];
  const key=JSON.stringify([s,show,onlyReach,wantBg,showLabels,baseVb,editmode,ED.rev]);
  const inner=`${(wantBg&&bg)?`<image href="/mapimg" width="${bg.naturalWidth}" height="${bg.naturalHeight}"/>`:''}${lines}${dots}${labels}`;
  if(key===contentKey && svgEl){
    svgEl.setAttribute('viewBox', viewBox.join(' '));   // pan/zoom only
    return;
  }
  contentKey=key;
  const wrap=document.getElementById('wrap');
  wrap.innerHTML=
    `<svg id="graph" width="100%" height="100%" viewBox="${viewBox.join(' ')}" `+
    `style="cursor:grab">${inner}</svg>`;
  svgEl=wrap.firstElementChild;
}
function bar(){
  const cats=Object.keys(CAT_COLORS);
  bg=new Image(); bg.src='/mapimg';
  document.getElementById('bar').innerHTML=
    `<label><input type="checkbox" id="editmode"> edit mode</label>`+
    `<label><input type="checkbox" id="onlyreach">reachable only</label>`+
    `<label><input type="checkbox" id="mapbg">map bg</label>`+
    `<label><input type="checkbox" id="labels" checked>labels</label>`+
    cats.map(c=>`<label style="color:${CAT_COLORS[c]}"><input type="checkbox" data-cat="${c}" checked> ${c}</label>`).join('')+
    ` <span id="stat"></span>`;
  [...document.querySelectorAll('#bar input')].forEach(b=>b.onchange=()=>{
    if(b.id==='editmode'){ editmode=b.checked; if(!editmode) linkFrom=null; }
    stat(); render(); });
}
function stat(){
  const el=document.getElementById('stat');
  el.textContent = editmode
    ? (linkFrom?`link: click target node for ${linkFrom} (Esc cancels)`
               :'edit: drag nodes/ghosts · click edge = split · L = link nodes · right-click = remove · E = exit')
    : '';
}
// uniform scale the viewBox is rendered at ("meet": fit inside the element)
function meetScale(r){
  return Math.min(r.width/viewBox[2], r.height/viewBox[3]);
}
function svgPoint(evt){
  const r=svgEl.getBoundingClientRect();
  const s=meetScale(r);
  const ox=r.left+(r.width-viewBox[2]*s)/2, oy=r.top+(r.height-viewBox[3]*s)/2;
  return [viewBox[0]+(evt.clientX-ox)/s, viewBox[1]+(evt.clientY-oy)/s];
}
document.getElementById('wrap').addEventListener('wheel', e=>{
  e.preventDefault();
  if(!svgEl||!viewBox) return;
  const [mx,my]=svgPoint(e);
  const f=e.deltaY>0?1.15:1/1.15;
  let w=Math.max(60, Math.min(baseVb?baseVb[2]*1.5:40000, viewBox[2]*f));
  const h=w*(viewBox[3]/viewBox[2]);
  viewBox=[mx-(mx-viewBox[0])*w/viewBox[2], my-(my-viewBox[1])*w/viewBox[2], w, h];
  svgEl.setAttribute('viewBox', viewBox.join(' '));
},{passive:false});
document.getElementById('wrap').addEventListener('mousedown', e=>{
  if(e.button!==0) return;
  movedPx=0;
  if(editmode&&svgEl){
    const [vx,vy]=svgPoint(e);
    const hit=nearestNode(vx,vy,14/meetScale(svgEl.getBoundingClientRect()));
    if(hit){
      let p;
      if(hit.type==='node') p=pos[hit.id];
      else { const g=ED.ghosts.find(x=>x.id===hit.id); p=[g.x, g.y]; }
      dragNode={...hit, ox:p[0]-vx, oy:p[1]-vy};
      e.preventDefault(); return;
    }
  }
  dragging={x:e.clientX, y:e.clientY, vb:viewBox.slice(), s:meetScale(svgEl.getBoundingClientRect())};
  svgEl.style.cursor='grabbing';
});
window.addEventListener('mousemove', e=>{
  if(dragNode&&svgEl){
    movedPx+=Math.abs(e.movementX||0)+Math.abs(e.movementY||0);
    const [vx,vy]=svgPoint(e);
    const nx=vx+dragNode.ox, ny=vy+dragNode.oy;
    if(!isFinite(nx)||!isFinite(ny)) return;
    if(dragNode.type==='node'){
      pos[dragNode.id]=[nx,ny];
      const c=svgEl.querySelector(`circle[data-node="${CSS.escape(dragNode.id)}"]`);
      if(c){c.setAttribute('cx',nx);c.setAttribute('cy',ny);}
      const l=svgEl.querySelector(`text[data-lab="${CSS.escape(dragNode.id)}"]`);
      if(l){l.setAttribute('x',nx);l.setAttribute('y',ny-14);}
    }else{
      const g=ED.ghosts.find(x=>x.id===dragNode.id);
      if(g){g.x=nx;g.y=ny;}
      const r=svgEl.querySelector(`rect[data-ghost="${CSS.escape(dragNode.id)}"]`);
      if(r){r.setAttribute('x',nx-7);r.setAttribute('y',ny-7);
            r.setAttribute('transform',`rotate(45 ${nx} ${ny})`);}
    }
    return;
  }
  if(!dragging||!svgEl) return;
  movedPx+=Math.abs(e.movementX||0)+Math.abs(e.movementY||0);
  viewBox[0]=dragging.vb[0]-(e.clientX-dragging.x)/dragging.s;
  viewBox[1]=dragging.vb[1]-(e.clientY-dragging.y)/dragging.s;
  svgEl.setAttribute('viewBox', viewBox.join(' '));
});
window.addEventListener('mouseup', ()=>{
  if(dragNode){
    if(dragNode.type==='node') ED.positions[dragNode.id]=pos[dragNode.id].slice();
    saveEdits(); dragNode=null; return;
  }
  if(dragging&&svgEl) svgEl.style.cursor='grab';
  dragging=null;
});
window.addEventListener('keydown', e=>{
  if(e.key==='r'&&svgEl&&baseVb){ viewBox=baseVb.slice(); svgEl.setAttribute('viewBox', viewBox.join(' ')); }
  if(e.key==='e'&&e.target.tagName!=='INPUT'){
    editmode=!editmode;
    const cb=document.querySelector('#editmode'); if(cb) cb.checked=editmode;
    if(!editmode) linkFrom=null;
    stat(); render();
  }
  if(e.key==='l'&&editmode){ linkFrom=null; stat(); }
  if(e.key==='Escape'){ if(linkFrom){ linkFrom=null; stat(); } closeInfo(); }
});
let selNode=null, RULES=null, FUNCS=null, curView=null, viewStack=[], noPush=false;
function ensureRules(){
  if(RULES===null){
    RULES=false;
    fetch('/rules').then(r=>r.json()).then(d=>{ RULES=d||{}; rerender(); }).catch(()=>{ RULES={}; });
  }
  if(FUNCS===null){
    FUNCS=false;
    fetch('/funcs').then(r=>r.json()).then(d=>{ FUNCS=d||{}; rerender(); }).catch(()=>{ FUNCS={}; });
  }
}
function showView(v){ if(!noPush && curView && curView!==v) viewStack.push(curView); noPush=false; curView=v; }
function rerender(){ noPush=true; if(curView){ if(curView.type==='func') renderFunc(curView.name); else renderNode(curView.name); } }
function back(){
  if(viewStack.length){ const v=viewStack.pop(); noPush=true; curView=v; if(v.type==='func') renderFunc(v.name); else renderNode(v.name); }
  else closeInfo();
}
function lvlColor(node, s){ const lvl=(s.levels||{})[node]||0; return lvl>0?'#4caf50':'#e05555'; }
function renderExpr(e, s){
  if(e===null||e===undefined) return '';
  if(typeof e==='string'){
    const it=(s.items||{})[e];
    const col=it===undefined?'#8a8':(it>0?'#7fbf7f':'#e05555');
    return `<span style="color:${col}" title="${it===undefined?'unknown state':it+' owned'}">${e}</span>`;
  }
  if(typeof e==='number') return `<span style="color:#7fbf7f">${e}</span>`;
  if(e.and||e.or){
    const items=(e.and||e.or);
    if(items.length===1) return renderExpr(items[0],s);
    const rows=items.map(x=>{
      const g=x&&(x.and||x.or);
      return `<li${g?' class="subgrp"':''}>${renderExpr(x,s)}</li>`;
    }).join('');
    return `<div class="grp"><span class="oplabel">${e.and?'all of':'any of'}:</span><ul>${rows}</ul></div>`;
  }
  if(e.item) return `<span style="color:#7fbf7f">${e.item}${e.count&&e.count>1?' ×'+e.count:''}</span>`;
  if(e.access){
    return `<span class="fntok" style="color:${lvlColor(e.access,s)}" onclick="showInfo('${e.access}');event.stopPropagation()">@${e.access}</span>`;
  }
  if(e.fn){
    const r=(s.funcs||{})[e.fn];
    const col=r===undefined?'#c9a':(r?'#7fbf7f':'#e05555');
    const args=(e.args&&e.args.length)
      ? '('+e.args.map(a=>renderExpr(a,s)).join(', ')+')' : '()';
    return `<span class="fntok" style="color:${col}" onclick="showFunc('${e.fn}');event.stopPropagation()">${e.fn}${args}</span>`;
  }
  if(e.raw) return `<span style="color:#9ab">${e.raw}</span>`;
  return '';
}
function renderFuncSource(src, s){
  let h = src.replace(/&/g,'&amp;').replace(/</g,'&lt;');
  h = h.replace(/canAccess\\("(\\w+)"/g, (m,node)=>
    `canAccess(<span style="color:${lvlColor(node,s)}">"${node}"</span>`);
  h = h.replace(/"(\\w+)"/g, m=>`<span style="color:#7fbf7f">${m}</span>`);
  h = h.replace(/(\\w+)\\(/g, (m,f)=>{
    if(!FUNCS[f]) return m;
    const r=(s.funcs||{})[f];
    const col=r===undefined?'':(r?'#7fbf7f':'#e05555');
    return `<span class="fntok" style="color:${col}" onclick="showFunc('${f}');event.stopPropagation()">${f}(</span>`;
  });
  h = h.replace(/"(?=[^"]*$)|^"/g, m=>m);
  return h;
}
function showInfo(node){ showView({type:'node',name:node}); ensureRules(); renderNode(node); }
function showFunc(name){ showView({type:'func',name}); ensureRules(); renderFunc(name); }
function renderNode(node){
  const s=state;
  if(!s||!s.edges) return;
  selNode=node;
  const via=(s.via||{})[node]||{};
  const viaRule=(s.viarule||{})[node]||{};
  const lvl=(s.levels||{})[node]||0;
  const inc=s.edges.filter(e=>e.t===node);
  inc.sort((a,b)=>((via[b.k]!==undefined)-(via[a.k]!==undefined)) || a.f.localeCompare(b.f));
  let rows='';
  for(const e of inc){
    const pass=via[e.k]!==undefined;
    const r=RULES?RULES[e.k]:null;
    let txt='';
    if(r && (r.n||r.s)){
      txt=`<div class="rule">`+
        (r.n?`<span class="tag">normal:</span> ${renderExpr(r.n,s)}`
            :'<span class="tag">no conditions</span>')+
        (r.s?`<br><span class="tag">seq-break:</span> ${renderExpr(r.s,s)}`:'')+
        `</div>`;
    }
    rows+=`<div class="row ${pass?'ok':'no'}" onclick="showInfo('${e.f}')">`+
      `<span class="mark">${pass?'✔':'✘'}</span> <b>${e.f}</b> <span class="cat">[${e.c}]</span> `+
      `<span class="lvl">(${LEVEL_NAMES[(s.levels||{})[e.f]||0]||'None'})</span>`+
      txt+
      (pass?`<div class="grant">grants: ${LEVEL_NAMES[via[e.k]]||via[e.k]}</div>`:'')+
      (pass&&viaRule[e.k]!==undefined&&viaRule[e.k]>via[e.k]
        ?`<div class="ruleup">conditions reach ${LEVEL_NAMES[viaRule[e.k]]} — limited by previous node</div>`:'')+
      `</div>`;
  }
  document.getElementById('info').innerHTML=
    `<div class="head"><b>${node}</b> = ${LEVEL_NAMES[lvl]||lvl}`+
    (viewStack.length?`<span class="back" onclick="back()">← back</span>`:'')+
    `<span style="cursor:pointer;float:right;padding:0 4px" onclick="closeInfo()">✕</span></div>`+
    `<div class="sect">access rules · region_rules.lua (evaluated live)</div>`+
    `<div class="sub">${inc.length} incoming edge${inc.length===1?'':'s'}${node===s.spawn?' · SPAWN':''} · click a row to jump, click a function for details</div>`+
    (rows||'<div class="sub">no incoming edges</div>');
  document.getElementById('info').style.display='block';
}
function renderFunc(name){
  const s=state||{};
  const f=FUNCS?FUNCS[name]:null;
  let body='';
  if(f && f.expr) body=`<div class="rule">${renderExpr(f.expr,s)}</div>`;
  else if(f && f.src) body=`<div class="rule">${renderFuncSource(f.src,s)}</div>`;
  else body='<div class="sub">not found in control.lua</div>';
  const r=s.funcs?s.funcs[name]:undefined;
  if(r!==undefined) body+=`<div class="grant">result: ${r?'currently satisfied':'not satisfied'}</div>`;
  document.getElementById('info').innerHTML=
    `<div class="head"><b>${name}()</b> <span class="sub">control.lua</span>`+
    (viewStack.length?`<span class="back" onclick="back()">← back</span>`:'')+
    `<span style="cursor:pointer;float:right;padding:0 4px" onclick="closeInfo()">✕</span></div>`+
    body;
  document.getElementById('info').style.display='block';
}
function closeInfo(){ selNode=null; curView=null; viewStack=[]; document.getElementById('info').style.display='none'; }
document.getElementById('wrap').addEventListener('click', e=>{
  if(movedPx>4||!svgEl||!state) return;       // was a drag, not a click
  const t=e.target.closest ? e.target.closest('circle[data-node]') : null;
  const name=t?t.getAttribute('data-node'):null;
  if(editmode){
    const [vx,vy]=svgPoint(e);
    if(linkFrom){                             // pick target -> create edge
      if(name&&name!==linkFrom){
        ED.edges.push({id:'u'+ED.edges.length+'_'+linkFrom+'__'+name, a:linkFrom, b:name});
        saveEdits(); render();
      }
      linkFrom=null; stat(); return;
    }
    if(name){ linkFrom=name; stat(); return; }
    const ed=nearestEdge(vx,vy,10/meetScale(svgEl.getBoundingClientRect()));
    if(ed&&ed.kind==='graph'){                // split edge with a ghost node
      ED.ghosts.push({id:'g'+Date.now().toString(36), edge:ed.key,
                      a:ed.f, b:ed.t, x:vx, y:vy});
      saveEdits(); render();
    }
    return;
  }
  if(name) showInfo(name);
});
document.getElementById('wrap').addEventListener('contextmenu', e=>{
  if(!editmode||!svgEl) return;
  e.preventDefault();
  const [vx,vy]=svgPoint(e);
  const s=meetScale(svgEl.getBoundingClientRect());
  const gi=ED.ghosts.findIndex(g=>Math.hypot(g.x-vx,g.y-vy)<14/s);
  if(gi>=0){ ED.ghosts.splice(gi,1); saveEdits(); render(); return; }
  const ed=nearestEdge(vx,vy,10/s);
  if(ed&&ed.kind==='user'){ ED.edges=ED.edges.filter(c=>c.id!==ed.id); saveEdits(); render(); }
});
window.addEventListener('keydown', e=>{ if(e.key==='Escape') closeInfo(); });
bar(); poll(); setInterval(poll,500);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/state":
            with lock:
                body = json.dumps(dict(state,
                                       pos={**ANCHORS, **EDITS["positions"]},
                                       edits=EDITS)).encode()
            ctype = "application/json"
        elif self.path == "/funcs":
            body = json.dumps(FUNCS).encode()
            ctype = "application/json"
        elif self.path == "/rules":
            body = json.dumps(EDGE_RULES).encode()
            ctype = "application/json"
        elif self.path == "/mapimg":
            img = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "overworld_composite.png")
            if not (img and os.path.isfile(img)):
                img = os.path.join(PACK_DIR, "images", "Overworld", "Full Map Big.png") if PACK_DIR else None
            if img and os.path.isfile(img):
                with open(img, "rb") as fh:
                    body = fh.read()
                ctype = "image/png"
            else:
                self.send_error(404)
                return
        elif self.path == "/":
            body = (PAGE
                    .replace("%(cats)s", json.dumps(CATEGORY_COLORS))
                    .replace("%(levels)s", json.dumps(LEVEL_COLORS))
                    .replace("%(lnames)s", json.dumps(LEVEL_NAMES))).encode()
            ctype = "text/html"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/edits":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self.send_error(400)
            return
        with lock:
            for sec in ("positions", "ghosts", "edges"):
                if sec in d and isinstance(d[sec], list if sec != "positions" else dict):
                    EDITS[sec] = d[sec]
            try:
                with open(EDITS_PATH, "w") as fh:
                    json.dump(EDITS, fh, indent=1, sort_keys=True)
            except OSError as ex:
                print(f"edit save failed: {ex}", file=sys.stderr)
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _set_pdeathsig():
    """preexec hook: die automatically when the parent (server) dies, even on
    SIGKILL - keeps orphan trackers from piling up."""
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG = 1
    except Exception:
        pass


def spawn_tracker(argv):
    """Run the tracker under a pseudo-TTY so its stdout is line-buffered."""
    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave,
                            close_fds=True, preexec_fn=_set_pdeathsig)
    os.close(slave)
    threading.Thread(target=read_stream_fd, args=(master, "pty"), daemon=True).start()
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
    print("tracker exited; viewer stays up with last state", file=sys.stderr)


def main():
    global PACK_DIR
    argv = sys.argv[1:]
    PACK_DIR = argv[1] if len(argv) > 1 else None
    parse_edge_rules(os.path.join(PACK_DIR, "scripts", "region_rules.lua")
                     if PACK_DIR else "scripts/region_rules.lua")
    import rule_parser
    FUNCS.update(rule_parser.parse_functions(
        os.path.join(PACK_DIR, "scripts", "control.lua")
        if PACK_DIR else "scripts/control.lua"))
    print(f"edge rules parsed: {len(EDGE_RULES)}, "
          f"functions parsed: {len(FUNCS)}", file=sys.stderr)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"overlay viewer: http://localhost:{PORT}", file=sys.stderr)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if argv and argv[0] != "--":
        spawn_tracker(argv)          # blocks until the tracker exits
    else:
        threading.Thread(target=read_stdin, daemon=True).start()
        try:
            threading.Event().wait()  # stdin mode: run forever
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
