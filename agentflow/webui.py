"""Interactive web UI for agentflow.

A zero-dependency, stdlib-only HTTP server providing a polished single-page
application for running agentflow pipelines, inspecting results, managing
memory, and browsing the audit trail.

Start with:
    python -m agentflow serve [--port 8080]

Or programmatically:
    from agentflow.webui import WebUIServer
    server = WebUIServer(host="127.0.0.1", port=8080)
    server.serve_forever()
"""
from __future__ import annotations

import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional

from . import __version__
from .core import (
    Agent, AgentResult, Context, Governor, LLMError, MockLLM,
    OpenAICompatible, make_backend, Pipeline, MemoryStore,
)
from .agents import Researcher, Writer, FactChecker

# ── HTML template (embedded) ───────────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>agentflow — governed agentic pipelines</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='14' fill='%236d5ef5'/%3E%3Ccircle cx='16' cy='16' r='6' fill='%2322d3ee'/%3E%3C/svg%3E">
<style>
:root{
  --bg:#04060c;
  --card:rgba(255,255,255,.035);
  --card-hi:rgba(255,255,255,.06);
  --brd:rgba(255,255,255,.09);
  --brd-hi:rgba(255,255,255,.16);
  --text:#eef2fb;
  --muted:#8b94ab;
  --dim:#5c6579;
  --acc1:#6d5ef5;
  --acc2:#22d3ee;
  --ok:#34d399;
  --err:#f87171;
  --warn:#fbbf24;
  --r:16px;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Code","JetBrains Mono",Consolas,monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);line-height:1.6;min-height:100vh;font-size:15px}
body::before{
  content:"";position:fixed;inset:0;z-index:-2;pointer-events:none;
  background:
    radial-gradient(640px 420px at 12% -8%,rgba(109,94,245,.20),transparent 62%),
    radial-gradient(720px 480px at 88% -4%,rgba(34,211,238,.12),transparent 62%),
    radial-gradient(1000px 700px at 50% 115%,rgba(109,94,245,.09),transparent 65%);
}
body::after{
  content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
  background-image:radial-gradient(rgba(255,255,255,.055) 1px,transparent 1px);
  background-size:26px 26px;
  -webkit-mask-image:linear-gradient(180deg,rgba(0,0,0,.55),transparent 65%);
  mask-image:linear-gradient(180deg,rgba(0,0,0,.55),transparent 65%);
}
::selection{background:rgba(109,94,245,.4)}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,.12);border-radius:8px;border:2px solid var(--bg)}
::-webkit-scrollbar-track{background:transparent}
a{color:#a5b4fc;text-decoration:none}
a:hover{text-decoration:underline}

.shell{display:grid;grid-template-columns:248px 1fr;min-height:100vh}

/* ── rail ─────────────────────────────────────────── */
.rail{
  position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:8px;
  padding:26px 18px;background:rgba(10,14,24,.55);backdrop-filter:blur(18px);
  -webkit-backdrop-filter:blur(18px);border-right:1px solid var(--brd);z-index:20;
}
.brand{display:flex;align-items:center;gap:12px;padding:0 10px 22px;margin-bottom:6px;border-bottom:1px solid var(--brd)}
.brand .orb{
  width:36px;height:36px;border-radius:11px;flex-shrink:0;position:relative;
  background:conic-gradient(from 210deg,#6d5ef5,#22d3ee,#6d5ef5);
  display:grid;place-items:center;box-shadow:0 4px 18px rgba(109,94,245,.4);
}
.brand .orb::after{content:"";width:14px;height:14px;border-radius:50%;background:var(--bg);box-shadow:inset 0 0 0 3px rgba(255,255,255,.85)}
.brand .name{font-size:16px;font-weight:700;letter-spacing:-.01em}
.brand .name small{display:block;font-size:10.5px;font-weight:500;color:var(--dim);letter-spacing:.14em;text-transform:uppercase;margin-top:1px}
.nav{display:flex;flex-direction:column;gap:4px;margin-top:8px}
.nav button{
  display:flex;align-items:center;gap:11px;padding:10px 13px;border-radius:11px;
  background:transparent;border:1px solid transparent;color:var(--muted);
  font-family:var(--sans);font-size:14px;font-weight:500;cursor:pointer;text-align:left;
  transition:all .18s ease;position:relative;
}
.nav button svg{width:18px;height:18px;flex-shrink:0;opacity:.75}
.nav button:hover{color:var(--text);background:var(--card)}
.nav button.on{
  color:#fff;background:linear-gradient(135deg,rgba(109,94,245,.20),rgba(34,211,238,.10));
  border-color:rgba(109,94,245,.35);box-shadow:0 4px 16px rgba(109,94,245,.15) inset;
}
.nav button.on svg{opacity:1;color:#a5b4fc}
.rail .foot{margin-top:auto;display:flex;flex-direction:column;gap:8px;padding:14px 12px 4px;border-top:1px solid var(--brd)}
.rail .foot .row{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--dim)}
.pulse-dot{width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 0 rgba(52,211,153,.5);animation:beat 2.4s infinite}
.pulse-dot.off{background:var(--err);animation:none}
@keyframes beat{0%{box-shadow:0 0 0 0 rgba(52,211,153,.45)}70%{box-shadow:0 0 0 7px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}

/* ── main ─────────────────────────────────────────── */
main{padding:34px 44px 80px;max-width:1180px;min-width:0}
.page{display:none}
.page.on{display:block;animation:rise .35s ease both}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.eyebrow{font-size:11px;font-weight:600;letter-spacing:.16em;text-transform:uppercase;color:#7c86a0;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.eyebrow::before{content:"";width:18px;height:1px;background:linear-gradient(90deg,var(--acc1),var(--acc2))}
h1{font-size:30px;font-weight:750;letter-spacing:-.02em;margin-bottom:8px}
h1 .grad{background:linear-gradient(90deg,#c7d2fe,#67e8f9);-webkit-background-clip:text;background-clip:text;color:transparent}
.lede{color:var(--muted);font-size:15px;max-width:640px;margin-bottom:30px}
h2.sec{font-size:13px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:34px 0 14px;display:flex;align-items:center;gap:12px}
h2.sec::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--brd),transparent)}

.card{
  background:var(--card);border:1px solid var(--brd);border-radius:var(--r);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  transition:border-color .2s ease,background .2s ease;
}
.card.pad{padding:22px}
.card.hover:hover{border-color:var(--brd-hi);background:var(--card-hi)}

/* ── forms ────────────────────────────────────────── */
.field{margin-bottom:18px}
.field label,.micro{display:block;font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);margin-bottom:8px}
input[type=text],input[type=number],textarea{
  width:100%;padding:12px 14px;background:rgba(4,6,12,.5);border:1px solid var(--brd);
  border-radius:12px;color:var(--text);font-size:14px;font-family:var(--sans);outline:none;
  transition:border-color .15s ease,box-shadow .15s ease;
}
input::placeholder,textarea::placeholder{color:var(--dim)}
input:focus,textarea:focus{border-color:rgba(109,94,245,.6);box-shadow:0 0 0 3px rgba(109,94,245,.18)}
textarea{min-height:96px;resize:vertical;line-height:1.55}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}

.seg{display:flex;background:rgba(4,6,12,.5);border:1px solid var(--brd);border-radius:12px;padding:4px;gap:4px}
.seg button{
  flex:1;padding:9px 12px;border-radius:9px;background:transparent;border:none;
  color:var(--muted);font-size:13px;font-weight:600;cursor:pointer;font-family:var(--sans);
  transition:all .18s ease;display:flex;align-items:center;justify-content:center;gap:8px;
}
.seg button small{font-weight:400;font-size:11px;color:var(--dim)}
.seg button:hover{color:var(--text)}
.seg button.on{
  color:#fff;background:linear-gradient(135deg,rgba(109,94,245,.45),rgba(34,211,238,.28));
  box-shadow:0 2px 10px rgba(109,94,245,.25);
}
.seg button.on small{color:#c9d4f5}

.switchrow{display:flex;gap:26px;flex-wrap:wrap;margin:20px 0 4px}
.switch{display:flex;align-items:center;gap:11px;cursor:pointer;font-size:13.5px;color:var(--muted);user-select:none}
.switch input{display:none}
.switch .tr{
  width:40px;height:22px;border-radius:99px;background:rgba(255,255,255,.10);
  border:1px solid var(--brd);position:relative;transition:all .2s ease;flex-shrink:0;
}
.switch .tr::after{
  content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;
  background:var(--muted);transition:all .2s ease;
}
.switch input:checked + .tr{background:linear-gradient(135deg,rgba(109,94,245,.7),rgba(34,211,238,.5));border-color:rgba(109,94,245,.5)}
.switch input:checked + .tr::after{left:20px;background:#fff}
.switch:hover .tr{border-color:var(--brd-hi)}

.btn{
  display:inline-flex;align-items:center;gap:9px;padding:12px 22px;border-radius:12px;border:none;
  font-size:14px;font-weight:600;cursor:pointer;font-family:var(--sans);transition:all .18s ease;
  position:relative;overflow:hidden;
}
.btn-grad{
  background:linear-gradient(135deg,var(--acc1) 0%,#4f8ef7 55%,var(--acc2) 120%);
  color:#fff;box-shadow:0 8px 24px rgba(109,94,245,.35);
}
.btn-grad::after{content:"";position:absolute;inset:0;background:linear-gradient(120deg,transparent 30%,rgba(255,255,255,.25) 50%,transparent 70%);transform:translateX(-120%);transition:transform .55s ease}
.btn-grad:hover{transform:translateY(-1px);box-shadow:0 12px 30px rgba(109,94,245,.45)}
.btn-grad:hover::after{transform:translateX(120%)}
.btn-grad:active{transform:none}
.btn-grad:disabled{opacity:.55;cursor:not-allowed;transform:none}
.btn-ghost{background:var(--card);color:var(--muted);border:1px solid var(--brd)}
.btn-ghost:hover{color:var(--text);border-color:var(--brd-hi);background:var(--card-hi)}
.btn-danger{background:rgba(248,113,113,.10);color:var(--err);border:1px solid rgba(248,113,113,.3)}
.btn-danger:hover{background:rgba(248,113,113,.18)}
.btn-sm{padding:8px 14px;font-size:12.5px;border-radius:10px}
.kbd{font-family:var(--mono);font-size:10.5px;color:var(--dim);border:1px solid var(--brd);border-bottom-width:2px;border-radius:6px;padding:2px 7px;background:rgba(255,255,255,.03)}

.runbar{display:flex;align-items:center;gap:16px;margin-top:26px;flex-wrap:wrap}
.runmeta{font-size:13px;color:var(--dim);display:flex;align-items:center;gap:10px}

/* ── pipeline flow viz ─────────────────────────────── */
.flowwrap{padding:30px 14px 24px;margin-top:26px;position:relative}
.flow{display:flex;align-items:flex-start;justify-content:space-between;gap:4px}
.node{display:flex;flex-direction:column;align-items:center;gap:11px;width:118px;flex-shrink:0}
.node .orb{
  width:58px;height:58px;border-radius:18px;display:grid;place-items:center;position:relative;
  background:var(--card);border:1px solid var(--brd);color:var(--muted);
  transition:all .3s ease;
}
.node .orb svg{width:24px;height:24px}
.node .orb .mark{
  position:absolute;right:-6px;bottom:-6px;width:20px;height:20px;border-radius:50%;
  display:none;place-items:center;font-size:11px;font-weight:800;color:#04121a;
  border:2px solid var(--bg);
}
.node .nm{font-size:12.5px;font-weight:600;color:var(--muted);letter-spacing:.01em;transition:color .3s}
.node .st{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);min-height:13px;transition:color .3s}
.node[data-state=active] .orb{border-color:rgba(109,94,245,.7);color:#c7d2fe;background:rgba(109,94,245,.12);animation:pulse 1.5s ease-in-out infinite}
.node[data-state=active] .st{color:#a5b4fc}
.node[data-state=pass] .orb{border-color:rgba(52,211,153,.6);color:var(--ok);background:rgba(52,211,153,.10)}
.node[data-state=pass] .mark{display:grid;background:var(--ok)}
.node[data-state=pass] .st{color:var(--ok)}
.node[data-state=fail] .orb{border-color:rgba(248,113,113,.6);color:var(--err);background:rgba(248,113,113,.10)}
.node[data-state=fail] .mark{display:grid;background:var(--err)}
.node[data-state=fail] .st{color:var(--err)}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(109,94,245,.35)}50%{box-shadow:0 0 0 12px rgba(109,94,245,0)}}
.link{flex:1;height:2px;margin-top:28px;position:relative;background:rgba(255,255,255,.10);border-radius:2px;min-width:24px}
.link::after{
  content:"";position:absolute;inset:-1px;border-radius:2px;opacity:0;transition:opacity .3s;
  background:linear-gradient(90deg,transparent,rgba(109,94,245,.9),rgba(34,211,238,.9),transparent);
  background-size:220% 100%;
}
.flow.running .link::after{opacity:1;animation:flowmove 1.1s linear infinite}
@keyframes flowmove{from{background-position:220% 0}to{background-position:-100% 0}}
.node.gate .orb{border-radius:14px}

/* ── verdict + stats ───────────────────────────────── */
.results{margin-top:30px;display:flex;flex-direction:column;gap:18px}
.verdict{display:flex;align-items:center;gap:18px;padding:22px 24px;border-radius:var(--r);position:relative;overflow:hidden;animation:rise .4s ease both}
.verdict.ok{background:linear-gradient(135deg,rgba(52,211,153,.10),rgba(52,211,153,.015));border:1px solid rgba(52,211,153,.32)}
.verdict.err{background:linear-gradient(135deg,rgba(248,113,113,.10),rgba(248,113,113,.015));border:1px solid rgba(248,113,113,.32)}
.verdict .vi{width:52px;height:52px;border-radius:15px;display:grid;place-items:center;flex-shrink:0}
.verdict.ok .vi{background:rgba(52,211,153,.15);color:var(--ok);box-shadow:0 0 24px rgba(52,211,153,.25)}
.verdict.err .vi{background:rgba(248,113,113,.15);color:var(--err);box-shadow:0 0 24px rgba(248,113,113,.25)}
.verdict .vi svg{width:26px;height:26px}
.verdict .vt{font-size:19px;font-weight:700;letter-spacing:-.01em}
.verdict.ok .vt{color:#a7f3d0}
.verdict.err .vt{color:#fecaca}
.verdict .vr{font-size:13px;color:var(--muted);margin-top:2px}
.verdict .vright{margin-left:auto;text-align:right;font-size:12px;color:var(--dim);white-space:nowrap}
.verdict .vright b{display:block;font-size:17px;color:var(--text);font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.stat{padding:16px 18px}
.stat .lb{font-size:10.5px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin-bottom:7px;display:flex;justify-content:space-between;align-items:center}
.stat .vl{font-size:24px;font-weight:750;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat .vl small{font-size:13px;color:var(--dim);font-weight:500}
.stat .bar{height:4px;border-radius:4px;background:rgba(255,255,255,.08);margin-top:10px;overflow:hidden}
.stat .bar i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--acc1),var(--acc2));width:0;transition:width .8s cubic-bezier(.2,.8,.2,1)}
.stat .vl.ok{color:var(--ok)}
.stat .vl.warn{color:var(--warn)}
.stat .vl.err{color:var(--err)}

/* ── stages / checks ───────────────────────────────── */
.stages{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.stage{padding:18px;animation:rise .4s ease both}
.stage .sh{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.stage .si{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;flex-shrink:0}
.stage .si svg{width:17px;height:17px}
.stage.pass .si{background:rgba(52,211,153,.13);color:var(--ok)}
.stage.fail .si{background:rgba(248,113,113,.13);color:var(--err)}
.stage.na .si{background:rgba(255,255,255,.06);color:var(--muted)}
.stage .sn{font-size:14.5px;font-weight:700}
.stage .sv{margin-left:auto;font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;padding:4px 10px;border-radius:99px}
.stage.pass .sv{background:rgba(52,211,153,.12);color:var(--ok)}
.stage.fail .sv{background:rgba(248,113,113,.12);color:var(--err)}
.stage.na .sv{background:rgba(255,255,255,.06);color:var(--dim)}
.chk{display:flex;gap:10px;padding:9px 11px;border-radius:10px;background:rgba(4,6,12,.35);border:1px solid rgba(255,255,255,.05);align-items:flex-start;margin-bottom:8px}
.chk:last-child{margin-bottom:0}
.chk .ci{width:19px;height:19px;border-radius:6px;display:grid;place-items:center;font-size:10.5px;font-weight:800;flex-shrink:0;margin-top:1px}
.chk.pass .ci{background:rgba(52,211,153,.15);color:var(--ok)}
.chk.fail .ci{background:rgba(248,113,113,.15);color:var(--err)}
.chk .cn{font-family:var(--mono);font-size:11.5px;color:var(--text);word-break:break-all}
.chk .cd{font-size:11.5px;color:var(--dim);margin-top:2px}

/* ── output / markdown ─────────────────────────────── */
.out{padding:0;overflow:hidden}
.out .oh{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;border-bottom:1px solid var(--brd)}
.out .oh .t{font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);display:flex;gap:9px;align-items:center}
.out .ob{padding:22px 24px;max-height:520px;overflow-y:auto;font-size:14.5px;line-height:1.75}
.out .ob h2,.out .ob h3,.out .ob h4{margin:20px 0 10px;letter-spacing:-.01em;line-height:1.35}
.out .ob h2{font-size:19px}.out .ob h3{font-size:16px}.out .ob h4{font-size:14px;color:#c7d2fe}
.out .ob p{margin:0 0 12px;color:#d6dcec}
.out .ob ul{margin:0 0 14px;padding-left:4px;list-style:none}
.out .ob li{position:relative;padding-left:20px;margin-bottom:6px;color:#d6dcec}
.out .ob li::before{content:"";position:absolute;left:4px;top:10px;width:6px;height:6px;border-radius:2px;background:linear-gradient(135deg,var(--acc1),var(--acc2))}
.out .ob strong{color:#fff}
.out .ob code{font-family:var(--mono);font-size:12.5px;background:rgba(109,94,245,.14);border:1px solid rgba(109,94,245,.25);border-radius:6px;padding:1.5px 6px;color:#c7d2fe}
.out .ob pre{background:rgba(4,6,12,.7);border:1px solid var(--brd);border-radius:12px;padding:16px;overflow-x:auto;margin:0 0 14px}
.out .ob pre code{background:none;border:none;padding:0;color:#aeb9d6;font-size:12.5px;line-height:1.7}

/* ── warnings / trace ──────────────────────────────── */
.warnbox{padding:14px 18px;border-left:3px solid var(--warn);background:rgba(251,191,36,.06);border-radius:10px;font-size:13.5px;color:#fcd97d;margin-bottom:8px}
.tl{padding:6px 6px 6px 4px;max-height:380px;overflow-y:auto}
.tl-item{position:relative;padding:9px 14px 9px 34px;border-radius:10px;transition:background .15s}
.tl-item:hover{background:var(--card)}
.tl-item::before{
  content:"";position:absolute;left:11px;top:15px;width:8px;height:8px;border-radius:50%;
  background:var(--bg);border:2px solid var(--dim);
}
.tl-item.ev-start::before{border-color:var(--acc1)}
.tl-item.ev-done::before{border-color:var(--ok);background:rgba(52,211,153,.3)}
.tl-item.ev-pub::before{border-color:var(--acc2);background:rgba(34,211,238,.3)}
.tl-item.ev-veto::before{border-color:var(--err);background:rgba(248,113,113,.3)}
.tl-item .ev{font-weight:700;font-size:13px;display:inline-block;min-width:130px}
.tl-item .det{color:var(--muted);font-size:12.5px;font-family:var(--mono);word-break:break-all}
.tl-item .ts{float:right;color:var(--dim);font-size:11px;font-family:var(--mono);margin-left:12px}

/* ── memory ────────────────────────────────────────── */
.membar{display:flex;gap:12px;align-items:center;margin-bottom:20px;flex-wrap:wrap}
.membar .inp{flex:1;min-width:220px;position:relative}
.membar .inp input{padding-left:40px}
.membar .inp svg{position:absolute;left:13px;top:50%;transform:translateY(-50%);width:17px;height:17px;color:var(--dim)}
.mem-item{padding:16px 18px;margin-bottom:10px;animation:rise .35s ease both}
.mem-item .mt{font-size:14px;color:var(--text);line-height:1.55}
.mem-item .mm{display:flex;gap:10px;align-items:center;margin-top:9px;flex-wrap:wrap}
.chip{font-size:10.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;padding:3px 10px;border-radius:99px}
.chip.ok{background:rgba(52,211,153,.12);color:var(--ok)}
.chip.err{background:rgba(248,113,113,.12);color:var(--err)}
.chip.neu{background:rgba(255,255,255,.06);color:var(--muted)}
.mem-item .when{font-size:12px;color:var(--dim);margin-left:auto}
.empty{padding:44px 20px;text-align:center;color:var(--dim);font-size:14px}
.empty svg{width:38px;height:38px;margin-bottom:12px;opacity:.4}

/* ── about ─────────────────────────────────────────── */
.aboutgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:6px}
.pcard{padding:20px}
.pcard .pi{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;margin-bottom:14px;background:linear-gradient(135deg,rgba(109,94,245,.25),rgba(34,211,238,.15));color:#c7d2fe}
.pcard .pi svg{width:20px;height:20px}
.pcard h3{font-size:15px;font-weight:700;margin-bottom:6px}
.pcard p{font-size:13px;color:var(--muted);line-height:1.6}
.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.fact{padding:16px 18px}
.fact .lb{font-size:10.5px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin-bottom:6px}
.fact .vl{font-size:15px;font-weight:650;word-break:break-word}
.arch{
  background:rgba(4,6,12,.65);border:1px solid var(--brd);border-radius:14px;padding:22px;
  font-family:var(--mono);font-size:12.5px;line-height:1.85;color:#aeb9d6;overflow-x:auto;
  white-space:pre;
}
.arch .hl{color:#c7d2fe}

/* ── toasts / spinner ──────────────────────────────── */
.toasts{position:fixed;bottom:24px;right:24px;display:flex;flex-direction:column;gap:10px;z-index:100}
.toast{
  padding:13px 18px;border-radius:12px;font-size:13.5px;font-weight:550;max-width:360px;
  background:rgba(13,18,32,.9);backdrop-filter:blur(16px);border:1px solid var(--brd-hi);
  box-shadow:0 12px 34px rgba(0,0,0,.5);animation:toastin .25s ease both;
  display:flex;align-items:center;gap:10px;
}
.toast.ok{border-color:rgba(52,211,153,.4);color:#a7f3d0}
.toast.err{border-color:rgba(248,113,113,.4);color:#fecaca}
@keyframes toastin{from{opacity:0;transform:translateY(10px) scale(.97)}to{opacity:1;transform:none}}
.toast.bye{opacity:0;transform:translateY(6px);transition:all .3s}
.spinner{width:17px;height:17px;border:2.5px solid rgba(255,255,255,.2);border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite;display:inline-block;flex-shrink:0}
@keyframes spin{to{transform:rotate(360deg)}}

@media(max-width:920px){
  .shell{grid-template-columns:1fr}
  .rail{position:static;height:auto;flex-direction:row;align-items:center;padding:12px 16px;border-right:none;border-bottom:1px solid var(--brd);gap:10px;overflow-x:auto}
  .brand{border-bottom:none;padding:0 6px 0 0;margin:0}
  .brand .name small{display:none}
  .nav{flex-direction:row;margin:0;gap:4px}
  .nav button{padding:8px 12px;white-space:nowrap}
  .rail .foot{display:none}
  main{padding:24px 18px 70px}
  .stats,.stages,.aboutgrid,.facts,.grid3{grid-template-columns:1fr 1fr}
  .node{width:auto}
  .node .nm{font-size:11px}
}
@media(max-width:560px){.stats,.stages,.grid2,.grid3,.aboutgrid,.facts{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms !important;animation-iteration-count:1 !important;transition-duration:.01ms !important}
}
</style>
</head>
<body>
<div class="shell">
  <aside class="rail">
    <div class="brand">
      <div class="orb"></div>
      <div class="name">agentflow<small>governed pipelines</small></div>
    </div>
    <nav class="nav" id="nav">
      <button class="on" data-tab="run">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z"/></svg>
        Run pipeline
      </button>
      <button data-tab="memory">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9h6M9 13h6M9 17h4"/></svg>
        Memory
      </button>
      <button data-tab="about">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.5"/></svg>
        About
      </button>
    </nav>
    <div class="foot">
      <div class="row"><span class="pulse-dot" id="healthdot"></span><span id="healthtxt">checking…</span></div>
      <div class="row"><span>v0.4.1 · stdlib only · MIT</span></div>
    </div>
  </aside>

  <main>
    <!-- ════ RUN ════ -->
    <section class="page on" id="page-run">
      <div class="eyebrow">pipeline · researcher → writer → factchecker</div>
      <h1>Run a <span class="grad">governed pipeline</span></h1>
      <p class="lede">One task in, verified output out. Every stage is checked against a rubric, every decision is budget-gated by the Governor and audit-logged in the trace.</p>

      <div class="card pad" id="runform">
        <div class="field">
          <label for="task">Task / topic</label>
          <textarea id="task" placeholder="e.g. agentic AI governance in 2026">agentic AI governance in 2026</textarea>
        </div>

        <div class="grid2" style="margin-bottom:18px">
          <div class="field" style="margin-bottom:0">
            <label>LLM backend</label>
            <div class="seg" id="seg-backend">
              <button class="on" data-val="mock">Mock <small>offline</small></button>
              <button data-val="openai">OpenAI-compat <small>remote</small></button>
            </div>
          </div>
          <div class="field" id="f-model" style="margin-bottom:0;visibility:hidden">
            <label for="model">Model</label>
            <input type="text" id="model" placeholder="gpt-4o-mini" value="">
          </div>
        </div>

        <div class="grid3" id="f-knobs">
          <div class="field" style="visibility:hidden"><label for="temperature">Temperature</label><input type="number" id="temperature" value="0.7" step="0.1" min="0" max="2"></div>
          <div class="field" style="visibility:hidden"><label for="max_tokens">Max tokens</label><input type="number" id="max_tokens" value="2048" step="128" min="1" max="128000"></div>
          <div class="field" style="visibility:hidden"><label for="retries">Retries</label><input type="number" id="retries" value="2" min="0" max="10"></div>
        </div>

        <div class="switchrow">
          <label class="switch"><input type="checkbox" id="strict" checked><span class="tr"></span>Strict verification (fail on any check)</label>
          <label class="switch"><input type="checkbox" id="stop_on_failure"><span class="tr"></span>Stop pipeline on first failure</label>
        </div>

        <div class="runbar">
          <button class="btn btn-grad" id="btn-run">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M6 3.6v16.8a1 1 0 0 0 1.54.84l13.1-8.4a1 1 0 0 0 0-1.68L7.54 2.76A1 1 0 0 0 6 3.6z"/></svg>
            <span id="run-label">Run pipeline</span>
          </button>
          <span class="runmeta"><span class="kbd">⌘</span><span class="kbd">↵</span>&nbsp; to run &nbsp;·&nbsp; <span id="run-status"></span></span>
        </div>
      </div>

      <div class="card flowwrap">
        <div class="flow" id="flow">
          <div class="node" id="node-Researcher">
            <div class="orb">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.8-3.8"/></svg>
              <span class="mark">✓</span>
            </div>
            <div class="nm">Researcher</div><div class="st">ready</div>
          </div>
          <div class="link"></div>
          <div class="node" id="node-Writer">
            <div class="orb">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              <span class="mark">✓</span>
            </div>
            <div class="nm">Writer</div><div class="st">ready</div>
          </div>
          <div class="link"></div>
          <div class="node" id="node-FactChecker">
            <div class="orb">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-3.5 8-10V5l-8-3-8 3v7c0 6.5 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
              <span class="mark">✓</span>
            </div>
            <div class="nm">FactChecker</div><div class="st">ready</div>
          </div>
          <div class="link"></div>
          <div class="node gate" id="node-Gate">
            <div class="orb">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2"/></svg>
              <span class="mark">✓</span>
            </div>
            <div class="nm">Governor · publish</div><div class="st">gated</div>
          </div>
        </div>
      </div>

      <div class="results" id="results"></div>
    </section>

    <!-- ════ MEMORY ════ -->
    <section class="page" id="page-memory">
      <div class="eyebrow">memory · publish-gated recall</div>
      <h1>Memory <span class="grad">store</span></h1>
      <p class="lede">Records published through the pipeline are remembered on disk (JSON). Recall by keyword, or clear the store.</p>
      <div class="membar">
        <div class="inp">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.8-3.8"/></svg>
          <input type="text" id="mem-query" placeholder="Search records… (blank = all)">
        </div>
        <button class="btn btn-ghost" id="btn-recall">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>
          Recall
        </button>
        <button class="btn btn-danger" id="btn-memclear">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6"/></svg>
          Clear all
        </button>
      </div>
      <div id="mem-results"></div>
    </section>

    <!-- ════ ABOUT ════ -->
    <section class="page" id="page-about">
      <div class="eyebrow">about · project #1 of the agentic-ai portfolio</div>
      <h1>agentflow <span class="grad">— the control plane for autonomous agents</span></h1>
      <p class="lede">A governed, verifiable multi-agent pipeline toolkit in pure Python — zero runtime dependencies. The layer that decides <em>what an agent is allowed to do</em>, not just who it is.</p>

      <div class="aboutgrid">
        <div class="card pcard">
          <div class="pi"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="12" r="2.5"/><circle cx="19" cy="6" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="M7.3 11 16.6 7M7.3 13l9.3 4"/></svg></div>
          <h3>Multi-agent orchestration</h3>
          <p>A <b>Pipeline</b> threads a shared <b>Context</b> through a sequence of agents, each building on the previous output, with retryable LLM calls and strict / lenient run modes.</p>
        </div>
        <div class="card pcard">
          <div class="pi"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-3.5 8-10V5l-8-3-8 3v7c0 6.5 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg></div>
          <h3>Verifiability-by-design</h3>
          <p>Every agent ships a rubric of composable checks. The pipeline verifies each stage's output against it <b>before</b> moving on — pass/fail, with human-readable detail.</p>
        </div>
        <div class="card pcard">
          <div class="pi"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M7 21h10M12 18v3M8 9h8M8 13h5"/></svg></div>
          <h3>Governor control-plane</h3>
          <p>A policy + budget layer that can veto the final <b>publish</b> action, enforces call/token budgets, and writes a JSONL audit <b>Trace</b> of every decision.</p>
        </div>
      </div>

      <h2 class="sec">Facts</h2>
      <div class="facts" id="about-grid"></div>

      <h2 class="sec">Architecture</h2>
      <pre class="arch"><span class="hl">task</span> ──►  PIPELINE (orchestrator)
             Governor ──► budget?  policy?  audit
                │
   [ Researcher ] ─► [ Writer ] ─► [ FactChecker ] ─► publish?
        │              │              │
        └──────────────┴──────────────┘
               shared Context (blackboard)
               + per-stage Verifier rubric
               + Trace (audit log, JSONL)</pre>
    </section>
  </main>
</div>

<div class="toasts" id="toasts"></div>

<script>
"use strict";
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=n=>n==null?"∞":Number(n).toLocaleString();

function toast(msg,kind){
  const t=document.createElement("div");
  t.className="toast "+(kind||"");
  t.innerHTML=(kind==="ok"?'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="m5 13 4 4L19 7"/></svg>':kind==="err"?'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>':"");
  t.appendChild(document.createTextNode(" "+msg));
  $("toasts").appendChild(t);
  setTimeout(()=>{t.classList.add("bye");setTimeout(()=>t.remove(),320)},3600);
}
async function api(path,opts={}){
  const r=await fetch(path,{headers:{"Content-Type":"application/json"},...opts});
  let d=null;try{d=await r.json()}catch(e){}
  if(!r.ok)throw new Error((d&&d.error)||r.statusText);
  return d;
}
function relTime(ts){
  if(!ts)return"";
  const d=Math.max(0,Date.now()/1000-ts);
  if(d<60)return"just now";
  if(d<3600)return Math.floor(d/60)+"m ago";
  if(d<86400)return Math.floor(d/3600)+"h ago";
  if(d<86400*7)return Math.floor(d/86400)+"d ago";
  return new Date(ts*1000).toLocaleDateString();
}

/* ── nav ─────────────────────────────────────────── */
document.querySelectorAll("#nav button").forEach(b=>b.addEventListener("click",()=>{
  document.querySelectorAll("#nav button").forEach(x=>x.classList.remove("on"));
  b.classList.add("on");
  document.querySelectorAll(".page").forEach(p=>p.classList.remove("on"));
  $("page-"+b.dataset.tab).classList.add("on");
  if(b.dataset.tab==="about")loadAbout();
  if(b.dataset.tab==="memory"&&!memLoaded)recallMem();
  window.scrollTo({top:0});
}));

/* ── backend segmented control ───────────────────── */
let backend="mock";
document.querySelectorAll("#seg-backend button").forEach(b=>b.addEventListener("click",()=>{
  document.querySelectorAll("#seg-backend button").forEach(x=>x.classList.remove("on"));
  b.classList.add("on");
  backend=b.dataset.val;
  const remote=backend!=="mock";
  $("f-model").style.visibility=remote?"visible":"hidden";
  document.querySelectorAll("#f-knobs .field").forEach(f=>f.style.visibility=remote?"visible":"hidden");
}));

/* ── health ──────────────────────────────────────── */
async function checkHealth(){
  try{
    const d=await api("/api/health");
    $("healthdot").classList.remove("off");
    $("healthtxt").textContent="online · v"+(d.version||"0.4.0");
  }catch(e){
    $("healthdot").classList.add("off");
    $("healthtxt").textContent="offline";
  }
}
checkHealth();setInterval(checkHealth,30000);

/* ── pipeline viz states ─────────────────────────── */
function flowReset(){
  $("flow").classList.remove("running");
  ["Researcher","Writer","FactChecker","Gate"].forEach(n=>{
    const el=$("node-"+n);
    el.removeAttribute("data-state");
    el.querySelector(".st").textContent=n==="Gate"?"gated":"ready";
  });
}
function flowRunning(){
  $("flow").classList.add("running");
  ["Researcher","Writer","FactChecker"].forEach(n=>$("node-"+n).setAttribute("data-state","active"));
  ["Researcher","Writer","FactChecker"].forEach(n=>$("node-"+n).querySelector(".st").textContent="working");
  $("node-Gate").setAttribute("data-state","active");
  $("node-Gate").querySelector(".st").textContent="awaiting";
}
function flowDone(d){
  $("flow").classList.remove("running");
  (d.stages||[]).forEach(s=>{
    const el=$("node-"+s.name);
    if(!el)return;
    const st=el.querySelector(".st");
    if(s.verified===true){el.setAttribute("data-state","pass");st.textContent="verified"}
    else if(s.verified===false){el.setAttribute("data-state","fail");st.textContent="failed"}
    else{el.removeAttribute("data-state");st.textContent="skipped"}
  });
  const g=$("node-Gate"),gst=g.querySelector(".st");
  if(d.publishable){g.setAttribute("data-state","pass");gst.textContent="published"}
  else if(d.aborted){g.setAttribute("data-state","fail");gst.textContent="aborted"}
  else{g.setAttribute("data-state","fail");gst.textContent="vetoed"}
}

/* ── run ─────────────────────────────────────────── */
async function runPipeline(){
  const task=$("task").value.trim();
  if(!task){toast("Enter a task first","err");return}
  const body={task,strict:$("strict").checked,stop_on_failure:$("stop_on_failure").checked};
  if(backend==="openai"){
    Object.assign(body,{
      backend:"openai",
      model:$("model").value.trim()||"gpt-4o-mini",
      temperature:parseFloat($("temperature").value)||0.7,
      max_tokens:parseInt($("max_tokens").value)||2048,
      retries:parseInt($("retries").value)||2
    });
  }
  const btn=$("btn-run"),label=$("run-label"),status=$("run-status");
  btn.disabled=true;
  label.innerHTML='<span class="spinner"></span>&nbsp;Running…';
  status.textContent="";
  $("results").innerHTML="";
  flowRunning();
  const t0=performance.now();
  try{
    const data=await api("/api/run",{method:"POST",body:JSON.stringify(body)});
    const dt=((performance.now()-t0)/1000).toFixed(2);
    status.textContent="completed in "+(data.elapsed!=null?data.elapsed+"s":dt+"s");
    flowDone(data);
    renderResults(data);
    toast("Pipeline completed — "+(data.publishable?"published":"blocked"),"ok");
  }catch(e){
    flowReset();
    status.textContent=e.message;
    toast(e.message,"err");
  }finally{
    btn.disabled=false;
    label.innerHTML='<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M6 3.6v16.8a1 1 0 0 0 1.54.84l13.1-8.4a1 1 0 0 0 0-1.68L7.54 2.76A1 1 0 0 0 6 3.6z"/></svg><span>Run pipeline</span>';
  }
}
$("btn-run").addEventListener("click",runPipeline);
document.addEventListener("keydown",e=>{
  if((e.metaKey||e.ctrlKey)&&e.key==="Enter"&&$("page-run").classList.contains("on")){e.preventDefault();runPipeline();}
});

/* ── markdown (tiny, safe) ───────────────────────── */
function md(src){
  if(!src)return"";
  const lines=String(src).split("\n");
  let html="",inCode=false,codeBuf=[],inList=false,para=[];
  const flushP=()=>{if(para.length){html+="<p>"+para.join("<br>")+"</p>";para=[]}};
  const flushL=()=>{if(inList){html+="</ul>";inList=false}};
  const inline=t=>esc(t)
    .replace(/`([^`]+)`/g,"<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g,"<em>$1</em>");
  for(const line of lines){
    if(line.trim().startsWith("```")){
      if(inCode){html+="<pre><code>"+esc(codeBuf.join("\n"))+"</code></pre>";codeBuf=[];inCode=false;}
      else{flushP();flushL();inCode=true;}
      continue;
    }
    if(inCode){codeBuf.push(line);continue}
    const h=line.match(/^(#{1,6})\s+(.*)/);
    if(h){flushP();flushL();const l=Math.min(h[1].length+1,4);html+="<h"+l+">"+inline(h[2])+"</h"+l+">";continue}
    const b=line.match(/^\s*[-*]\s+(.*)/);
    if(b){flushP();if(!inList){html+="<ul>";inList=true}html+="<li>"+inline(b[1])+"</li>";continue}
    if(line.trim()===""){flushP();flushL();continue}
    flushL();para.push(inline(line));
  }
  flushP();flushL();
  if(inCode)html+="<pre><code>"+esc(codeBuf.join("\n"))+"</code></pre>";
  return html;
}

/* ── results render ──────────────────────────────── */
const STAGE_ICONS={
  Researcher:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.8-3.8"/></svg>',
  Writer:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>',
  FactChecker:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-3.5 8-10V5l-8-3-8 3v7c0 6.5 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>'
};
function renderResults(d){
  const el=$("results");
  const ok=!!d.publishable;
  const dec=d.decision||{};
  const vTitle=ok?"PUBLISHABLE — clear to ship":(d.aborted?("RUN ABORTED — "+d.aborted):"VETOED — publish blocked");
  const vReason=dec.reason||dec.action||"no governor decision recorded";
  el.innerHTML=
    '<div class="verdict '+(ok?"ok":"err")+'">'+
      '<div class="vi">'+(ok
        ?'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><path d="m8 12.5 2.7 2.7L16.5 9"/></svg>'
        :'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><path d="M9 9l6 6M15 9l-6 6"/></svg>')+'</div>'+
      '<div><div class="vt">'+esc(vTitle)+'</div><div class="vr">'+esc(vReason)+'</div></div>'+
      '<div class="vright">elapsed<b>'+(d.elapsed!=null?d.elapsed.toFixed(2)+" s":"—")+'</b></div>'+
    '</div>'
  ;
  /* stats */
  const b=d.budget||{};
  const callsPct=b.max_agent_calls?Math.min(100,((b.calls_used||0)/b.max_agent_calls*100)):null;
  const tokPct=b.max_total_tokens?Math.min(100,((b.tokens_used||0)/b.max_total_tokens*100)):null;
  el.innerHTML+=
    '<div class="stats">'+
      '<div class="card stat"><div class="lb">Agent calls<b>'+(b.max_agent_calls?fmt(b.calls_used)+" / "+fmt(b.max_agent_calls):fmt(b.calls_used))+'</b></div><div class="vl">'+(b.calls_used!=null?b.calls_used:"—")+'</div>'+(callsPct!=null?'<div class="bar"><i data-w="'+callsPct.toFixed(1)+'"></i></div>':'')+'</div>'+
      '<div class="card stat"><div class="lb">Tokens<b>'+(b.max_total_tokens?fmt(b.tokens_used)+" / "+fmt(b.max_total_tokens):fmt(b.tokens_used))+'</b></div><div class="vl">'+(b.tokens_used!=null?b.tokens_used.toLocaleString():"—")+'</div>'+(tokPct!=null?'<div class="bar"><i data-w="'+tokPct.toFixed(1)+'"></i></div>':'')+'</div>'+
      '<div class="card stat"><div class="lb">Warnings</div><div class="vl '+(d.warnings&&d.warnings.length?"warn":"ok")+'">'+(d.warnings?d.warnings.length:0)+'</div><div class="bar"><i data-w="'+(d.warnings&&d.warnings.length?50:100)+'"></i></div></div>'+
      '<div class="card stat"><div class="lb">Stages verified</div><div class="vl '+(d.stages&&d.stages.length?(d.stages.every(s=>s.verified)?"ok":"warn"):"")+'">'+(d.stages?d.stages.filter(s=>s.verified===true).length+" / "+d.stages.length:"—")+'</div></div>'+
    '</div>';
  /* stages */
  if(d.stages&&d.stages.length){
    let s='<div class="stages">';
    d.stages.forEach((st,i)=>{
      const cls=st.verified===true?"pass":(st.verified===false?"fail":"na");
      const sv=st.verified===true?"verified":(st.verified===false?"failed":"no verdict");
      let checks="";
      (st.checks||[]).forEach(c=>{
        checks+='<div class="chk '+(c.passed?"pass":"fail")+'">'+
          '<span class="ci">'+(c.passed?"✓":"✗")+'</span>'+
          '<div><div class="cn">'+esc(c.check||c.name||"check")+'</div>'+(c.detail?'<div class="cd">'+esc(c.detail)+'</div>':'')+'</div>'+
        '</div>';
      });
      s+='<div class="card stage '+cls+'" style="animation-delay:'+(i*70)+'ms">'+
        '<div class="sh"><div class="si">'+(STAGE_ICONS[st.name]||"")+'</div><div class="sn">'+esc(st.name)+'</div><div class="sv">'+sv+'</div></div>'+
        (checks||'<div style="font-size:12.5px;color:var(--dim)">no checks recorded</div>')+
      '</div>';
    });
    s+='</div>';
    el.innerHTML+=s;
  }
  /* output */
  if(d.output){
    el.innerHTML+=
      '<div class="card out">'+
        '<div class="oh"><span class="t"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M9 13h6M9 17h4"/></svg>final output</span>'+
        '<button class="btn btn-ghost btn-sm" id="btn-copy"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>copy</button></div>'+
        '<div class="ob" id="outbody">'+md(d.output)+'</div>'+
      '</div>';
    const cb=$("btn-copy");
    if(cb)cb.addEventListener("click",()=>{
      (navigator.clipboard?navigator.clipboard.writeText(d.output):Promise.reject()).then(
        ()=>toast("Copied to clipboard","ok"),
        ()=>toast("Copy failed","err"));
    });
  }
  /* warnings */
  if(d.warnings&&d.warnings.length){
    el.innerHTML+='<div style="display:flex;flex-direction:column">'+d.warnings.map(w=>'<div class="warnbox">⚠&nbsp; '+esc(w)+'</div>').join("")+'</div>';
  }
  /* trace */
  if(d.trace&&d.trace.length){
    const t0ts=d.trace.reduce((m,e)=>Math.min(m,e.ts||1e15),1e15);
    const evcls=e=>{
      const n=e.event||"";
      if(n==="governor")return e.allow===false?"ev-veto":"ev-pub";
      if(n==="pipeline_end")return e.publishable?"ev-pub":"ev-veto";
      if(/veto|fail|error|abort|blocked/i.test(n))return"ev-veto";
      if(/done|pass/i.test(n))return"ev-done";
      return"ev-start";
    };
    let tl='<div class="tl">';
    d.trace.forEach(e=>{
      const det=Object.entries(e).filter(([k])=>k!=="event"&&k!=="ts")
        .map(([k,v])=>{
          if(Array.isArray(v))return k+": ["+v.length+" items]";
          if(v&&typeof v==="object")return k+": {…}";
          return k+"="+JSON.stringify(v);
        }).join("  ");
      const off=(e.ts&&t0ts<1e15)?(e.ts-t0ts).toFixed(2)+"s":"0.00s";
      tl+='<div class="tl-item "+evcls(e)+"><span class="ts">+'+off+'</span><span class="ev">'+esc(e.event||"event")+'</span><span class="det">'+esc(det)+'</span></div>';
    });
    tl+='</div>';
    el.innerHTML+=
      '<div class="card" style="padding:18px 20px 12px">'+
        '<div style="font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin-bottom:10px;display:flex;justify-content:space-between">audit trace<b style="color:var(--muted)">'+d.trace.length+' events</b></div>'+tl+'</div>';
  }
  requestAnimationFrame(()=>{
    el.querySelectorAll(".bar i[data-w]").forEach(i=>{i.style.width=i.dataset.w+"%"});
  });
}

/* ── memory ──────────────────────────────────────── */
let memLoaded=false;
async function recallMem(){
  const q=$("mem-query").value.trim();
  const el=$("mem-results");
  el.innerHTML='<div class="card" style="padding:20px;display:flex;gap:12px;align-items:center;color:var(--muted);font-size:13.5px"><span class="spinner"></span>Loading records…</div>';
  try{
    const data=await api("/api/memory/recent?limit=50"+(q?"&query="+encodeURIComponent(q):""));
    memLoaded=true;
    if(!data.length){
      el.innerHTML='<div class="card empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9h6M9 13h6"/></svg><div>No records '+(q?"match “"+esc(q)+"”":"stored yet")+'.<br>Published pipeline runs are remembered here automatically.</div></div>';
      return;
    }
    el.innerHTML=data.map((r,i)=>{
      const text=r.text||r.topic||r.title||r.task||JSON.stringify(r);
      const pub=r.publishable;
      const chip=pub===undefined?'<span class="chip neu">record</span>':(pub?'<span class="chip ok">published</span>':'<span class="chip err">vetoed</span>');
      return '<div class="card mem-item" style="animation-delay:'+(i*40)+'ms">'+
        '<div class="mt">'+esc(text)+'</div>'+
        '<div class="mm">'+chip+'<span class="chip neu">'+(r.topic||"untitled")+'</span><span class="when">'+relTime(r.ts)+'</span></div>'+
      '</div>';
    }).join("");
  }catch(e){
    el.innerHTML='<div class="card" style="padding:18px;color:var(--err);font-size:13.5px">'+esc(e.message)+'</div>';
  }
}
$("btn-recall").addEventListener("click",recallMem);
$("mem-query").addEventListener("keydown",e=>{if(e.key==="Enter")recallMem()});
$("btn-memclear").addEventListener("click",async()=>{
  if(!confirm("Clear all memory records? This cannot be undone."))return;
  try{
    await api("/api/memory/clear",{method:"POST"});
    toast("Memory cleared","ok");
    recallMem();
  }catch(e){toast(e.message,"err")}
});

/* ── about ───────────────────────────────────────── */
async function loadAbout(){
  try{
    const d=await api("/api/about");
    const items=[
      ["Version","v"+d.version],
      ["Agents",d.agents.join(" · ")],
      ["Core modules",d.core_modules.join(", ")],
      ["Runtime dependencies","none — pure stdlib"],
      ["Python",">= 3.10"],
      ["License","MIT"]
    ];
    $("about-grid").innerHTML=items.map(([l,v])=>
      '<div class="card fact"><div class="lb">'+l+'</div><div class="vl">'+esc(String(v))+'</div></div>').join("");
  }catch(e){}
}
loadAbout();
flowReset();
</script>
</body>
</html>"""


# ── Handler ──────────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    """Serves the embedded HTML + JSON API for the agentflow web UI."""

    server: "WebUIServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self) -> None:
        body = _HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path in ("/", "/index.html"):
            self._send_html()
            return
        if path == "/api/health":
            self._send_json({"status": "ok", "version": __version__})
            return
        if path == "/api/about":
            self._send_json({
                "version": __version__,
                "agents": ["Researcher", "Writer", "FactChecker"],
                "core_modules": ["Pipeline", "Governor", "Verifier", "Context",
                                 "Agent", "MemoryStore", "FanOut", "WebhookNotifier"],
            })
            return
        if path == "/api/memory/recent":
            self._handle_memory_recent()
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/api/run":
            self._handle_run()
            return
        if path == "/api/memory/clear":
            self._handle_memory_clear()
            return
        self._send_json({"error": "not found"}, 404)

    def _handle_run(self) -> None:
        try:
            body = self._read_json()
            task = body.get("task", "").strip()
            if not task:
                self._send_json({"error": "task is required"}, 400)
                return
            strict = body.get("strict", True)
            stop_on_failure = body.get("stop_on_failure", False)
            backend = body.get("backend", "mock")

            llm_kwargs: Dict[str, Any] = {}
            if backend in ("openai", "openai-compat", "ollama", "vllm", "remote"):
                llm_kwargs["retries"] = body.get("retries", 2)
                if body.get("model"):
                    llm_kwargs["model"] = body["model"]
                if body.get("temperature") is not None:
                    llm_kwargs["temperature"] = body["temperature"]
                if body.get("max_tokens") is not None:
                    llm_kwargs["max_tokens"] = body["max_tokens"]
                llm = make_backend("openai", **llm_kwargs)
            else:
                llm = MockLLM()

            governor = Governor(max_agent_calls=10)
            agents = [
                Researcher(name="Researcher", llm=llm),
                Writer(name="Writer", llm=llm),
                FactChecker(name="FactChecker", llm=llm),
            ]
            pipeline = Pipeline(
                agents=agents, governor=governor,
                strict=strict, stop_on_failure=stop_on_failure,
            )
            import time
            t0 = time.time()
            result = pipeline.run(task)
            elapsed = round(time.time() - t0, 3)

            stages = []
            for name in ("Researcher", "Writer", "FactChecker"):
                v = result.get("stage_outputs", {}).get(f"{name}_verdict", {})
                stages.append({
                    "name": name,
                    "verified": v.get("verified", False) if v else None,
                    "checks": v.get("checks", []) if v else [],
                })

            self._send_json({
                "output": result.get("output"),
                "publishable": result.get("publishable"),
                "aborted": result.get("aborted"),
                "warnings": result.get("warnings", []),
                "decision": result.get("decision"),
                "budget": result.get("budget"),
                "trace": result.get("trace", []),
                "trace_summary": result.get("trace_summary"),
                "stages": stages,
                "elapsed": elapsed,
            })
        except LLMError as e:
            self._send_json({"error": f"LLM error: {e}"}, 502)
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _handle_memory_recent(self) -> None:
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        params: Dict[str, str] = {}
        for part in qs.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = v
        limit = min(int(params.get("limit", "50")), 200)
        query = params.get("query", "").strip() or None
        mem = MemoryStore(self.server.memory_path)
        self._send_json(mem.recall(query, limit=limit))

    def _handle_memory_clear(self) -> None:
        MemoryStore(self.server.memory_path).clear()
        self._send_json({"ok": True, "cleared": True})


# ── Server ───────────────────────────────────────────────────────────────
class WebUIServer:
    """Threading HTTP server for the agentflow web UI.

    Args:
        host: bind address (default 127.0.0.1).
        port: port (default 8080).
        memory_path: path to the MemoryStore JSON file.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        memory_path: str = "agentflow_memory.json",
    ) -> None:
        self.host = host
        self.port = port
        self.memory_path = memory_path
        self._httpd: Optional[HTTPServer] = None

    def serve_forever(self) -> None:
        from http.server import ThreadingHTTPServer
        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self._httpd.memory_path = self.memory_path
        url = f"http://{self.host}:{self.port}"
        print(f"\n  \033[36magentflow\033[0m v{__version__} — interactive web UI")
        print(f"  \033[2m→ {url}\033[0m")
        print(f"  \033[2mPress Ctrl+C to stop.\033[0m\n")
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Shutting down.")
            self._httpd.server_close()

    def serve_once(self, timeout: float = 5.0) -> None:
        from http.server import ThreadingHTTPServer
        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self._httpd.memory_path = self.memory_path
        self._httpd.timeout = timeout
        self._httpd.handle_request()
        self._httpd.server_close()


__all__ = ["WebUIServer"]
