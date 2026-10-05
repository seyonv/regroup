#!/usr/bin/env python3
"""regroup/render.py — draw the workstream canvas from regroup.json.

The page IS the canvas. Everything else floats over it in a small HUD.

Each workstream reads top to bottom as the thing you actually lost:
    your prompt  ->  decisions made  ->  tasks  ->  subtasks
Each of those has its own shape, so the hierarchy is legible before it is read.

Design follows the skill-receipts console system: warm neutrals, one green
accent, one rust danger, hairline rules, pill chips, monospace throughout.
"""

import html, json
import sys
from pathlib import Path

# Paths are resolved against the working directory, so `scripts/render.py
# example/regroup.json out.html` works from the repo root. Bare defaults fall
# back to sitting beside the script.
HERE = Path(__file__).parent

HTML = r"""<title>__TITLE__</title>
<style>
:root{
  --bg:#fbfbfa; --sunk:#f3f3f1; --panel:#ffffff; --hud:rgba(251,251,250,.93);
  --fg:#1a1a19; --dim:#6b6b68; --faint:#8f8d88; --line:#e4e4e1;
  --accent:#2f6f4f; --danger:#b5432d; --warn:#946a1f; --live:#5b4a8c; --cloud:#2563a8;
  --tint-accent:#eaf2ed; --tint-danger:#f8ebe8; --tint-warn:#f6efe1; --tint-live:#eeeaf5;
  --shadow:0 1px 2px rgba(0,0,0,.05); --shadow-lg:0 8px 34px -10px rgba(0,0,0,.22);
}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#161614; --sunk:#1c1c1a; --panel:#1f1f1c; --hud:rgba(22,22,20,.93);
  --fg:#eceae5; --dim:#9a978f; --faint:#7b7871; --line:#2c2a27;
  --accent:#7fc0a0; --danger:#e08a76; --warn:#d6a95c; --live:#a99ad6; --cloud:#79aee6;
  --tint-accent:#1a2a21; --tint-danger:#2e1c19; --tint-warn:#2c2418; --tint-live:#221d2e;
  --shadow:0 1px 2px rgba(0,0,0,.5); --shadow-lg:0 8px 34px -10px rgba(0,0,0,.8);
}}
:root[data-theme="dark"]{
  --bg:#161614; --sunk:#1c1c1a; --panel:#1f1f1c; --hud:rgba(22,22,20,.93);
  --fg:#eceae5; --dim:#9a978f; --faint:#7b7871; --line:#2c2a27;
  --accent:#7fc0a0; --danger:#e08a76; --warn:#d6a95c; --live:#a99ad6; --cloud:#79aee6;
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
.t-warn,.t-amber{color:var(--warn)} .t-live,.t-violet{color:var(--live)} .t-ink{color:var(--fg)} .t-cloud{color:var(--cloud)}

/* ---------------- the canvas is the page ---------------- */
#shell{position:fixed;top:46px;left:0;right:0;bottom:0;background:var(--sunk);overflow:hidden;cursor:grab;
  background-image:radial-gradient(var(--line) 1.2px,transparent 1.2px);background-size:24px 24px}
#shell.drag{cursor:grabbing}
/* Panning must never select text: a drag is a pan, and copy is a button. */
#shell{-webkit-user-select:none;user-select:none}
#shell .card,#shell .chipcard{cursor:zoom-in}
#shell .card.focus,#shell .chipcard.focus{cursor:zoom-out;outline:2px solid var(--fg);outline-offset:6px}
#shell.drag .card,#shell.drag .chipcard{cursor:grabbing}
.world.glide{transition:transform .32s cubic-bezier(.2,.7,.2,1)}
@media(prefers-reduced-motion:reduce){.world.glide{transition:none}}
.world{position:absolute;top:0;left:0;transform-origin:0 0;padding:34px;width:max-content}
.band{display:grid;grid-template-columns:repeat(var(--cols,8),214px);gap:0 26px}
.band.open{align-items:start}
.band.chips{align-items:start;margin-top:12px}
.band.retired{align-items:start;margin-top:24px}
.trunk{position:relative;height:172px;margin:36px 0 0;z-index:2}
.trunk-line{position:absolute;left:0;right:0;top:54px;height:2px;background:var(--accent);opacity:.5}
.nodes{position:absolute;inset:0;display:grid;grid-template-columns:repeat(var(--cols,8),1fr)}
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
/* Third axis, independent of the other two: where the session ran. */
.where{display:inline-flex;align-items:center;gap:6px;margin-bottom:9px;padding:3px 9px 3px 7px;
  border-radius:4px;background:var(--cloud);color:var(--bg);font-size:13px;font-weight:800;
  letter-spacing:.08em;text-transform:uppercase;line-height:1.4}
.where svg{width:18px;height:18px;flex:none}
.card.cloud,.chipcard.cloud{border-left:4px solid var(--cloud)}
.chipcard .where{font-size:10px;padding:2px 7px 2px 5px;margin-bottom:6px}
.where-link{color:var(--cloud);word-break:break-all}
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

/* ---------------- chips open in place ---------------- */
.chipcard .more{display:none}
.chipcard.open{width:454px;z-index:6;box-shadow:var(--shadow-lg);font-size:13px}
.chipcard.open h4{font-size:15px}
.chipcard.open .more{display:block;margin-top:10px;border-top:1px solid var(--line);padding-top:4px}
#wires path.donewire{opacity:.22}
#wires path.hot{stroke-width:3.2;opacity:1}
.node.hot .dot{box-shadow:0 0 0 5px var(--tint-accent)}

/* ---------------- ask Claude ---------------- */
/* The chat is docked beside the canvas, open from the start: the shell gives up
   its width rather than being covered by it. Below 760px it floats instead. */
:root{--chatw:400px}
#chat{position:fixed;top:46px;right:0;bottom:0;width:var(--chatw);z-index:39;background:var(--bg);
  border-left:1px solid var(--line);display:flex;flex-direction:column}
body.chat-on #shell{right:var(--chatw)}
@media(max-width:760px){:root{--chatw:100vw} body.chat-on #shell{right:0}
  #chat{box-shadow:var(--shadow-lg);top:auto;height:62vh;border-top:1px solid var(--line)}}
#chat[hidden]{display:none}
#chat .chead{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line)}
#chat .chead b{font-size:13px;flex:1;white-space:nowrap}
#chat .iconbtn{width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;
  background:var(--bg);color:var(--dim);border:1px solid var(--line);border-radius:7px;padding:0}
#chat .iconbtn:hover,#chat .iconbtn.on{color:var(--fg);border-color:var(--dim)}
#chat .iconbtn svg{width:15px;height:15px}
#clog .hist h4{margin:0 0 10px;font-size:12px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
#clog .hrow{display:block;width:100%;text-align:left;font:inherit;cursor:pointer;background:var(--panel);color:var(--fg);
  border:1px solid var(--line);border-radius:7px;padding:8px 10px;margin:0 0 7px}
#clog .hrow:hover,#clog .hrow.cur{border-color:var(--dim)}
#clog .hrow small{display:block;color:var(--dim);font-size:11px;margin-top:3px}
#chat .gpill{font-size:10.5px;padding:2px 8px;border-radius:10px;border:1px solid var(--line);color:var(--dim);white-space:nowrap}
#chat .gpill.on{color:var(--accent);border-color:var(--accent)}
#clog{flex:1;overflow-y:auto;overflow-wrap:anywhere;padding:14px 16px;display:flex;flex-direction:column;gap:14px;font-size:13px;line-height:1.6}
#clog .cempty{color:var(--dim);font-size:12.5px}
#clog .cempty p{margin:0 0 10px}
#clog .sugg{display:block;width:100%;text-align:left;margin:0 0 7px;font:inherit;font-size:12.5px;cursor:pointer;
  background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:8px 10px}
#clog .sugg:hover{border-color:var(--dim)}
.msg.me{align-self:flex-end;max-width:88%;background:var(--sunk);border:1px solid var(--line);border-radius:9px;
  padding:7px 11px;white-space:pre-wrap}
.msg.ai{min-width:0}
.msg.ai .acts2{display:flex;flex-direction:column;gap:3px;margin-bottom:6px}
.msg.ai .acts2 span{font-size:11.5px;color:var(--dim)}
.msg.ai .acts2 span::before{content:"\25B8 ";color:var(--cloud)}
.msg.ai .body p{margin:0 0 8px} .msg.ai .body ul{margin:0 0 8px;padding-left:18px}
.msg.ai .body code{background:var(--sunk);border:1px solid var(--line);border-radius:4px;padding:0 4px;font-size:12px}
.msg.ai .body pre{background:var(--sunk);border:1px solid var(--line);border-radius:6px;padding:8px 10px;
  overflow-x:auto;font-size:12px;margin:0 0 8px}
.msg.ai .body pre code{border:0;padding:0;background:none}
.msg.ai .wait{color:var(--dim)}
.msg.ai .err{color:var(--danger);font-size:12px}
#cform{border-top:1px solid var(--line);padding:10px 16px 14px;display:flex;flex-direction:column;gap:8px}
#cin{font:inherit;font-size:13px;resize:none;border:1px solid var(--line);border-radius:8px;padding:8px 10px;
  background:var(--panel);color:var(--fg);min-height:58px}
#cin:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
#cform .crow{display:flex;align-items:center;gap:10px;font-size:11.5px;color:var(--dim)}
#cform .crow label{flex:1;display:flex;align-items:center;gap:6px;cursor:pointer}
#cform .crow button{font:inherit;font-size:12px;padding:5px 14px;border-radius:7px;cursor:pointer;
  border:1px solid var(--fg);background:var(--fg);color:var(--bg)}
#cform .crow button#cstop{background:var(--bg);color:var(--fg)}
#cform .crow button:disabled{opacity:.45;cursor:default}

/* ---------------- live: the board notices what you've done ----------------
   Status changes are applied in place: no reload, no camera move. A card that
   is finished dims and takes a stamp; whatever just changed pulses once. */
/* Done = a closed loop: kept for context, not something to act on. It must read
   as closed at a glance and stay that way when opened, so it is marked three
   ways: a hatched ground, a solid stamp, and strike-through on the title, the
   next step and the command. Its wire fades too. */
.donestamp{display:none;font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;
  color:var(--bg);background:var(--accent);border-radius:4px;padding:3px 9px;margin-bottom:8px}
.done>.donestamp,.done>div>.donestamp{display:inline-block}
.card.done,.chipcard.done{
  background:repeating-linear-gradient(135deg,var(--panel) 0 9px,var(--sunk) 9px 18px);
  border-color:var(--line);border-top-color:var(--faint);opacity:.6;transition:opacity .35s}
.chipcard.done{border-left-color:var(--faint)}
.card.done:hover,.chipcard.done:hover,.card.done.focus,.chipcard.done.open{opacity:.92}
.done>h3,.done>h4{text-decoration:line-through;text-decoration-thickness:2px;color:var(--dim)}
.done .next,.done .verdict{color:var(--dim)}
.done .next{text-decoration:line-through}
.done button.cmd{text-decoration:line-through;color:var(--faint)}
.done .ask,.done .task,.done .dec-row{background:transparent}
.actrow.done{opacity:.6}
.actrow.done h3{text-decoration:line-through;text-decoration-thickness:2px;color:var(--dim)}
.actrow.done button.cmd{text-decoration:line-through;color:var(--faint)}
.actrow.done p{display:none}
.actrow .tick{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;color:var(--dim);margin-top:6px;cursor:pointer}
@keyframes livepulse{0%{box-shadow:0 0 0 0 var(--accent)}100%{box-shadow:0 0 0 16px transparent}}
.flash{animation:livepulse 1.1s ease-out 2}
@media(prefers-reduced-motion:reduce){.flash{animation:none}}
#b-live{border-color:var(--accent);color:var(--accent)}
#b-live i{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);margin-right:6px;vertical-align:1px}
#b-live.busy i{animation:livebeat .8s ease-in-out infinite}
@keyframes livebeat{50%{opacity:.25}}
#b-new{border-color:var(--warn);color:var(--warn)}
#drop-new ul{margin:6px 0 10px;padding-left:18px;line-height:1.7}

/* ---------------- run (local) ---------------- */
.runbtn.inline{margin:0 0 0 6px;padding:1px 9px;vertical-align:1px}
pre+.runbtn.inline{margin:0 0 8px}
.msg.ai .confirm,.msg.ai .runout{margin:6px 0 8px}
.runbtn{font:inherit;font-size:11px;margin-top:6px;padding:3px 12px;border-radius:6px;cursor:pointer;
  background:var(--bg);color:var(--accent);border:1px solid var(--accent)}
.runbtn.risky{color:var(--danger);border-color:var(--danger)}
.confirm{margin-top:8px;padding:9px 11px;border:1px solid var(--line);border-radius:7px;background:var(--sunk);
  display:flex;flex-direction:column;gap:7px;font-size:12px;cursor:default}
.confirm code{word-break:break-all;font-size:11.5px}
.confirm .btns{display:flex;gap:8px}
.confirm button{font:inherit;font-size:11.5px;padding:4px 14px;border-radius:6px;cursor:pointer;
  border:1px solid var(--line);background:var(--panel);color:var(--fg)}
.confirm button.go{background:var(--accent);border-color:var(--accent);color:var(--bg)}
.confirm button.go.risky{background:var(--danger);border-color:var(--danger)}
.confirm .running{color:var(--dim)}
.runout{margin-top:8px;border:1px solid var(--line);border-radius:7px;padding:8px 10px;font-size:11.5px;cursor:default}
.runout .h{font-weight:700} .runout.ok .h{color:var(--accent)} .runout.bad .h{color:var(--danger)}
.runout pre{margin:6px 0 0;max-height:180px;overflow:auto;white-space:pre-wrap;font-size:11px;color:var(--dim)}
.done .runbtn,.done .confirm{display:none}
#b-live.gone{border-color:var(--danger);color:var(--danger)} #b-live.gone i{background:var(--danger)}

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
    h += '<div class="tasks-wrap"><span class="lab tcount">tasks &middot; '+done+' of '+t.tasks.length
      + ' done</span><div class="tasks">'
      + t.tasks.map(function(k,i){
          return '<div class="task '+k.state+'" data-k="'+i+'"><div class="task-h">'
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
const CLOUD_SVG='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M17.5 19H7a5 5 0 1 1 1.1-9.9A6 6 0 0 1 19.6 11 4 4 0 0 1 17.5 19z"/></svg>';
function where(w){ return w.runtime==='cloud'
  ? '<div><span class="where">'+CLOUD_SVG+'Claude Code cloud</span></div>' : ''; }
function body(w){
  return (w.ask?'<div class="ask"><span class="lab">the prompt you gave</span><p>'
       + esc(w.ask)+'</p></div>':'')
   + tree(w.tree)
   + (w.verdict?'<p class="verdict">'+esc(w.verdict)+'</p>':'')
   + (w.next?'<p class="next">'+esc(w.next)+'</p>':'')
   + (w.act?'<div class="act"><div class="h">'+esc(w.act.label)+'</div>'
       + '<button class="cmd" data-cmd="'+esc(w.act.cmd)+'">'+esc(w.act.cmd)+'</button></div>':'');
}
/* A closed loop is context, not work: chips and finished lanes are closed by
   default (unless "closed": false); "closed": true closes any card. Cards with
   live "done" checks are closed by the live layer instead. */
function closed(w){ if(w.done&&w.done.length) return false;
  return w.closed===true||(w.closed!==false&&(w.zone==='chip'||w.zone==='retired')); }
function card(w){
  const L=w.landing, S=w.session_state;
  return '<article class="card l-'+L.state+(w.runtime==='cloud'?' cloud':'')+(closed(w)?' done':'')+'" style="grid-column:'+w.gcol+' / span '+w.span+'" '
   + 'data-id="'+esc(w.id)+'" data-anchor="'+(w.anchor==null?'':w.anchor)+'">'
   + where(w)
   + '<span class="donestamp">&#10003; Done &middot; closed loop, kept for context</span>'
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
   + (w.cloud_url?'<br><b>session</b> <a class="where-link" href="'+esc(w.cloud_url)+'">'+esc(w.cloud_url.replace('https://',''))+'</a>':'')
   + (w.worktree?'<br><b>tree</b> '+esc(w.worktree)+(w.locked?' · locked':''):'')
   + (w.dirty?'<br><b>uncommitted</b> '+w.dirty.count+' file'+(w.dirty.count===1?'':'s')
       +' — '+esc(w.dirty.note):'')+'</div>'
   + body(w)
   + '</article>';
}
/* Work that already landed needs no card — it needs a tombstone under the
   merge that absorbed it. */
function chip(w){
  return '<article class="chipcard'+(w.runtime==='cloud'?' cloud':'')+(closed(w)?' done':'')+'" style="grid-column:'+w.gcol+' / span '+w.span+'" '
   + 'data-id="'+esc(w.id)+'" data-anchor="'+(w.anchor==null?'':w.anchor)+'">'+where(w)+'<span class="donestamp">&#10003; done</span><h4>'+esc(w.title)+'</h4>'
   + '<div class="ln"><b>'+esc(w.landing.label)+'</b> '+esc(w.landing.detail)+'</div>'
   + '<div class="ln">'+esc(w.session_state.label)
   + (w.when?' &middot; last '+esc(w.when.last):'')+'</div>'
   /* The whole card body rides along hidden; clicking the chip opens it. */
   + '<div class="more">'+body(w)+'</div></article>';
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
 + '<button class="barbtn" id="b-new" hidden aria-expanded="false"></button>'
 + '<button class="barbtn" id="b-live" hidden title="Checks your repo when you come back to this page. Click to check now."><i></i>live</button>'
 + '<button class="barbtn" id="b-ask" hidden aria-pressed="true">chat</button>'
 + '</div></div>'

 + '<div class="drop" id="drop-overview">'
 + '<div class="intro">'+esc(D.headline.intro)+'</div>'
 + '<h1>'+esc(D.headline.verdict)+'</h1>'
 + '<div class="hsub">'+esc(D.headline.reassurance)+'</div>'
 + '<div class="figs">'+D.headline.stats.map(function(s){
     return '<span class="fig"><b class="t-'+s.tone+'">'+esc(s.n)+'</b> '+esc(s.label)+'</span>';
   }).join('')+'</div></div>'

 + '<div class="drop" id="drop-legend">'+D.legend.map(function(g){
     return '<div class="row"><span class="k">'+({landing:'in main?',session:'session?',runtime:'ran in?'}[g.k]||g.k)+'</span>'
       + g.items.map(function(it){ return '<span class="it"><i style="background:var(--'
          + it.tone+')"></i>'+esc(it.text)+'</span>'; }).join('')+'</div>'; }).join('')
 + '<div class="shapes"><span><b>&ldquo; &rdquo;</b> the prompt you gave</span>'
 + '<span><b class="t-accent">&#9670;</b> a decision</span>'
 + '<span><b>&#9635;</b> task</span><span><b>&#9492; &#9633;</b> subtask</span>'
 + '<span>click a card to read it &middot; click again or Esc to go back &middot; drag to pan &middot; scroll to zoom</span></div></div>'

 + '<div class="drop" id="drop-new"></div>'
 + '<aside id="chat" hidden aria-label="Ask about this board"><div class="chead"><b>Ask about this board</b>'
 + '<span class="gpill" id="gitstate">git: checking</span>'
 + '<button class="iconbtn" id="chist" hidden title="Past chats" aria-label="Past chats"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/></svg></button>'
 + '<button class="iconbtn" id="cnew" hidden title="New chat" aria-label="New chat"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg></button>'
 + '<button class="closex" id="cclose">hide</button></div>'
 + '<div id="clog"></div>'
 + '<form id="cform"><textarea id="cin" rows="2" placeholder="Ask about a branch, a session, what to land…"></textarea>'
 + '<div class="crow"><label><input type="checkbox" id="cdeep"> think longer</label>'
 + '<button type="button" id="cstop" hidden>stop</button><button type="submit" id="csend">send</button></div></form></aside>'
 + '<aside id="drawer"><button class="closex" id="dclose">close</button>'
 + '<h2>What to do, in order</h2><p class="lede">Ranked by what is lost if you do nothing.</p>'
 + '<div class="acts">'+D.actions.map(function(a){
     return '<div class="actrow" data-i="'+D.actions.indexOf(a)+'"><div class="rank t-'+a.tone+'">'+esc(a.rank)+'</div>'
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
  /* Wires from the lowest band must climb past the chips. Run them up a
     column gutter, never behind a chip, or a chip looks connected to the card
     below it. */
  const chipBand=document.querySelector('.band.chips');
  const chipRects=[].map.call(document.querySelectorAll('.chipcard'),px);
  var gutters=[];
  if(chipBand&&chipRects.length){
    const cb0=px(chipBand), cols=parseInt(getComputedStyle(document.documentElement).getPropertyValue('--cols'))||8;
    for(var k=0;k<=cols;k++){ const gx=cb0.l+k*240-13;
      if(!chipRects.some(function(r){return gx>r.l-4&&gx<r.l+r.w+4;})) gutters.push(gx); }
    var chipTop=Math.min.apply(null,chipRects.map(function(r){return r.t;})),
        chipBot=Math.max.apply(null,chipRects.map(function(r){return r.t+r.h;}));
  }
  document.querySelectorAll('.card,.chipcard').forEach(function(c,wi){
    c.dataset.w=wi;
    const ai=c.dataset.anchor, cb=px(c);
    const isOpen=c.closest('.band').classList.contains('open');
    const x1=cb.l+cb.w/2, y1=isOpen?cb.t+cb.h:cb.t;
    /* The wire carries the landing answer, same as the card's top edge. */
    const fade=c.classList.contains('done')?' class="donewire"':'';
    const col = c.classList.contains('l-unmerged')?'var(--danger)'
              : c.classList.contains('l-none')?'var(--dim)':'var(--accent)';
    if(ai===''){
      const tk=px(document.getElementById('trunk'));
      const y2=isOpen?tk.t+38:tk.t+70;
      o += '<path'+fade+' data-w="'+wi+'" d="M'+x1+','+y1+' L'+x1+','+y2+'" stroke="'+col+'" stroke-width="1.5" '
        + 'fill="none" stroke-dasharray="3 5" opacity=".8"/>'
        + '<circle cx="'+x1+'" cy="'+y2+'" r="3.5" fill="var(--sunk)" stroke="'+col
        + '" stroke-width="1.5"/>';
      return;
    }
    const nd=document.querySelector('.node[data-i="'+ai+'"] .dot');
    if(!nd) return;
    const nb=px(nd), x2=nb.l+nb.w/2, y2=nb.t+nb.h/2;
    const my=isOpen?y1+(y2-y1)*0.55:y1-(y1-y2)*0.55;
    if(c.closest('.band.retired')&&gutters.length){
      const g=gutters.reduce(function(a,b){return Math.abs(b-x2)<Math.abs(a-x2)?b:a;});
      const yB=chipBot+12, yT=chipTop-14, m2=yT-(yT-y2)*0.55;
      o += '<path'+fade+' data-w="'+wi+'" d="M'+x1+','+y1+' L'+x1+','+yB+' L'+g+','+yB+' L'+g+','+yT
        + ' C'+g+','+m2+' '+x2+','+m2+' '+x2+','+y2+'" stroke="'+col
        + '" stroke-width="1.5" stroke-linejoin="round" fill="none" opacity=".85"/>';
      return;
    }
    o += '<path'+fade+' data-w="'+wi+'" d="M'+x1+','+y1+' C'+x1+','+my+' '+x2+','+my+' '+x2+','+y2+'" stroke="'+col
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
/* Click a card to fly to it at reading size; click it again, click empty canvas
   or press Esc to fly back. A press that moves more than a few pixels is a pan,
   never a click. Manual zoom or pan after focusing forgets the way back. */
var focused=null, back=null;
function glide(){ world.classList.add('glide'); clearTimeout(glide.t);
  glide.t=setTimeout(function(){ world.classList.remove('glide'); },360); }
function focusCard(c){
  /* Layout offsets, not getBoundingClientRect: mid-glide the screen rect is
     an in-between frame and would send the camera to the wrong place. */
  var wx=0, wy=0, el=c, p=28;
  while(el&&el!==world){ wx+=el.offsetLeft; wy+=el.offsetTop; el=el.offsetParent; }
  const cw=c.offsetWidth, ch=c.offsetHeight;
  if(!focused) back={x:x,y:y,s:s};
  if(focused&&focused!==c){ focused.classList.remove('focus','open'); }
  if(c.classList.contains('chipcard')&&!c.classList.contains('open')){ c.classList.add('open'); drawWires(); }
  const fitW=(shell.clientWidth-p*2)/cw, fitH=(shell.clientHeight-p*2)/ch;
  /* Tall cards keep a readable size and start at their top; wheel pans the rest. */
  const ns=Math.min(MAXS,Math.max(Math.min(fitW,fitH),Math.min(fitW,1.15)),1.8);
  s=ns; x=(shell.clientWidth-cw*s)/2-wx*s;
  y=(ch*s<=shell.clientHeight-p*2)?(shell.clientHeight-ch*s)/2-wy*s:p-wy*s;
  focused=c; c.classList.add('focus'); glide(); apply();
}
function unfocus(restore){
  if(!focused) return;
  const wasOpen=focused.classList.contains('open');
  focused.classList.remove('focus','open'); focused=null;
  if(wasOpen) drawWires();
  if(restore&&back){ x=back.x; y=back.y; s=back.s; glide(); apply(); }
  back=null;
}
function forgetBack(){ back=null; }
var down=false,moved=false,sx=0,sy=0,ox=0,oy=0,downOn=null;
shell.addEventListener('pointerdown',function(e){ if(e.target.closest('button,a,.confirm,.runout')) return;
  e.preventDefault();
  down=true; moved=false; ox=e.clientX; oy=e.clientY; sx=e.clientX-x; sy=e.clientY-y;
  downOn=e.target.closest('.card,.chipcard');
  const sel=window.getSelection&&window.getSelection(); if(sel) sel.removeAllRanges();
  shell.setPointerCapture(e.pointerId); });
shell.addEventListener('pointermove',function(e){ if(!down) return;
  if(!moved&&Math.abs(e.clientX-ox)+Math.abs(e.clientY-oy)<5) return;
  if(!moved){ moved=true; shell.classList.add('drag'); forgetBack(); }
  x=e.clientX-sx; y=e.clientY-sy; apply(); });
shell.addEventListener('pointerup',function(){
  if(down&&!moved){
    if(downOn&&downOn!==focused) focusCard(downOn);
    else unfocus(true);
  }
  down=false; moved=false; downOn=null; shell.classList.remove('drag'); });
shell.addEventListener('wheel',function(e){ e.preventDefault(); forgetBack();
  const r=shell.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top;
  if(e.ctrlKey||Math.abs(e.deltaX)<1){
    const ns=Math.min(MAXS,Math.max(MINS,s*(e.deltaY<0?1.1:1/1.1)));
    x=mx-(mx-x)*(ns/s); y=my-(my-y)*(ns/s); s=ns;
  } else { x-=e.deltaX; y-=e.deltaY; }
  apply(); },{passive:false});
function zoom(f){ const cx=shell.clientWidth/2, cy=shell.clientHeight/2;
  const ns=Math.min(MAXS,Math.max(MINS,s*f)); x=cx-(cx-x)*(ns/s); y=cy-(cy-y)*(ns/s); s=ns; apply(); }
document.getElementById('zi').onclick=function(){forgetBack();zoom(1.22);};
document.getElementById('zo').onclick=function(){forgetBack();zoom(1/1.22);};
document.getElementById('fita').onclick=function(){unfocus(false);glide();fitAll();};
document.getElementById('fitw').onclick=function(){unfocus(false);glide();fitWidth();};
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
/* Hover a card: its wire and its merge on main light up, so what connects to
   what is never a guess. */
shell.addEventListener('mouseover',function(e){
  const c=e.target.closest('.card,.chipcard');
  document.querySelectorAll('#wires path.hot,.node.hot').forEach(function(n){n.classList.remove('hot');});
  if(!c||down) return;
  const pth=document.querySelector('#wires path[data-w="'+c.dataset.w+'"]'); if(pth) pth.classList.add('hot');
  const nd=document.querySelector('.node[data-i="'+c.dataset.anchor+'"]'); if(c.dataset.anchor!==''&&nd) nd.classList.add('hot');
});
document.addEventListener('keydown',function(e){ if(e.key!=='Escape') return;
  unfocus(true);
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
function boot(){
  document.documentElement.style.setProperty('--cols', D.trunk.nodes.length || 8);
  drawWires(); fitWidth();
}
requestAnimationFrame(boot); setTimeout(boot,150);
if(document.fonts&&document.fonts.ready) document.fonts.ready.then(boot);
window.addEventListener('resize',function(){ drawWires(); if(focused) focusCard(focused); else fitWidth(); });

/* ---- local mode: served by serve.py, which hands the page a token ----
   Everything the artifact does through claude.use() goes to the local server
   instead: probe, chat, and running the board's own commands. */
const LOCAL=window.REGROUP_LOCAL||null;
function api(path,body,signal){
  return fetch(path,{method:'POST',signal:signal,headers:{'Content-Type':'application/json','X-Regroup-Token':LOCAL.token},
    body:JSON.stringify(body||{})});
}

/* ---- run: the board's own commands, from the page (local only) ----
   Each runnable command gets a run button. Running always goes through an
   inline confirm that shows the exact command; the server refuses anything
   that is not on the board. Afterwards the board re-checks the repo at once. */
(function(){
  if(!LOCAL) return;
  function interactive(c){ return /^claude /.test(c)||/\| *(less|more)\b/.test(c); }
  function risky(c){ return /\bkill\b|branch -D|--delete|worktree remove|reset --hard|--force|\brm\b/.test(c); }
  document.querySelectorAll('button.cmd').forEach(function(b){
    const c=b.dataset.cmd; if(!c||interactive(c)) return;
    const r=document.createElement('button'); r.type='button'; r.className='runbtn'+(risky(c)?' risky':''); r.textContent='run';
    b.insertAdjacentElement('afterend',r);
  });
  document.addEventListener('click',async function(e){
    const r=e.target.closest('button.runbtn'); const go=e.target.closest('.confirm .go'), no=e.target.closest('.confirm .no');
    if(r){ const c=r.dataset.cmd||r.previousElementSibling.dataset.cmd, host=r.parentNode;
      host.querySelectorAll('.confirm,.runout').forEach(function(x){x.remove();});
      r.insertAdjacentHTML('afterend','<div class="confirm"><span>Run in <b>'+esc(D.repo)+'</b>:</span><code>'+esc(c)+'</code>'
        +'<span class="btns"><button type="button" class="go'+(risky(c)?' risky':'')+'">Run</button><button type="button" class="no">Cancel</button></span></div>');
      host.querySelector('.confirm .go').focus(); return; }
    if(no){ no.closest('.confirm').remove(); return; }
    if(go){ const box=go.closest('.confirm'), c=box.querySelector('code').textContent;
      box.innerHTML='<span class="running">Running <code>'+esc(c)+'</code>…</span>';
      var out;
      try{ const res=await api('/api/run',{cmd:c}); out=await res.json();
        if(res.status===403) out={code:-1,out:'This page is from an older start of the regroup server. Reload the page once, then run it again. Nothing was run.'};
        else if(!res.ok) out={code:-1,out:(out.error||('server '+res.status))+'. Nothing was run.'}; }
      catch(err){ out={code:-1,out:'The regroup server isn\'t running. Run /regroup to start it again.'}; }
      box.outerHTML='<div class="runout '+(out.code===0?'ok':'bad')+'"><div class="h">'
        +(out.code===0?'&#10003; done'+(out.ms!=null?' in '+out.ms+' ms':''):'&#10007; exit '+out.code)+'</div>'
        +(out.out&&out.out.trim()?'<pre>'+esc(out.out.trim())+'</pre>':'')+'</div>';
      if(window.__regroupLive&&window.__regroupLive.probeNow) window.__regroupLive.probeNow();
    }
  });
})();

/* ---- live: watch the repo and update the board in place ----
   A local read-only MCP server (host:regroup, tool `probe`, ~60 ms) answers what
   is true now. Each action and workstream carries "done" checks; the page
   evaluates them and toggles classes and labels on the existing elements. It
   checks on load, the moment the viewer comes back to the page (focus,
   visibility, first pointer move after a pause), and every 30 s while open.
   Never a reload, never a camera move. */
(function(){
  const liveBtn=document.getElementById('b-live'), newBtn=document.getElementById('b-new'),
        newDrop=document.getElementById('drop-new'), drawBtn=document.getElementById('b-draw');
  const K=D.known||null, KEY='regroup-done:'+D.repo+':'+D.generated;
  /* Manual ticks are keyed by the action's title, not its position, so they
     survive actions being split or reordered. Local boards keep them on disk
     beside the board (marks.json); an artifact keeps them in this browser. */
  var manual={}; if(!LOCAL){ try{ manual=JSON.parse(localStorage.getItem(KEY)||'{}'); }catch(e){} }
  function saveMark(title,on){
    if(on) manual[title]=Date.now(); else delete manual[title];
    if(LOCAL) api('/api/marks',{title:title,done:on}).catch(function(){});
    else { try{ localStorage.setItem(KEY,JSON.stringify(manual)); }catch(err){} }
  }
  var last=null, lastAt=0, inflight=false, mcp=null, hostOK=false, seen={}, applied=0;
  function chk(c,p){
    if(c.any) return c.any.some(function(x){return chk(x,p);});
    if('pushed' in c) return p.ahead===0;
    if(c.branch_gone) return !(c.branch_gone in p.branches);
    if(c.remote_gone) return !(c.remote_gone in p.remote_branches);
    if(c.worktree_gone) return !p.worktrees.some(function(w){return w.path===c.worktree_gone;});
    if(c.pid_gone) return p.alive.indexOf(c.pid_gone)<0;
    if(c.on_main) return p.on_main.indexOf(c.on_main)>=0;
    if(c.path_on_main) return (p.paths_on_main||[]).indexOf(c.path_on_main)>=0;
    if(c.answered) return !!(p.turns&&p.turns[c.answered]&&p.turns[c.answered].answered);
    if(c.pr_merged) return !!(p.prs&&p.prs[c.pr_merged]&&p.prs[c.pr_merged].state==='MERGED');
    return false;
  }
  function all(list,p){ return !!(p&&list&&list.length&&list.every(function(c){return chk(c,p);})); }
  function walk(list,fn){ (list||[]).forEach(function(c){ if(c.any) walk(c.any,fn); else fn(c); }); }
  const pids=[], subjects=[], paths=[];
  /* A card's session: session_id, or the uuid in its `claude --resume` command. */
  function sid(w){ if(w.session_id) return w.session_id;
    const m=((w.act&&w.act.cmd)||'').match(/--resume\s+([0-9a-f-]{36})/); return m?m[1]:''; }
  const sessions=[];
  function gather(list){ walk(list,function(c){ if(c.pid_gone&&pids.indexOf(c.pid_gone)<0) pids.push(c.pid_gone);
    if(c.answered&&sessions.indexOf(c.answered)<0) sessions.push(c.answered);
    if(c.on_main&&subjects.indexOf(c.on_main)<0) subjects.push(c.on_main);
    if(c.path_on_main&&paths.indexOf(c.path_on_main)<0) paths.push(c.path_on_main); }); }
  D.actions.forEach(function(a){ gather(a.done); });
  D.workstreams.forEach(function(w){ gather(w.done); (w.live||[]).forEach(function(r){ gather(r.when); });
    ((w.tree&&w.tree.tasks)||[]).forEach(function(k){ gather(k.done); });
    if(w.pid&&pids.indexOf(w.pid)<0) pids.push(w.pid);
    if(w.pid&&sid(w)&&sessions.indexOf(sid(w))<0) sessions.push(sid(w)); });
  const INPUT={repo_path:D.repo_path,pids:pids,subjects:subjects,paths:paths,sessions:sessions};

  /* Pulse only what changes while the page is open; the first check just sets
     the scene. */
  function hhmm(iso){ const d=new Date(iso); return isNaN(d)?'?':String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'); }
  function pulse(el){ if(!applied) return; el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }
  function flash(el,key,now){ if(seen[key]!==undefined&&seen[key]!==now) pulse(el); seen[key]=now; }
  function setTag(el,cls,state,label,detail){
    const t=el.querySelector('.tag.'+cls+'-'+'unmerged,.tag.'+cls+'-merged,.tag.'+cls+'-none,.tag.'+cls+'-live,.tag.'+cls+'-idle,.tag.'+cls+'-closed');
    if(!t) return false;
    const before=t.className+'|'+t.textContent;
    t.className='tag '+cls+'-'+state; t.textContent=label;
    const d=t.parentNode.querySelector('.tagdetail'); if(d&&detail!=null) d.textContent=detail;
    return before!==t.className+'|'+t.textContent;
  }
  function apply(p){
    last=p; lastAt=Date.now(); var rewire=false, remaining=0;
    D.actions.forEach(function(a,i){
      const row=document.querySelector('.actrow[data-i="'+i+'"]'); if(!row) return;
      const done=all(a.done,p)||!!manual[a.title];
      row.classList.toggle('done',done); if(!done) remaining++;
      if(a.done&&a.done.length) flash(row,'a'+i,done);
    });
    drawBtn.innerHTML='what to do &middot; '+(remaining?remaining+' left':'all done');
    D.workstreams.forEach(function(w){
      const el=document.querySelector('[data-id="'+w.id+'"]'); if(!el) return;
      (w.live||[]).forEach(function(r){
        if(!all(r.when,p)||!r.landing) return;
        if(el.classList.contains('card')){
          if(setTag(el,'l',r.landing.state,r.landing.label,r.landing.detail)){ rewire=true;
            el.classList.remove('l-unmerged','l-merged','l-none'); el.classList.add('l-'+r.landing.state); pulse(el); }
        } else { const b=el.querySelector('.ln b'); if(b) b.textContent=r.landing.label; }
      });
      /* Tasks with live checks tick themselves (an in-flight question gets
         {"answered": uuid}), and the count above them follows. */
      const tasks=(w.tree&&w.tree.tasks)||[];
      if(tasks.some(function(k){return k.done&&k.done.length;})){
        var n=0;
        tasks.forEach(function(k,i){
          const row=el.querySelector('.task[data-k="'+i+'"]');
          const st=(k.done&&k.done.length&&all(k.done,p))?'done':k.state;
          if(st==='done') n++;
          if(!row||row.classList.contains(st)) return;
          row.classList.remove('done','unknown','open'); row.classList.add(st);
          row.querySelector('.gl').textContent=GL[st]; pulse(row); });
        const c=el.querySelector('.tcount'); if(c) c.innerHTML='tasks &middot; '+n+' of '+tasks.length+' done';
      }
      const gone=w.pid&&p.alive.indexOf(w.pid)<0, turn=p.turns&&p.turns[sid(w)];
      if(gone&&el.classList.contains('card'))
        if(setTag(el,'s','closed','Session closed','pid '+w.pid+' has exited')) pulse(el);
      /* Running is not working: a session whose last prompt has its answer is
         waiting on you, whatever the board said when it was built. */
      if(!gone&&w.pid&&turn&&el.classList.contains('card'))
        if(turn.answered) { if(setTag(el,'s','idle','Idle, answered','last reply '+hhmm(turn.answered_at)+'; waiting on you')) pulse(el); }
        else if(turn.last_prompt_at&&setTag(el,'s','live','Working','on your prompt from '+hhmm(turn.last_prompt_at))) pulse(el);
      /* A session with nothing to land is a closed loop once it exits. */
      const auto=!(w.done&&w.done.length)&&w.pid&&w.landing&&w.landing.state==='none'&&gone;
      if(w.done&&w.done.length||auto){ const done=auto||all(w.done,p);
        if(el.classList.contains('done')!==done) rewire=true;
        el.classList.toggle('done',done); flash(el,'w'+w.id,done); }
    });
    if(rewire) drawWires();
    news(p); tick(); applied++;
  }
  function news(p){
    if(!K){ newBtn.hidden=true; return; }
    const items=[];
    Object.keys(p.branches).forEach(function(b){ if(K.branches.indexOf(b)<0) items.push('branch <code>'+esc(b)+'</code>'); });
    Object.keys(p.remote_branches).forEach(function(b){ if(K.remote_branches.indexOf(b)<0) items.push('remote branch <code>'+esc(b)+'</code>'); });
    p.worktrees.forEach(function(w){ if(K.worktrees.indexOf(w.path)<0) items.push('worktree <code>'+esc(w.path)+'</code>'); });
    p.sessions.forEach(function(s2){
      if(K.pids.indexOf(s2.pid)>=0) return;
      if(K.sessions.some(function(id){return s2.args.indexOf(id)>=0;})) return;   /* a known session, resumed */
      items.push('Claude session pid '+s2.pid+' <code>'+esc(s2.args)+'</code>'); });
    /* Work merged on GitHub lands in origin/main first; offer the pull. */
    if(p.behind>0) items.unshift('<b>'+esc(p.main)+' is '+p.behind+' commit'+(p.behind===1?'':'s')+' behind '+esc(p.upstream)
      +'</b> (merged on GitHub). <button type="button" class="runbtn inline" data-cmd="git pull --ff-only">pull</button>');
    newBtn.hidden=!items.length;
    newBtn.textContent=(p.behind>0?'↓'+p.behind+' to pull · ':'')+'+'+items.length+' new';
    newDrop.innerHTML='<b>New since this board was built</b><ul>'+items.map(function(t){return '<li>'+t+'</li>';}).join('')
      +'</ul><p class="lede">The board only knows what it was built with. Run <code>/regroup</code> again to place these.</p>';
  }
  function ago(){ if(!lastAt) return 'not yet';
    const s2=Math.round((Date.now()-lastAt)/1000); return s2<5?'just now':s2<60?s2+'s ago':Math.round(s2/60)+'m ago'; }
  function tick(){ if(hostOK&&!liveBtn.classList.contains('gone')) liveBtn.lastChild.textContent='live · '+ago(); }
  setInterval(tick,5000);
  window.__regroupLive={ago:ago,summary:function(){ if(!last) return 'none';
    return JSON.stringify({current_branch:last.head_branch,main_ahead_of_upstream:last.ahead,branches:Object.keys(last.branches),
      remote_branches:Object.keys(last.remote_branches),worktrees:last.worktrees,landed_on_main:last.on_main,
      sessions_alive:last.sessions.map(function(x){return x.pid+' '+x.args;}),
      actions_done:D.actions.filter(function(a){return all(a.done,last)||manual[a.title];}).map(function(a){return a.title;})}); }};

  /* Manual ticks: for actions no check can see (hand tests), and for every
     action when the probe is not reachable (a browser tab). */
  function ticks(){
    D.actions.forEach(function(a,i){
      const row=document.querySelector('.actrow[data-i="'+i+'"]'); if(!row||row.querySelector('.tick')) return;
      if(hostOK&&a.done&&a.done.length) return;
      row.insertAdjacentHTML('beforeend','<label class="tick"><input type="checkbox" '+(manual[a.title]?'checked':'')+'> mark done</label>');
      row.querySelector('.tick input').addEventListener('change',function(e){
        saveMark(a.title,e.target.checked);
        if(last) apply(last); else { row.classList.toggle('done',!!manual[a.title]); }
      });
      if(manual[a.title]) row.classList.add('done');
    });
  }
  async function probe(force){
    if(!hostOK||inflight) return;
    if(force!==true&&Date.now()-lastAt<1500) return;
    inflight=true; liveBtn.classList.add('busy');
    try{
      if(LOCAL){
        const res=await api('/api/probe',INPUT);
        if(!res.ok) throw {code:'local_'+res.status};
        const p=await res.json(); if(p&&p.ok) apply(p);
        if(liveBtn.classList.contains('gone')){ liveBtn.classList.remove('gone'); }
      } else {
        const r=await mcp.callTool('host:regroup','probe',INPUT,{cache:false});
        const p=r.structuredContent||r.payload; if(p&&p.ok) apply(p);
      }
    }catch(e){
      if(LOCAL){ liveBtn.classList.add('gone');
        liveBtn.lastChild.textContent=(e&&e.code==='local_403')?'server restarted · reload page':'server stopped · run /regroup'; return; }
      if(e&&(e.code==='server_not_connected'||e.code==='not_in_manifest'||e.code==='not_granted'||e.code==='capability_disabled')) offline();
    }finally{ inflight=false; liveBtn.classList.remove('busy'); }
  }
  function offline(){ hostOK=false; liveBtn.hidden=true; ticks(); }
  var idleSince=Date.now();
  function soon(){ clearTimeout(soon.t); soon.t=setTimeout(probe,120); }
  window.addEventListener('focus',soon);
  document.addEventListener('visibilitychange',function(){ if(!document.hidden) soon(); });
  document.addEventListener('pointermove',function(){ if(Date.now()-idleSince>15000) soon(); idleSince=Date.now(); },{passive:true});
  liveBtn.onclick=function(){ probe(true); };
  newBtn.onclick=function(){ const open=!newDrop.classList.contains('on');
    document.querySelectorAll('.drop').forEach(function(o){o.classList.remove('on');});
    if(open) newDrop.classList.add('on'); };

  window.__regroupLive.probeNow=function(){ return probe(true); };
  if(LOCAL&&D.repo_path){
    /* Local: no floor on how often to look, so check every 4 s while visible. */
    hostOK=true; liveBtn.hidden=false;
    api('/api/marks',{}).then(function(r){ return r.json(); }).then(function(m){ manual=m||{};
      document.querySelectorAll('.actrow .tick').forEach(function(t){ t.remove(); }); ticks(); if(last) apply(last); })
      .catch(function(){ ticks(); });
    probe(true);
    /* Every 4 s while visible; once a minute in a background tab, which also
       keeps the server from idling out while the board is open anywhere. */
    setInterval(function(){ if(!document.hidden||Date.now()-lastAt>60000) probe(); },4000);
    return;
  }
  ticks();
  if(!window.claude||typeof claude.use!=='function'||!D.repo_path) return;
  claude.use('mcp').then(async function(m){
    if(!m) return;
    mcp=m;
    try{ const l=await mcp.listTools('host:regroup');
      hostOK=(l.servers||[]).some(function(v){ return v.tools&&v.tools.length; });
    }catch(e){ hostOK=false; }
    if(!hostOK) return;
    liveBtn.hidden=false;
    document.querySelectorAll('.actrow .tick').forEach(function(t){
      const i=+t.closest('.actrow').dataset.i; if(D.actions[i].done&&D.actions[i].done.length) t.remove(); });
    probe();
    setInterval(function(){ if(!document.hidden) probe(); },30000);
  });
})();

/* ---- ask Claude about the board ----
   sample runs on the viewer's own Claude plan. Git comes from a local MCP
   server (host:git, read-only tools only) and so works only for the owner in
   the Claude desktop app; everywhere else the chat answers from the board. */
(function(){
  const GIT_TOOLS={
    git_status:{d:'Working-tree status of the repo.',p:{}},
    git_log:{d:'Recent commits on the current branch: sha, author, date, full message.',p:{max_count:{type:'integer',description:'How many commits, at most 30'}}},
    git_show:{d:'One commit or ref: message and full diff. Use for "what is in <branch>": pass e.g. origin/evals.',p:{revision:{type:'string'}},r:['revision']},
    git_diff:{d:'Diff against a target. "main...origin/evals" shows what landing that branch would add.',p:{target:{type:'string'}},r:['target']},
    git_branch:{d:'List branches.',p:{branch_type:{type:'string',enum:['local','remote','all']}},r:['branch_type']}
  };
  const chat=document.getElementById('chat'), log=document.getElementById('clog'), form=document.getElementById('cform'),
        input=document.getElementById('cin'), send=document.getElementById('csend'), stop=document.getElementById('cstop'),
        deep=document.getElementById('cdeep'), gitPill=document.getElementById('gitstate'), btn=document.getElementById('b-ask');
  var sample=null, mcp=null, toolsOK=false, gitOn=false, turns=[], ctl=null, busy=false, chatId=null;
  const SUGG=(D.chat&&D.chat.suggestions)||['What needs me first, and why?','Which sessions can I close right now?','What exactly would land if I merged the branch that is not in main?'];
  function setGit(on,why){ gitOn=on; gitPill.textContent=on?'git: on (read-only)':'git: off'; gitPill.title=why||'';
    gitPill.classList.toggle('on',on); }
  function md(t){
    var h=esc(t), blocks=[];
    h=h.replace(/```[a-z]*\n?([\s\S]*?)(```|$)/g,function(_,c){blocks.push('<pre><code>'+c+'</code></pre>');return '\u0000'+(blocks.length-1)+'\u0000';});
    h=h.replace(/`([^`\n]+)`/g,'<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g,'<b>$1</b>');
    h=h.split(/\n{2,}/).map(function(par){
      if(/^\u0000\d+\u0000$/.test(par.trim())) return par.trim();
      const ls=par.split('\n');
      if(ls.every(function(l){return /^\s*([-*]|\d+\.)\s/.test(l);}))
        return '<ul>'+ls.map(function(l){return '<li>'+l.replace(/^\s*([-*]|\d+\.)\s/,'')+'</li>';}).join('')+'</ul>';
      return '<p>'+ls.join('<br>')+'</p>'; }).join('');
    return h.replace(/\u0000(\d+)\u0000/g,function(_,i){return blocks[+i];});
  }
  function empty(){ log.innerHTML='<div class="cempty"><p>Ask anything about these workstreams. Answers use the board'
    +(LOCAL?', the live repo state, and read-only access to the repo\'s files, git and session transcripts':
      gitOn?' and read-only git on '+esc(D.repo_path||'the repo'):'')+'.</p>'
    +SUGG.map(function(q){return '<button type="button" class="sugg">'+esc(q)+'</button>';}).join('')+'</div>'; }
  function rules(){
    const board=JSON.stringify({repo:D.repo,repo_path:D.repo_path,generated:D.generated,headline:D.headline,actions:D.actions,
      trunk:D.trunk,workstreams:D.workstreams,worktree_state:D.worktree_state,decisions:D.decisions,method:D.method});
    return 'You are answering questions on a "regroup" board: a map of the user\'s Claude Code sessions, branches and worktrees in the git repo '
      +D.repo+'. The board data is below as JSON. Each workstream has an id, the user\'s verbatim ask, whether it is in main (landing), '
      +'whether a session is running (session_state), where it ran (runtime: local or cloud), its tasks, a verdict, the next step and a command.\n\n'
      +'Answer briefly: lead with the answer, then at most a few bullets. Put commands, shas and branch names in backticks, spelled exactly as on the board. '
      +'When your answer centres on one workstream, call focus_card with its id so the board flies to it. '
      +(gitOn?'You can run read-only git with the git_* tools (repo_path is filled in for you). Use them when the board lacks the fact '
        +'(file lists, diffs, commit contents) and say in one line what you looked at. '
        :'You cannot run git in this view. If a question needs it, say so and give the git command for the user to run. ')
      +'You cannot change anything: for any change, give the command and let the user run it. If the board does not say, say you do not know.'
      +(window.__regroupLive?'\n\nLIVE STATE (checked '+window.__regroupLive.ago()+'; newer than the board, trust it over the board): '+window.__regroupLive.summary():'')
      +'\n\nBOARD:\n'+board;
  }
  function tools(act){
    if(!toolsOK) return undefined;
    const t=[{name:'focus_card',description:'Fly the board to one workstream card and open it. Input: its id from the board JSON. Returns "ok".',
      inputSchema:{type:'object',properties:{id:{type:'string'}},required:['id']},
      execute:function(i){ const el=document.querySelector('[data-id="'+String(i.id).replace(/"/g,'')+'"]');
        if(!el) throw new Error('no card with id '+i.id); focusCard(el); act('showed '+(el.querySelector('h3,h4')||el).textContent); return 'ok'; }}];
    if(gitOn) Object.keys(GIT_TOOLS).forEach(function(n){ const g=GIT_TOOLS[n];
      t.push({name:n,description:g.d+' Read-only.',inputSchema:{type:'object',properties:g.p,required:g.r||[]},
        execute:async function(i,cx){
          const args=Object.assign({},i,{repo_path:D.repo_path});
          if(n==='git_log') args.max_count=Math.min(30,Math.max(1,Number(i.max_count)||10));
          act(n.replace('_',' ')+' '+[i.revision,i.target,i.branch_type].filter(Boolean).join(' '));
          try{ const r=await mcp.callTool('host:git',n,args,{signal:cx.signal});
            var txt=(r.content||[]).filter(function(b){return b.type==='text';}).map(function(b){return b.text;}).join('\n');
            return txt.length>14000?txt.slice(0,14000)+'\n[cut at 14,000 characters; ask for something narrower]':txt;
          }catch(e){
            if(e&&(e.code==='server_not_connected'||e.code==='not_in_manifest'||e.code==='not_granted')) setGit(false,'not reachable in this view');
            throw new Error('git unavailable here ('+(e&&e.code||'error')+'). Answer from the board and give the user the command to run.');
          }}});
    });
    return t;
  }
  const COPY={not_granted:'Asking Claude is turned off for this page.',sampling_disabled:'Claude isn\'t available on this account.',
    rate_limited:'You\'ve hit a usage limit. Try again in a bit.',session_expired:'Sign in to claude.ai again, then retry.',
    prompt_too_large:'The conversation got too long. Close and reopen the chat to start fresh.',refused:'Claude declined that one. Try rephrasing.',
    empty_completion:'No answer came back. Try asking differently.',tools_unavailable:'This view can\'t run tools; answering from the board only.'};
  async function ask(q){
    if(busy||!q.trim()) return;
    busy=true; send.disabled=true; stop.hidden=false;
    if(log.querySelector('.cempty,.hist')){ log.innerHTML=''; histBtn.classList.remove('on'); }
    const me=document.createElement('div'); me.className='msg me'; me.textContent=q; log.appendChild(me);
    const ai=document.createElement('div'); ai.className='msg ai';
    ai.innerHTML='<div class="acts2"></div><div class="body"><span class="wait">Thinking…</span></div>'; log.appendChild(ai);
    const acts=ai.querySelector('.acts2'), bodyEl=ai.querySelector('.body');
    function act(t){ const s=document.createElement('span'); s.textContent=t; acts.appendChild(s); log.scrollTop=log.scrollHeight; }
    log.scrollTop=log.scrollHeight;
    turns.push({role:'user',content:q}); if(!LOCAL&&turns.length>16) turns=turns.slice(-16);
    while(turns.length&&turns[0].role!=='user') turns.shift();
    ctl=new AbortController();
    if(LOCAL) return localAsk(bodyEl,act);
    try{
      const r=await sample([{role:'user',content:rules()}].concat(turns),{signal:ctl.signal,cache:false,
        modelTier:deep.checked?'default':'quick',tools:tools(act),
        onText:function(u){ bodyEl.innerHTML=md(u.text); log.scrollTop=log.scrollHeight; }});
      turns.push({role:'assistant',content:r.text});
      if(r.truncated) bodyEl.insertAdjacentHTML('beforeend','<p class="err">Cut short. Ask for less at a time.</p>');
    }catch(e){
      const c=e&&e.code;
      if(e&&e.text&&c!=='refused') bodyEl.innerHTML=md(e.text); else bodyEl.innerHTML='';
      if(c!=='cancelled') bodyEl.insertAdjacentHTML('beforeend','<p class="err">'+esc(COPY[c]||'Something went wrong reaching Claude. Try again.')+'</p>');
      if(c==='not_granted'||c==='sampling_disabled') { btn.hidden=true; chat.hidden=true; }
      if(c==='tools_unavailable') toolsOK=false;
      turns.pop();
    }finally{ busy=false; send.disabled=false; stop.hidden=true; ctl=null; }
  }
  /* Local chat: claude -p in the repo, streamed as NDJSON by serve.py. A
     [[focus:<id>]] marker at the end of the answer flies the board to that card. */
  async function localAsk(bodyEl,act){
    var text='', focusId=null;
    function show(){ const m=text.match(/\[\[focus:([\w-]+)\]\]/); if(m) focusId=m[1];
      bodyEl.innerHTML=md(text.replace(/\s*\[\[focus:[\w-]+\]\]\s*/g,' ').trim()||'…'); log.scrollTop=log.scrollHeight; }
    try{
      if(!chatId) chatId=new Date().toISOString().replace(/[-:T]/g,'').slice(0,14)+'-'+Math.random().toString(36).slice(2,6);
      const res=await api('/api/chat',{turns:turns,deep:deep.checked,chat_id:chatId},ctl.signal);
      if(res.status===403) throw new Error('This page is from an older start of the regroup server. Reload the page once.');
      if(!res.ok||!res.body) throw new Error('server '+res.status);
      const rd=res.body.getReader(), dec=new TextDecoder(); var buf='', failed=null, cmds=[];
      for(;;){
        const c=await rd.read(); if(c.done) break;
        buf+=dec.decode(c.value,{stream:true});
        const lines=buf.split('\n'); buf=lines.pop();
        lines.forEach(function(l){ if(!l.trim()) return; var ev; try{ ev=JSON.parse(l); }catch(e){ return; }
          if(ev.t==='text'){ text+=ev.d; show(); }
          else if(ev.t==='tool') act(ev.s);
          else if(ev.t==='cmds') cmds=ev.list;
          else if(ev.t==='error') failed=ev.m; });
      }
      if(failed&&!text) throw new Error(failed);
      addRuns(bodyEl,cmds);
      turns.push({role:'assistant',content:text.replace(/\s*\[\[focus:[\w-]+\]\]\s*/g,' ').trim()});
      if(focusId){ const el=document.querySelector('[data-id="'+focusId+'"]'); if(el){ focusCard(el); act('showed '+(el.querySelector('h3,h4')||el).textContent); } }
    }catch(e){
      if(text) show(); else bodyEl.innerHTML='';
      if(!(e&&e.name==='AbortError'))
        bodyEl.insertAdjacentHTML('beforeend','<p class="err">'+esc(/Failed to fetch|server 5/.test(String(e&&e.message))
          ?'The regroup server isn\'t running. Run /regroup to start it again.':String(e&&e.message||e))+'</p>');
      turns.pop();
    }finally{ busy=false; send.disabled=false; stop.hidden=true; ctl=null; }
  }
  /* Commands Claude wrote get the same run button and confirm as the board's. */
  function addRuns(bodyEl,cmds){
      bodyEl.querySelectorAll('pre code, code').forEach(function(el){
        if(el.closest('pre')&&el.parentNode.tagName!=='PRE') return;
        const t=el.textContent.trim(); if(cmds.indexOf(t)<0) return;
        const anchor=el.parentNode.tagName==='PRE'?el.parentNode:el;
        if(anchor.nextElementSibling&&anchor.nextElementSibling.classList.contains('runbtn')) return;
        const r=document.createElement('button'); r.type='button'; r.dataset.cmd=t;
        r.className='runbtn inline'+(/\bkill\b|branch -D|--delete|worktree remove|reset --hard|--force|\brm\b/.test(t)?' risky':'');
        r.textContent='run'; anchor.insertAdjacentElement('afterend',r);
      });
  }
  /* Past chats (local only): every conversation is saved by the server; the
     clock icon lists them and any one can be reopened and continued. */
  const histBtn=document.getElementById('chist'), newChatBtn=document.getElementById('cnew');
  function when(ms){ const m=Math.round((Date.now()-ms)/60000);
    return m<1?'just now':m<60?m+' min ago':m<1440?Math.round(m/60)+' h ago':new Date(ms).toLocaleDateString(undefined,{month:'short',day:'numeric'}); }
  async function showHistory(){
    if(busy) return;
    histBtn.classList.add('on');
    var list=[]; try{ list=await (await api('/api/chats',{})).json(); }catch(e){}
    log.innerHTML='<div class="hist"><h4>Past chats</h4>'+(list.length?list.map(function(c){
      return '<button type="button" class="hrow'+(c.id===chatId?' cur':'')+'" data-id="'+esc(c.id)+'">'+esc(c.title)
        +'<small>'+when(c.updated)+' &middot; '+c.questions+' question'+(c.questions===1?'':'s')+(c.id===chatId?' &middot; open now':'')+'</small></button>';
    }).join(''):'<p class="cempty">No chats yet.</p>')+'</div>';
  }
  async function openChat(id){
    var c; try{ const r=await api('/api/chat-load',{id:id}); if(!r.ok) return; c=await r.json(); }catch(e){ return; }
    chatId=c.id; turns=c.turns.map(function(t){ return {role:t.role,content:t.content}; });
    histBtn.classList.remove('on'); log.innerHTML='';
    c.turns.forEach(function(t){
      const m=document.createElement('div');
      if(t.role==='user'){ m.className='msg me'; m.textContent=t.content; log.appendChild(m); return; }
      m.className='msg ai'; m.innerHTML='<div class="acts2"></div><div class="body"></div>'; log.appendChild(m);
      const b=m.querySelector('.body'); b.innerHTML=md(t.content); addRuns(b,t.cmds||[]);
    });
    log.scrollTop=log.scrollHeight;
  }
  function newChat(){ if(busy) return; chatId=null; turns=[]; histBtn.classList.remove('on'); empty(); input.focus(); }
  histBtn.onclick=function(){ if(histBtn.classList.contains('on')){ if(chatId) openChat(chatId); else { histBtn.classList.remove('on'); empty(); } } else showHistory(); };
  newChatBtn.onclick=newChat;
  log.addEventListener('click',function(e){ const h=e.target.closest('.hrow'); if(h) openChat(h.dataset.id); });
  form.addEventListener('submit',function(e){ e.preventDefault(); const q=input.value; input.value=''; ask(q); });
  input.addEventListener('keydown',function(e){ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); form.requestSubmit(); } });
  stop.onclick=function(){ if(ctl) ctl.abort(); };
  log.addEventListener('click',function(e){ const b=e.target.closest('.sugg'); if(b) ask(b.textContent); });
  /* Show or hide the docked chat and refit the canvas to the width it leaves. */
  function dock(on,remember){
    chat.hidden=!on; document.body.classList.toggle('chat-on',on); btn.setAttribute('aria-pressed',on?'true':'false');
    if(remember){ try{ localStorage.setItem('regroup-chat',on?'on':'off'); }catch(e){} }
    requestAnimationFrame(function(){ drawWires(); if(focused) focusCard(focused); else fitWidth(); });
  }
  btn.onclick=function(){ dock(chat.hidden,true); if(!chat.hidden) input.focus(); };
  document.getElementById('cclose').onclick=function(){ dock(false,true); };
  var wantOn=true; try{ wantOn=localStorage.getItem('regroup-chat')!=='off'; }catch(e){}
  /* Inside a Claude viewer, reserve the chat's width before the first fit so
     the board doesn't jump when the chat lights up a moment later. */
  if(wantOn&&window.claude&&typeof claude.use==='function'){ document.body.classList.add('chat-on'); }
  if(LOCAL){
    btn.hidden=false; gitOn=true; gitPill.textContent='read access'; gitPill.classList.add('on');
    gitPill.title='claude -p in '+D.repo_path+' on your plan: files, git and transcripts, read-only';
    document.body.classList.add('chat-on'); dock(wantOn,false); empty();
    histBtn.hidden=false; newChatBtn.hidden=false;
    /* A reload shouldn't lose the conversation: reopen the latest one if recent. */
    api('/api/chats',{}).then(function(r){ return r.json(); }).then(function(list){
      if(list&&list[0]&&Date.now()-list[0].updated<6*3600e3&&!turns.length) openChat(list[0].id); }).catch(function(){});
    return;
  }
  if(!window.claude||typeof claude.use!=='function') return;
  claude.use('sample').then(async function(s){
    if(!s){ if(document.body.classList.contains('chat-on')) dock(false,false); return; }
    sample=s; btn.hidden=false; dock(wantOn,false);
    try{ const L=await sample.limits(); toolsOK=!!(L&&L.tools); }catch(e){}
    setGit(false,'checking'); empty();
    if(!toolsOK||!D.repo_path){ setGit(false,'this view cannot run tools'); empty(); return; }
    try{ mcp=await claude.use('mcp'); }catch(e){ mcp=null; }
    if(!mcp){ setGit(false,'open the board in the Claude desktop app'); empty(); return; }
    try{ const l=await mcp.listTools('host:git');
      const on=(l.servers||[]).some(function(v){ return v.tools&&v.tools.length; });
      setGit(on,on?'':'open the board in the Claude desktop app with the git server running');
    }catch(e){ setGit(false,'open the board in the Claude desktop app'); }
    empty();
  });
})();
</script>
"""

def render(data, head=""):
    """The board as one HTML string. `head` is injected first: serve.py uses it
    to hand the page its local-server token."""
    title = data.get("title") or (str(data.get("repo", "")) + " Regroup").strip()
    blob = json.dumps(data).replace("</", "<\\/")
    return head + HTML.replace("__TITLE__", html.escape(title)).replace("__DATA__", blob)


if __name__ == "__main__":
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "regroup.json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "regroup.html"
    out.write_text(render(json.loads(data_path.read_text())))
    print("wrote " + str(out) + " (" + str(out.stat().st_size // 1024) + " KB)")
