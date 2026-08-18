#!/usr/bin/env python3
"""regroup/render.py — draw the workstream canvas from regroup.json.

The page IS the canvas. Everything else floats over it in a small HUD.

Each workstream reads top to bottom as the thing you actually lost:
    your prompt  ->  decisions made  ->  tasks  ->  subtasks
Each of those has its own shape, so the hierarchy is legible before it is read.

Design follows the skill-receipts console system: warm neutrals, one green
accent, one rust danger, hairline rules, pill chips, monospace throughout.
"""

import json
import sys
from pathlib import Path

# Paths are resolved against the working directory, so `scripts/render.py
# example/regroup.json out.html` works from the repo root. Bare defaults fall
# back to sitting beside the script.
HERE = Path(__file__).parent
data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "regroup.json"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "regroup.html"
data = json.loads(data_path.read_text())

HTML = r"""<title>Grove Regroup</title>
<style>
:root{
  --bg:#fbfbfa; --sunk:#f3f3f1; --panel:#ffffff; --hud:rgba(251,251,250,.93);
  --fg:#1a1a19; --dim:#6b6b68; --faint:#8f8d88; --line:#e4e4e1;
  --accent:#2f6f4f; --danger:#b5432d; --warn:#946a1f; --live:#5b4a8c;
  --tint-accent:#eaf2ed; --tint-danger:#f8ebe8; --tint-warn:#f6efe1; --tint-live:#eeeaf5;
  --shadow:0 1px 2px rgba(0,0,0,.05); --shadow-lg:0 8px 34px -10px rgba(0,0,0,.22);
}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#161614; --sunk:#1c1c1a; --panel:#1f1f1c; --hud:rgba(22,22,20,.93);
  --fg:#eceae5; --dim:#9a978f; --faint:#7b7871; --line:#2c2a27;
  --accent:#7fc0a0; --danger:#e08a76; --warn:#d6a95c; --live:#a99ad6;
  --tint-accent:#1a2a21; --tint-danger:#2e1c19; --tint-warn:#2c2418; --tint-live:#221d2e;
  --shadow:0 1px 2px rgba(0,0,0,.5); --shadow-lg:0 8px 34px -10px rgba(0,0,0,.8);
}}
:root[data-theme="dark"]{
  --bg:#161614; --sunk:#1c1c1a; --panel:#1f1f1c; --hud:rgba(22,22,20,.93);
  --fg:#eceae5; --dim:#9a978f; --faint:#7b7871; --line:#2c2a27;
  --accent:#7fc0a0; --danger:#e08a76; --warn:#d6a95c; --live:#a99ad6;
  --tint-accent:#1a2a21; --tint-danger:#2e1c19; --tint-warn:#2c2418; --tint-live:#221d2e;
  --shadow:0 1px 2px rgba(0,0,0,.5); --shadow-lg:0 8px 34px -10px rgba(0,0,0,.8);
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);overflow:hidden;
  font:14px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
h1,h2,h3,h4{margin:0;font-weight:700;font-family:inherit;text-wrap:balance}
.lab{color:var(--dim);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.08em}
.t-accent,.t-moss{color:var(--accent)} .t-danger,.t-rose{color:var(--danger)}
.t-warn,.t-amber{color:var(--warn)} .t-live,.t-violet{color:var(--live)} .t-ink{color:var(--fg)}

/* ---------------- the canvas is the page ---------------- */
#shell{position:fixed;top:46px;left:0;right:0;bottom:0;background:var(--sunk);overflow:hidden;cursor:grab;
  background-image:radial-gradient(var(--line) 1.2px,transparent 1.2px);background-size:24px 24px}
#shell.drag{cursor:grabbing}
.world{position:absolute;top:0;left:0;transform-origin:0 0;padding:34px;width:max-content}
.band{display:grid;grid-template-columns:repeat(8,214px);gap:0 26px}
.band.open{align-items:start}
.band.chips{align-items:start;margin-top:12px}
.band.retired{align-items:start;margin-top:24px}
.trunk{position:relative;height:172px;margin:36px 0 0;z-index:2}
.trunk-line{position:absolute;left:0;right:0;top:54px;height:2px;background:var(--accent);opacity:.5}
.nodes{position:absolute;inset:0;display:grid;grid-template-columns:repeat(8,1fr)}
.node{display:flex;flex-direction:column;align-items:center;padding-top:38px}
.node .dot{width:13px;height:13px;border-radius:50%;background:var(--bg);
  border:2px solid var(--accent);z-index:2}
.node.head .dot{width:19px;height:19px;background:var(--accent);box-shadow:0 0 0 4px var(--sunk)}
.node .d{font-size:11px;color:var(--dim);margin-top:10px;background:var(--sunk);
  padding:1px 7px;border-radius:10px;border:1px solid var(--line)}
.node .t{font-size:12px;color:var(--fg);text-align:center;line-height:1.35;max-width:158px;
  margin-top:5px;font-weight:600;background:var(--sunk);padding:3px 6px;border-radius:5px}
svg.wires{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}

/* ---------------- workstream card ---------------- */
.card{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--dim);
  border-radius:9px;padding:18px 20px;position:relative;z-index:1;font-size:14px;
  box-shadow:var(--shadow)}
.card.l-unmerged{border-top-color:var(--danger)}
.card.l-merged{border-top-color:var(--accent)}
.card.l-none{border-top-color:var(--dim)}
.card h3{font-size:17px;line-height:1.3;margin-bottom:9px}
/* When you are panned away from the timeline the card must still say WHEN.
   Opened -> last touched, plus how long ago, on its own line. */
.clock{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:11px;
  padding:6px 9px;border-radius:6px;background:var(--sunk);border:1px solid var(--line);
  font-size:11.5px;color:var(--dim)}
.clock .from{color:var(--fg);font-weight:600}
.clock .arrow{color:var(--faint)}
.clock .to{color:var(--fg);font-weight:600}
.clock .ago{margin-left:auto;padding:1px 8px;border-radius:9px;border:1px solid var(--line);
  background:var(--bg);color:var(--dim);white-space:nowrap}
.clock .ago.hot{color:var(--live);border-color:var(--live)}
.clock .ago.cold{color:var(--danger);border-color:var(--danger)}
.task-h .ref{font-size:11px;color:var(--faint);font-weight:400;text-align:right;
  white-space:nowrap;line-height:1.4}
.task-h .ref b{display:block;color:var(--dim);font-weight:400}
.status{display:flex;gap:9px;align-items:baseline;margin-bottom:7px;flex-wrap:wrap}
.tag{font-size:11.5px;font-weight:700;padding:3px 10px;border-radius:10px;
  border:1px solid currentColor;white-space:nowrap;display:inline-flex;align-items:center;gap:6px}
.tag.l-unmerged{color:var(--danger)} .tag.l-merged{color:var(--accent)} .tag.l-none{color:var(--dim)}
.tag.s-live{color:var(--live)} .tag.s-idle{color:var(--warn)}
.tag.s-none,.tag.s-closed{color:var(--faint)}
.tagdetail{font-size:12px;color:var(--dim);line-height:1.5;flex:1;min-width:0}
.meta{font-size:12px;color:var(--dim);line-height:1.65;border-top:1px solid var(--line);
  padding-top:10px;margin-top:11px;word-break:break-word}
.meta b{color:var(--fg);font-weight:600}

/* --- shape 1: the prompt. Your own words, quoted. --- */
.ask{margin:14px 0 0;background:var(--sunk);border:1px solid var(--line);border-left:3px solid var(--dim);
  border-radius:0 7px 7px 0;padding:11px 13px 12px}
.ask .lab{display:block;margin-bottom:5px}
.ask p{margin:0;font-size:13.5px;line-height:1.6;color:var(--fg)}
.ask p::before{content:"\201C"} .ask p::after{content:"\201D"}

/* --- shape 2: a decision. Diamond, tinted band. --- */
.decs{margin-top:14px}
.dec-row{display:grid;grid-template-columns:16px 1fr;gap:9px;align-items:start;
  background:var(--tint-accent);border-radius:6px;padding:8px 11px;margin-top:6px;
  font-size:12.5px;line-height:1.55}
.dec-row .gl{color:var(--accent);font-weight:700;line-height:1.45}

/* --- shape 3: a task. Bordered node with a status square. --- */
.tasks{margin-top:14px;display:flex;flex-direction:column;gap:9px}
.task{border:1px solid var(--line);border-radius:7px;padding:9px 11px;background:var(--bg)}
.task.done{border-left:3px solid var(--accent)}
.task.unknown{border-left:3px solid var(--warn)}
.task.open{border-left:3px solid var(--faint)}
.task-h{display:grid;grid-template-columns:16px 1fr auto;gap:9px;align-items:start;
  font-size:13px;line-height:1.5;font-weight:600}
.task-h .gl{line-height:1.4}
.task.done .gl{color:var(--accent)} .task.unknown .gl{color:var(--warn)}
.task.open .gl{color:var(--faint)}

/* --- shape 4: a subtask. Indented, on a spine. --- */
.subs{margin:8px 0 1px 6px;padding-left:13px;border-left:1px solid var(--line);
  display:flex;flex-direction:column;gap:5px}
.sub{position:relative;display:grid;grid-template-columns:12px 1fr;gap:8px;
  font-size:12px;line-height:1.5;color:var(--dim)}
.sub::before{content:"";position:absolute;left:-13px;top:9px;width:9px;height:1px;
  background:var(--line)}
.sub .gl{font-size:11px;line-height:1.6}
.sub.done .gl{color:var(--accent)} .sub.unknown .gl{color:var(--warn)}
.sub.open .gl{color:var(--faint)}

.verdict{margin:15px 0 0;font-size:13.5px;color:var(--fg);font-weight:600;line-height:1.6}
.next{margin:10px 0 0;font-size:12.5px;color:var(--dim);line-height:1.6}
.next::before{content:"\2192 ";color:var(--warn);font-weight:700}
.act{margin-top:13px;border-top:1px solid var(--line);padding-top:12px}
.act .h{font-size:12.5px;color:var(--fg);font-weight:600;margin-bottom:6px}
button.cmd{font:inherit;font-size:12px;width:100%;text-align:left;cursor:pointer;
  background:var(--sunk);color:var(--fg);border:1px solid var(--line);border-radius:6px;
  padding:8px 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
button.cmd:hover{border-color:var(--accent);color:var(--accent)}
button.cmd:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button.cmd.done{color:var(--accent);border-color:var(--accent)}
.dotlive{width:6px;height:6px;border-radius:50%;background:var(--live);display:inline-block;
  animation:pulse 2.4s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@media(prefers-reduced-motion:reduce){.dotlive{animation:none}}

/* ---------------- tombstones + retired ---------------- */
.chipcard{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:6px;padding:11px 12px;position:relative;z-index:1;font-size:12px}
.chipcard h4{margin:0 0 7px;font-size:12.5px;line-height:1.35}
.chipcard .ln{color:var(--dim);line-height:1.55}
.chipcard .ln b{color:var(--accent);font-weight:700}
.chipcard .act{margin-top:9px;padding-top:9px}

/* ---------------- one thin bar, everything else on demand ----------------
   The canvas is the product; chrome that permanently covers it is a bug. The
   bar owns a 46px strip and the shell starts below it, so nothing is hidden. */
#topbar{position:fixed;top:0;left:0;right:0;height:46px;z-index:40;display:flex;
  align-items:center;gap:14px;padding:0 12px;background:var(--hud);
  border-bottom:1px solid var(--line);backdrop-filter:blur(8px)}
#topbar .brand{display:flex;align-items:baseline;gap:9px;flex:0 0 auto;white-space:nowrap}
#topbar .brand b{font-size:12.5px}
#topbar .line{flex:1;min-width:0;display:flex;align-items:baseline;gap:10px;
  overflow:hidden;white-space:nowrap}
#topbar .greet{font-size:13px;font-weight:700;flex:0 0 auto}
#topbar .oneline{font-size:11.5px;color:var(--dim);overflow:hidden;text-overflow:ellipsis}
#topbar .right{display:flex;gap:6px;flex:0 0 auto}
.barbtn{font:inherit;font-size:11.5px;background:var(--bg);color:var(--fg);cursor:pointer;
  border:1px solid var(--line);border-radius:7px;padding:5px 11px;white-space:nowrap}
.barbtn:hover{border-color:var(--accent);color:var(--accent)}
.barbtn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.barbtn[aria-expanded=true]{background:var(--line)}
.barbtn .caret{color:var(--faint);margin-left:5px}
.drop{position:fixed;top:46px;z-index:39;background:var(--hud);border:1px solid var(--line);
  border-top:0;border-radius:0 0 10px 10px;box-shadow:var(--shadow-lg);backdrop-filter:blur(8px);
  padding:14px 17px;display:none}
.drop.on{display:block}
#drop-overview{left:12px;width:min(46vw,560px)}
#drop-legend{right:12px;width:min(52vw,640px)}
#drop-overview .intro{font-size:11.5px;color:var(--dim);line-height:1.6;margin-bottom:10px}
#drop-overview h1{font-size:13.5px;line-height:1.4;padding:7px 10px;border-radius:6px;
  background:var(--tint-warn);border:1px solid var(--line);color:var(--fg)}
#drop-overview h1::before{content:"the verdict  ";font-size:10px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--warn);font-weight:700}
#drop-overview .hsub{font-size:11.5px;color:var(--dim);margin-top:9px;line-height:1.55}
.figs{display:flex;gap:5px;flex-wrap:wrap;margin-top:11px}
.fig{border:1px solid var(--line);background:var(--bg);border-radius:8px;padding:2px 8px;
  font-size:11px;color:var(--dim);white-space:nowrap}
.fig b{font-size:13px;font-variant-numeric:tabular-nums}
#drop-legend .row{display:flex;gap:7px;align-items:center;flex-wrap:wrap;font-size:11.5px}
#drop-legend .row+.row{margin-top:8px}
#drop-legend .k{color:var(--faint);width:78px;flex:0 0 auto;font-size:10.5px;
  text-transform:uppercase;letter-spacing:.06em}
#drop-legend .it{display:inline-flex;align-items:center;gap:5px;color:var(--dim);
  border:1px solid var(--line);background:var(--bg);border-radius:9px;padding:1px 8px}
#drop-legend i{width:7px;height:7px;border-radius:50%;display:block}
#drop-legend .shapes{margin-top:11px;padding-top:10px;border-top:1px solid var(--line);
  font-size:11.5px;color:var(--dim);display:flex;gap:14px;flex-wrap:wrap}
#drop-legend .shapes b{color:var(--fg)}
.controls{display:flex;gap:4px;flex:0 0 auto;padding-right:8px;margin-right:4px;
  border-right:1px solid var(--line)}
.controls button{font:inherit;font-size:11.5px;background:var(--bg);color:var(--fg);
  border:1px solid var(--line);border-radius:7px;padding:5px 10px;cursor:pointer}
.controls button:hover{border-color:var(--accent);color:var(--accent)}
.controls button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* ---------------- drawer ---------------- */
#drawer{position:fixed;top:0;right:0;height:100%;width:min(520px,94vw);z-index:40;
  background:var(--bg);border-left:1px solid var(--line);box-shadow:var(--shadow-lg);
  transform:translateX(100%);transition:transform .22s ease;overflow-y:auto;padding:20px 22px 60px}
#drawer.on{transform:none}
@media(prefers-reduced-motion:reduce){#drawer{transition:none}}
#drawer h2{font-size:15px;margin:26px 0 4px}
#drawer h2:first-of-type{margin-top:14px}
#drawer .lede{color:var(--dim);font-size:12px;margin:0 0 12px}
.closex{position:sticky;top:0;float:right;font:inherit;font-size:12px;background:var(--bg);
  border:1px solid var(--line);border-radius:6px;padding:5px 10px;cursor:pointer;color:var(--fg)}
.acts{display:flex;flex-direction:column;gap:10px}
.actrow{border:1px solid var(--line);border-radius:7px;padding:12px 14px;background:var(--panel)}
.actrow .rank{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em}
.actrow h3{font-size:13.5px;margin:4px 0 4px}
.actrow p{margin:0;color:var(--dim);font-size:12px;line-height:1.6}
.actrow button.cmd{margin-top:9px}
.tg{border:1px solid var(--line);border-radius:7px;padding:11px 13px;margin-bottom:8px;
  background:var(--panel)}
.tg .lab2{font-weight:700;font-size:12.5px}
.tg .det{font-size:11px;color:var(--faint);margin-top:2px}
.tg ul{margin:8px 0 7px;padding:0;list-style:none;display:flex;flex-wrap:wrap;gap:4px}
.tg li{font-size:11px;background:var(--sunk);border:1px solid var(--line);border-radius:9px;
  padding:1px 8px;color:var(--dim)}
.tg .nt{font-size:12px;color:var(--dim);margin:0;line-height:1.55}
.declist{list-style:none;padding:0;margin:0;border-left:1px solid var(--line)}
.declist li{padding:0 0 14px 18px;position:relative}
.declist li::before{content:"";position:absolute;left:-4.5px;top:7px;width:8px;height:8px;
  border-radius:50%;background:var(--bg);border:2px solid var(--dim)}
.declist li.moss::before{border-color:var(--accent)}
.declist li.amber::before{border-color:var(--warn)}
.declist li.violet::before{border-color:var(--live)}
.declist .d{font-size:10.5px;color:var(--faint)}
.declist .t{font-size:12.5px;line-height:1.6;margin-top:2px}
.method{list-style:none;padding:0;margin:0;display:grid;gap:7px}
.method li{font-size:12px;color:var(--dim);padding-left:15px;position:relative;line-height:1.55}
.method li::before{content:"\00b7";position:absolute;left:4px;color:var(--accent);font-weight:700}
</style>
<div id="app"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const esc = s => (s==null?"":String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
/* One glyph per state, reused at every depth so the eye learns it once. */
const GL = {done:'▣', unknown:'?', open:'□'};

function subs(list){
  if(!list || !list.length) return '';
  return '<div class="subs">'+list.map(function(s){
    return '<div class="sub '+s.state+'"><span class="gl">'+GL[s.state]+'</span>'
      + '<span>'+esc(s.text)+'</span></div>'; }).join('')+'</div>';
}
function tree(t){
  if(!t) return '';
  var h='';
  if(t.decisions && t.decisions.length){
    h += '<div class="decs"><span class="lab">decisions made along the way</span>'
      + t.decisions.map(function(d){
          return '<div class="dec-row"><span class="gl">◆</span><span>'+esc(d)+'</span></div>';
        }).join('')+'</div>';
  }
  if(t.tasks && t.tasks.length){
    const done=t.tasks.filter(function(x){return x.state==='done';}).length;
    h += '<div class="tasks-wrap"><span class="lab">tasks &middot; '+done+' of '+t.tasks.length
      + ' done</span><div class="tasks">'
      + t.tasks.map(function(k){
          return '<div class="task '+k.state+'"><div class="task-h">'
            + '<span class="gl">'+GL[k.state]+'</span><span>'+esc(k.text)+'</span>'
            + (k.ref?'<span class="ref">'+esc(k.ref)
                 + (k.date?'<b>'+esc(k.date)+'</b>':'')+'</span>':'<span></span>')+'</div>'
            + subs(k.subs)+'</div>'; }).join('')
      + '</div></div>';
  }
  return h;
}
function clock(w){
  const t=w.when; if(!t) return '';
  const hot = /m ago$/.test(t.ago) || /^[0-5]h/.test(t.ago);
  const cold = /d ago$/.test(t.ago) && parseInt(t.ago,10)>=5;
  return '<div class="clock"><span class="from">'+esc(t.opened)+'</span>'
   + '<span class="arrow">&rarr;</span><span class="to">'+esc(t.last)+'</span>'
   + (t.span?'<span>&middot; '+esc(t.span)+'</span>':'')
   + '<span class="ago'+(hot?' hot':cold?' cold':'')+'">'+esc(t.ago)+'</span></div>';
}
function card(w){
  const L=w.landing, S=w.session_state;
  return '<article class="card l-'+L.state+'" style="grid-column:'+w.gcol+' / span '+w.span+'" '
   + 'data-anchor="'+(w.anchor==null?'':w.anchor)+'">'
   + '<h3>'+esc(w.title)+'</h3>'
   + clock(w)
   /* Two independent questions, never collapsed into one badge: is the work in
      main, and is a session still running on it. */
   + '<div class="status"><span class="tag l-'+L.state+'">'+esc(L.label)+'</span>'
   + '<span class="tagdetail">'+esc(L.detail)+'</span></div>'
   + '<div class="status"><span class="tag s-'+S.state+'">'
   + (S.state==='live'?'<i class="dotlive"></i>':'')+esc(S.label)+'</span>'
   + (S.detail?'<span class="tagdetail">'+esc(S.detail)+'</span>':'')+'</div>'
   + '<div class="meta"><b>branch</b> '+esc(w.branch||'—')
   + (w.worktree?'<br><b>tree</b> '+esc(w.worktree)+(w.locked?' · locked':''):'')
   + (w.dirty?'<br><b>uncommitted</b> '+w.dirty.count+' file'+(w.dirty.count===1?'':'s')
       +' — '+esc(w.dirty.note):'')+'</div>'
   + (w.ask?'<div class="ask"><span class="lab">the prompt you gave</span><p>'
       + esc(w.ask)+'</p></div>':'')
   + tree(w.tree)
   + '<p class="verdict">'+esc(w.verdict)+'</p>'
   + '<p class="next">'+esc(w.next)+'</p>'
   + (w.act?'<div class="act"><div class="h">'+esc(w.act.label)+'</div>'
       + '<button class="cmd" data-cmd="'+esc(w.act.cmd)+'">'+esc(w.act.cmd)+'</button></div>':'')
   + '</article>';
}
/* Work that already landed needs no card — it needs a tombstone under the
   merge that absorbed it. */
function chip(w){
  return '<article class="chipcard" style="grid-column:'+w.gcol+' / span '+w.span+'" '
   + 'data-anchor="'+(w.anchor==null?'':w.anchor)+'"><h4>'+esc(w.title)+'</h4>'
   + '<div class="ln"><b>'+esc(w.landing.label)+'</b> '+esc(w.landing.detail)+'</div>'
   + '<div class="ln">'+esc(w.session_state.label)
   + (w.when?' &middot; last '+esc(w.when.last):'')+'</div>'
   + (w.resume?'<div class="act"><button class="cmd" data-cmd="'+esc(w.resume)
       +'">reopen the tab</button></div>':'')+'</article>';
}
function zone(n){ return D.workstreams.filter(function(w){return w.zone===n;})
  .map(n==='chip'?chip:card).join(''); }

document.getElementById('app').innerHTML =
 '<div id="shell"><div class="world" id="world"><svg class="wires" id="wires"></svg>'
 + '<div class="band open">'+zone('open')+'</div>'
 + '<div class="trunk" id="trunk"><div class="trunk-line"></div><div class="nodes">'
 + D.trunk.nodes.map(function(n,i){ return '<div class="node '+(n.head?'head':'')
     + '" data-i="'+i+'"><div class="dot"></div><div class="d">'+esc(n.date)+' · '
     + esc(n.sha)+'</div><div class="t">'+esc(n.title)+'</div></div>'; }).join('')
 + '</div></div>'
 + '<div class="band chips">'+zone('chip')+'</div>'
 + '<div class="band retired">'+zone('retired')+'</div></div></div>'

 + '<div id="topbar">'
 + '<div class="brand"><span class="lab">regroup</span><b>'+esc(D.repo)+'</b>'
 + '<span class="lab">'+esc(D.headline.asof)+'</span></div>'
 + '<div class="line"><span class="greet">'+esc(D.headline.greeting)+'</span>'
 + '<span class="oneline">'+esc(D.headline.oneline)+'</span></div>'
 + '<div class="right">'
 + '<div class="controls"><button id="zo">&minus;</button>'
 + '<button id="fitw">fit width</button><button id="fita">fit all</button>'
 + '<button id="zi">+</button></div>'
 + '<button class="barbtn" id="b-over" aria-expanded="false">overview<span class="caret">&#9662;</span></button>'
 + '<button class="barbtn" id="b-leg" aria-expanded="false">legend<span class="caret">&#9662;</span></button>'
 + '<button class="barbtn" id="b-draw">what to do &middot; '+D.actions.length+'</button>'
 + '</div></div>'

 + '<div class="drop" id="drop-overview">'
 + '<div class="intro">'+esc(D.headline.intro)+'</div>'
 + '<h1>'+esc(D.headline.verdict)+'</h1>'
 + '<div class="hsub">'+esc(D.headline.reassurance)+'</div>'
 + '<div class="figs">'+D.headline.stats.map(function(s){
     return '<span class="fig"><b class="t-'+s.tone+'">'+esc(s.n)+'</b> '+esc(s.label)+'</span>';
   }).join('')+'</div></div>'

 + '<div class="drop" id="drop-legend">'+D.legend.map(function(g){
     return '<div class="row"><span class="k">'+(g.k==='landing'?'in main?':'session?')+'</span>'
       + g.items.map(function(it){ return '<span class="it"><i style="background:var(--'
          + it.tone+')"></i>'+esc(it.text)+'</span>'; }).join('')+'</div>'; }).join('')
 + '<div class="shapes"><span><b>&ldquo; &rdquo;</b> the prompt you gave</span>'
 + '<span><b class="t-accent">&#9670;</b> a decision</span>'
 + '<span><b>&#9635;</b> task</span><span><b>&#9492; &#9633;</b> subtask</span>'
 + '<span>drag to pan &middot; scroll to zoom</span></div></div>'

 + '<aside id="drawer"><button class="closex" id="dclose">close</button>'
 + '<h2>What to do, in order</h2><p class="lede">Ranked by what is lost if you do nothing.</p>'
 + '<div class="acts">'+D.actions.map(function(a){
     return '<div class="actrow"><div class="rank t-'+a.tone+'">'+esc(a.rank)+'</div>'
       + '<h3>'+esc(a.title)+'</h3><p>'+esc(a.why)+'</p>'
       + (a.cmd?'<button class="cmd" data-cmd="'+esc(a.cmd)+'">'+esc(a.cmd)+'</button>':'')
       + '</div>'; }).join('')+'</div>'
 + '<h2>'+esc(D.worktree_state.title)+'</h2><p class="lede">'+esc(D.worktree_state.path)+'</p>'
 + D.worktree_state.groups.map(function(g){
     return '<div class="tg"><div class="lab2 t-'+g.tone+'">'+esc(g.label)+'</div>'
       + '<div class="det">'+esc(g.detail)+'</div><ul>'
       + g.files.map(function(f){return '<li>'+esc(f)+'</li>';}).join('')
       + '</ul><p class="nt">'+esc(g.note)+'</p></div>'; }).join('')
 + '<h2>Decisions that got made</h2><p class="lede">So they survive the sessions that made them.</p>'
 + '<ul class="declist">'+D.decisions.map(function(d){
     return '<li class="'+d.tone+'"><div class="d">'+esc(d.date)+'</div><div class="t">'
       + esc(d.text)+'</div></li>'; }).join('')+'</ul>'
 + '<h2>'+esc(D.method.title)+'</h2><p class="lede">Every number came from the machine.</p>'
 + '<ul class="method">'+D.method.items.map(function(m){return '<li>'+esc(m)+'</li>';}).join('')
 + '</ul></aside>';

/* ---- wires ---- */
function drawWires(){
  const world=document.getElementById('world'), svg=document.getElementById('wires');
  const wr=world.getBoundingClientRect(), sc=(world.__scale||1);
  function px(el){ const r=el.getBoundingClientRect();
    return {l:(r.left-wr.left)/sc, t:(r.top-wr.top)/sc, w:r.width/sc, h:r.height/sc}; }
  svg.setAttribute('width', world.scrollWidth); svg.setAttribute('height', world.scrollHeight);
  var o='';
  document.querySelectorAll('.card,.chipcard').forEach(function(c){
    const ai=c.dataset.anchor, cb=px(c);
    const isOpen=c.closest('.band').classList.contains('open');
    const x1=cb.l+cb.w/2, y1=isOpen?cb.t+cb.h:cb.t;
    /* The wire carries the landing answer, same as the card's top edge. */
    const col = c.classList.contains('l-unmerged')?'var(--danger)'
              : c.classList.contains('l-none')?'var(--dim)':'var(--accent)';
    if(ai===''){
      const tk=px(document.getElementById('trunk'));
      const y2=isOpen?tk.t+38:tk.t+70;
      o += '<path d="M'+x1+','+y1+' L'+x1+','+y2+'" stroke="'+col+'" stroke-width="1.5" '
        + 'fill="none" stroke-dasharray="3 5" opacity=".8"/>'
        + '<circle cx="'+x1+'" cy="'+y2+'" r="3.5" fill="var(--sunk)" stroke="'+col
        + '" stroke-width="1.5"/>';
      return;
    }
    const nd=document.querySelector('.node[data-i="'+ai+'"] .dot');
    if(!nd) return;
    const nb=px(nd), x2=nb.l+nb.w/2, y2=nb.t+nb.h/2;
    const my=isOpen?y1+(y2-y1)*0.55:y1-(y1-y2)*0.55;
    o += '<path d="M'+x1+','+y1+' C'+x1+','+my+' '+x2+','+my+' '+x2+','+y2+'" stroke="'+col
      + '" stroke-width="1.5" fill="none" '+(isOpen?'stroke-dasharray="4 4" ':'')+'opacity=".85"/>';
  });
  svg.innerHTML=o;
}

/* ---- pan + zoom ---- */
const shell=document.getElementById('shell'), world=document.getElementById('world');
var x=0,y=0,s=1; const MINS=0.16, MAXS=2.4;
function apply(){ world.__scale=s; world.style.transform='translate('+x+'px,'+y+'px) scale('+s+')'; }
function fitAll(){ const p=24, sw=world.scrollWidth, sh=world.scrollHeight;
  s=Math.min((shell.clientWidth-p*2)/sw,(shell.clientHeight-p*2)/sh,1.4);
  x=(shell.clientWidth-sw*s)/2; y=(shell.clientHeight-sh*s)/2; apply(); }
/* Default fills the width and lets the reader pan down: the cards carry real
   reading, and fitting the whole board shrinks them past legibility. */
function fitWidth(){ const p=24, sw=world.scrollWidth, sh=world.scrollHeight;
  s=Math.min((shell.clientWidth-p*2)/sw,1.4); x=p;
  y=(sh*s<shell.clientHeight)?(shell.clientHeight-sh*s)/2:p; apply(); }
var down=false,sx=0,sy=0;
shell.addEventListener('pointerdown',function(e){ if(e.target.closest('button')) return;
  down=true; sx=e.clientX-x; sy=e.clientY-y; shell.classList.add('drag');
  shell.setPointerCapture(e.pointerId); });
shell.addEventListener('pointermove',function(e){ if(!down) return;
  x=e.clientX-sx; y=e.clientY-sy; apply(); });
shell.addEventListener('pointerup',function(){ down=false; shell.classList.remove('drag'); });
shell.addEventListener('wheel',function(e){ e.preventDefault();
  const r=shell.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top;
  if(e.ctrlKey||Math.abs(e.deltaX)<1){
    const ns=Math.min(MAXS,Math.max(MINS,s*(e.deltaY<0?1.1:1/1.1)));
    x=mx-(mx-x)*(ns/s); y=my-(my-y)*(ns/s); s=ns;
  } else { x-=e.deltaX; y-=e.deltaY; }
  apply(); },{passive:false});
function zoom(f){ const cx=shell.clientWidth/2, cy=shell.clientHeight/2;
  const ns=Math.min(MAXS,Math.max(MINS,s*f)); x=cx-(cx-x)*(ns/s); y=cy-(cy-y)*(ns/s); s=ns; apply(); }
document.getElementById('zi').onclick=function(){zoom(1.22);};
document.getElementById('zo').onclick=function(){zoom(1/1.22);};
document.getElementById('fita').onclick=fitAll;
document.getElementById('fitw').onclick=fitWidth;
const drawer=document.getElementById('drawer');
/* Only one drop panel at a time, and both start closed: the canvas is the
   product, so chrome is opt-in. */
function drop(btnId, panelId){
  const b=document.getElementById(btnId), p=document.getElementById(panelId);
  b.onclick=function(){
    const open=!p.classList.contains('on');
    document.querySelectorAll('.drop').forEach(function(o){o.classList.remove('on');});
    document.querySelectorAll('.barbtn[aria-expanded]').forEach(function(o){
      o.setAttribute('aria-expanded','false');});
    if(open){ p.classList.add('on'); b.setAttribute('aria-expanded','true'); }
  };
}
drop('b-over','drop-overview'); drop('b-leg','drop-legend');
document.getElementById('b-draw').onclick=function(){drawer.classList.toggle('on');};
shell.addEventListener('pointerdown',function(){
  document.querySelectorAll('.drop').forEach(function(o){o.classList.remove('on');});
  document.querySelectorAll('.barbtn[aria-expanded]').forEach(function(o){
    o.setAttribute('aria-expanded','false');});
});
document.getElementById('dclose').onclick=function(){drawer.classList.remove('on');};
document.addEventListener('keydown',function(e){ if(e.key!=='Escape') return;
  drawer.classList.remove('on');
  document.querySelectorAll('.drop').forEach(function(o){o.classList.remove('on');});
  document.querySelectorAll('.barbtn[aria-expanded]').forEach(function(o){
    o.setAttribute('aria-expanded','false');});
});
document.addEventListener('click',function(e){
  const b=e.target.closest('button.cmd'); if(!b) return;
  const old=b.textContent;
  navigator.clipboard.writeText(b.dataset.cmd).then(function(){
    b.textContent='copied — paste it in a terminal'; b.classList.add('done');
    setTimeout(function(){ b.textContent=old; b.classList.remove('done'); },1800);
  });
});
function boot(){ drawWires(); fitWidth(); }
requestAnimationFrame(boot); setTimeout(boot,150);
if(document.fonts&&document.fonts.ready) document.fonts.ready.then(boot);
window.addEventListener('resize',function(){ drawWires(); fitWidth(); });
</script>
"""

out.write_text(HTML.replace("__DATA__", json.dumps(data)))
print("wrote " + str(out) + " (" + str(out.stat().st_size // 1024) + " KB)")
