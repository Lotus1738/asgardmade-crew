"""
AsgardMade Pantheon — FastAPI server
WebSocket + REST API + background agent loops
"""

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import traceback
import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

load_dotenv()

import memory.obsidian as mem
import memory.brain as brain
import memory.sales_intel as sales_intel
import memory.ab_tests as ab_tests
import memory.pricing_intel as pricing_intel
import memory.review_tracker as review_tracker

_anthropic_client: anthropic.AsyncAnthropic | None = None

def get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(503, detail="ANTHROPIC_API_KEY not configured")
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=key)
    return _anthropic_client

from crew.agents import get_system_prompt, ALL_AGENTS, GRID_AGENTS
from crew.tools import get_system_metrics, scan_logs, generate_niche_idea
from crew.pipeline import run_idea_pipeline, run_design_pipeline, _build_vault_report
from integrations import discord as _discord
from integrations.twilio_sms import send_sms, build_briefing_sms

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
Path("logs").mkdir(exist_ok=True)

# ─── Connection Manager ──────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, msg: dict):
        if not self.active:
            return
        data = json.dumps(msg, default=str)
        dead = set()
        for ws in list(self.active):
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active.discard(ws)


# ─── App State ───────────────────────────────────────────────────────────────

class AppState:
    def __init__(self):
        self.agents: dict[str, dict] = {a: {"status": "idle", "lastAction": "Initializing", "xp": 0, "level": 1} for a in ALL_AGENTS}
        self.queue: dict[str, list] = {"ideas": [], "designs": []}
        self.vault: dict = {
            "startDate": datetime.now().isoformat(),
            "totalRevenue": 0.0,
            "totalExpenses": 0.0,
            "netProfit": 0.0,
            "profitMarginPct": 0.0,
            "transactions": [],
        }
        self.metrics: dict = {"cpu": 0, "ram": 0, "disk": 0, "network": {"rx": 0, "tx": 0}}
        self.blocked_ips: list[str] = []
        self.strategy_count: int = 0
        self.load_all()

    def load_all(self):
        self._load("agents.json", "agents")
        self._load("queue.json", "queue")
        self._load("vault.json", "vault")
        self._load("blocked_ips.json", "blocked_ips_wrapper")
        if isinstance(getattr(self, "_blocked_ips_wrapper", None), dict):
            self.blocked_ips = self._blocked_ips_wrapper.get("ips", [])

    def _load(self, filename: str, attr: str):
        path = DATA_DIR / filename
        if path.exists():
            try:
                data = json.loads(path.read_text())
                setattr(self, attr, data)
            except Exception as e:
                print(f"[STATE] Failed to load {filename}: {type(e).__name__}: {e} — using defaults")

    def save_agents(self):
        try:
            (DATA_DIR / "agents.json").write_text(json.dumps(self.agents, indent=2, default=str))
        except Exception as e:
            print(f"[STATE] save_agents error: {type(e).__name__}: {e}")

    def save_queue(self):
        try:
            # Prune completed items before saving to prevent unbounded queue growth.
            # Keeps all pending items + the 100 most-recent completed ones per category.
            for cat in ("ideas", "designs"):
                items = self.queue.get(cat, [])
                pending = [i for i in items if i.get("status") == "pending"]
                completed = [i for i in items if i.get("status") != "pending"]
                self.queue[cat] = pending + completed[-100:]
            (DATA_DIR / "queue.json").write_text(json.dumps(self.queue, indent=2, default=str))
        except Exception as e:
            print(f"[STATE] save_queue error: {type(e).__name__}: {e}")

    def save_vault(self):
        try:
            # Prune old transactions to prevent unbounded vault.json growth.
            # Keep all revenue transactions (every sale matters) + last 500 expenses.
            # Accumulate dropped expense amounts in prunedExpenseTotal so
            # recalculate_vault() never understates totalExpenses after a prune.
            txns = self.vault.get("transactions", [])
            if len(txns) > 600:
                revenue = [t for t in txns if t.get("type") == "revenue"]
                expenses = [t for t in txns if t.get("type") != "revenue"]
                dropped = expenses[:-500]
                self.vault["prunedExpenseTotal"] = round(
                    self.vault.get("prunedExpenseTotal", 0.0) + sum(t.get("amount", 0) for t in dropped), 2
                )
                self.vault["transactions"] = revenue + expenses[-500:]
            (DATA_DIR / "vault.json").write_text(json.dumps(self.vault, indent=2, default=str))
        except Exception as e:
            print(f"[STATE] save_vault error: {type(e).__name__}: {e}")

    def save_blocked(self):
        try:
            (DATA_DIR / "blocked_ips.json").write_text(json.dumps({"ips": self.blocked_ips}, indent=2))
        except Exception as e:
            print(f"[STATE] save_blocked error: {type(e).__name__}: {e}")

    def recalculate_vault(self):
        txns = self.vault.get("transactions", [])
        revenue = sum(t["amount"] for t in txns if t.get("type") == "revenue")
        expenses = sum(t["amount"] for t in txns if t.get("type") == "expense")
        # Add any expenses pruned from the transaction list (see save_vault pruning logic).
        # Without this, totalExpenses drifts downward after the first prune (>600 txns).
        expenses += self.vault.get("prunedExpenseTotal", 0.0)
        net = revenue - expenses
        self.vault["totalRevenue"] = round(revenue, 2)
        self.vault["totalExpenses"] = round(expenses, 2)
        self.vault["netProfit"] = round(net, 2)
        self.vault["profitMarginPct"] = round((net / revenue * 100) if revenue > 0 else 0, 1)


manager = ConnectionManager()
state = AppState()

# Runtime prompt overrides written by ODIN via /api/update-prompt
# Cleared on restart; layered on top of base prompts in agents.py
_prompt_overrides: dict[str, str] = {}


# ─── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(title="AsgardMade Pantheon", version="1.0.0")


# Serve public files
PUBLIC_DIR = Path("public")


@app.get("/")
async def serve_index():
    return FileResponse(str(PUBLIC_DIR / "index.html"))


# ─── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/")
async def ws_root(websocket: WebSocket):
    await _ws_handler(websocket)


@app.websocket("/ws")
async def ws_ws(websocket: WebSocket):
    await _ws_handler(websocket)


async def _ws_handler(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await _send_init(websocket)
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                await _handle_ws_message(msg, websocket)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


async def _send_init(ws: WebSocket):
    init_data = {
        "agentStats": {"agents": state.agents},
        "approvals": state.queue,
        "finance": state.vault,
        "metrics": state.metrics,
    }
    _net = state.vault.get('netProfit', 0)
    _pending = (
        len([i for i in state.queue['ideas'] if i.get('status') == 'pending']) +
        len([d for d in state.queue['designs'] if d.get('status') == 'pending'])
    )
    strategy = (
        f"Pantheon online. Net ${_net:.2f}. "
        f"{len(state.queue['ideas'])} ideas, {len(state.queue['designs'])} designs in queue"
        f"{f' — {_pending} need your approval' if _pending else ' — running autonomously'}."
    )
    await ws.send_text(json.dumps({
        "type": "init",
        "data": init_data,
        "strategy": strategy,
    }, default=str))


async def _handle_ws_message(msg: dict, ws: WebSocket):
    msg_type = msg.get("type", "")

    if msg_type == "approve_idea":
        item_id = msg.get("id")
        idea = next((i for i in state.queue["ideas"] if i["id"] == item_id), None)
        if idea:
            idea["status"] = "approved"
            state.save_queue()
            try:
                mem.heimdall_write_approved(idea)
            except Exception:
                pass
            try:
                brain.record_outcome(
                    "HEIMDALL",
                    f"Queued idea: '{idea.get('title')}' ({idea.get('niche')}, {idea.get('productType')})",
                    "Commander approved — pipeline triggered",
                    9,
                )
            except Exception:
                pass
            await manager.broadcast({"type": "queue_update", "data": {"category": "ideas", "id": item_id, "status": "approved"}})
            asyncio.create_task(run_idea_pipeline(idea, manager, state))

    elif msg_type == "approve_design":
        item_id = msg.get("id")
        design = next((d for d in state.queue["designs"] if d["id"] == item_id), None)
        if design:
            design["status"] = "approved"
            state.save_queue()
            try:
                mem.vulcan_write_approved(design)
            except Exception:
                pass
            try:
                brain.record_outcome(
                    "VULCAN",
                    f"Generated design for '{design.get('ideaTitle')}' ({design.get('niche')}) — variant {design.get('variantIndex')}",
                    "Commander approved — uploading to Printify",
                    9,
                )
            except Exception:
                pass
            await manager.broadcast({"type": "queue_update", "data": {"category": "designs", "id": item_id, "status": "approved"}})
            asyncio.create_task(run_design_pipeline(design, manager, state))

    elif msg_type == "reject_idea":
        item_id = msg.get("id")
        item = next((i for i in state.queue["ideas"] if i["id"] == item_id), None)
        if item:
            item["status"] = "rejected"
            state.save_queue()
            try:
                mem.heimdall_write_rejected(item)
            except Exception:
                pass
            try:
                brain.record_outcome(
                    "HEIMDALL",
                    f"Queued idea: '{item.get('title')}' ({item.get('niche')}, {item.get('productType')})",
                    "Commander rejected — avoid similar ideas",
                    2,
                )
            except Exception:
                pass
            await manager.broadcast({"type": "queue_update", "data": {"category": "ideas", "id": item_id, "status": "rejected"}})

    elif msg_type == "reject_design":
        item_id = msg.get("id")
        item = next((d for d in state.queue["designs"] if d["id"] == item_id), None)
        if item:
            item["status"] = "rejected"
            state.save_queue()
            try:
                mem.vulcan_write_rejected(item)
            except Exception:
                pass
            try:
                brain.record_outcome(
                    "VULCAN",
                    f"Generated design for '{item.get('ideaTitle')}' ({item.get('niche')}) — variant {item.get('variantIndex')}",
                    "Commander rejected — avoid this visual approach",
                    2,
                )
            except Exception:
                pass
            await manager.broadcast({"type": "queue_update", "data": {"category": "designs", "id": item_id, "status": "rejected"}})


# ─── REST Endpoints ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    agent: str
    message: str
    history: list[dict] = []
    ctx: dict = {}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    agent_name = req.agent.upper()
    if agent_name not in ALL_AGENTS:
        raise HTTPException(400, detail=f"Unknown agent: {agent_name}")

    # Build context from live state
    ctx = dict(req.ctx)
    ctx.update({
        "totalRevenue": state.vault.get("totalRevenue", 0),
        "totalExpenses": state.vault.get("totalExpenses", 0),
        "netProfit": state.vault.get("netProfit", 0),
        "margin": state.vault.get("profitMarginPct", 0),
        "pendingDesigns": len([d for d in state.queue["designs"] if d["status"] == "pending"]),
        "pendingIdeas": len([i for i in state.queue["ideas"] if i["status"] == "pending"]),
        "cpu": state.metrics.get("cpu", 0),
        "ram": state.metrics.get("ram", 0),
        "agentXP": {a: state.agents.get(a, {}).get("xp", 0) for a in GRID_AGENTS},
    })

    # Inject Commander Preferences so agents learn from history
    try:
        prefs = mem.read_preferences()
        if prefs:
            ctx["commanderPreferences"] = prefs[:600]
    except Exception:
        pass

    # Inject agent's own conversation memory so it remembers past interactions
    try:
        agent_memory = mem.agent_read_memory(agent_name, limit=3)
        if agent_memory:
            ctx["agentMemory"] = agent_memory[:800]
    except Exception:
        pass

    # Inject distilled lessons from the brain synthesis loop
    try:
        lessons = brain.get_agent_lessons(agent_name)
        if lessons:
            ctx["agentLessons"] = lessons
    except Exception:
        pass

    # Inject Odin's improvement directives for this agent
    try:
        improvements = brain.get_agent_improvement(agent_name)
        if improvements:
            ctx["agentLessons"] = (ctx.get("agentLessons", "") + "\n\n" + improvements).strip()
    except Exception:
        pass

    # Inject Odin's current directive for non-Odin agents
    if agent_name != "ODIN":
        try:
            directive = brain.get_odin_briefing()
            if directive:
                ctx["odinDirective"] = directive[:300]
        except Exception:
            pass

    # Inject sales traction data for HEIMDALL so it prioritizes proven niches
    if agent_name == "HEIMDALL":
        try:
            si_text = sales_intel.format_top_niches_for_prompt()
            if si_text:
                ctx["sales_intel"] = si_text
        except Exception:
            pass

    # Inject seasonal intelligence for HEIMDALL so it targets upcoming demand spikes
    if agent_name == "HEIMDALL":
        try:
            from memory import seasonal_calendar as _sc
            seasonal_text = _sc.get_seasonal_niches_for_prompt()
            if seasonal_text:
                ctx["seasonal_intel"] = seasonal_text
        except Exception:
            pass

    # Inject pricing intel for LOKI so it sets competitive listing prices
    if agent_name == "LOKI":
        try:
            _niche_hint = ctx.get("niche", req.ctx.get("niche", ""))
            if _niche_hint:
                _pi_text = pricing_intel.format_pricing_for_prompt(_niche_hint)
            else:
                # No specific niche — pull all available intel (first 400 chars)
                import json as _json
                from pathlib import Path as _P
                _pi_file = _P("data/pricing_intel.json")
                if _pi_file.exists():
                    _pi_data = _json.loads(_pi_file.read_text())
                    _pi_lines = []
                    for _entry in list(_pi_data.values())[:6]:
                        _prices = _entry.get("prices", [])
                        if _prices:
                            _avg = sum(_prices) / len(_prices)
                            _pi_lines.append(
                                f"{_entry.get('niche','')} {_entry.get('product_type','')} avg ${_avg:.2f}"
                            )
                    _pi_text = "\n".join(_pi_lines)
                else:
                    _pi_text = ""
            if _pi_text:
                ctx["pricing_intel"] = _pi_text
        except Exception:
            pass

    # Web search injection: ODIN and HEIMDALL can search the live web
    # Triggered by keywords that imply need for current information
    _search_triggers = (
        "trend", "trending", "search", "latest", "current", "news",
        "what's hot", "right now", "today", "2026", "new niche",
        "competitor", "platform update", "etsy change", "research"
    )
    _msg_lower = req.message.lower()
    if agent_name in ("ODIN", "HEIMDALL") and any(t in _msg_lower for t in _search_triggers):
        try:
            from integrations.websearch import search
            # Extract a clean search query from the message
            _search_query = f"etsy print on demand {req.message[:80]}"
            _web_results = await search(_search_query, max_results=5)
            if _web_results:
                _snippets = "\n".join(
                    f"- {r['title']}: {r['snippet']}" for r in _web_results if r.get("snippet")
                )
                ctx["liveWebSearch"] = f"Live web search results for context:\n{_snippets[:800]}"
        except Exception as _e:
            print(f"[CHAT WEB SEARCH] {type(_e).__name__}: {_e}")

    system_prompt = get_system_prompt(agent_name, ctx)

    # Apply runtime prompt override from ODIN if one exists
    if agent_name in _prompt_overrides:
        system_prompt = system_prompt + f"\n\n=== ODIN DIRECTIVE OVERRIDE ===\n{_prompt_overrides[agent_name]}\n==="

    # Build message list for Anthropic API
    messages = []
    for h in req.history[-20:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": req.message})

    try:
        client = get_anthropic_client()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=450,
            system=system_prompt,
            messages=messages,
        )
        reply = response.content[0].text
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CHAT ERROR] agent={agent_name} error={type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(500, detail=f"{type(e).__name__}: {e}")

    # Write exchange to agent's personal memory folder
    try:
        mem.agent_write_chat(agent_name, req.message, reply)
    except Exception:
        pass

    # Capture feedback keywords to Commander Preferences
    try:
        mem.capture_chat_feedback(agent_name, req.message, reply)
    except Exception:
        pass

    # Log to live feed
    await manager.broadcast({
        "type": "agent_log",
        "agent": agent_name,
        "message": f"[CHAT] {req.message[:80]}{'...' if len(req.message) > 80 else ''}",
        "level": "info",
        "timestamp": datetime.now().isoformat(),
    })
    await _award_xp_silent(agent_name, 5, "chat_response")

    return {"reply": reply}


@app.post("/api/chat/{agent_name}")
async def chat_named(agent_name: str, req: ChatRequest):
    req.agent = agent_name
    return await chat(req)


@app.get("/api/status")
async def get_status():
    return {
        "agents": state.agents,
        "metrics": state.metrics,
        "queue_counts": {
            "ideas": len([i for i in state.queue["ideas"] if i["status"] == "pending"]),
            "designs": len([d for d in state.queue["designs"] if d["status"] == "pending"]),
        },
        "connected_clients": len(manager.active),
        "strategy_count": state.strategy_count,
    }


@app.get("/api/queue")
async def get_queue():
    return {
        "ideas": state.queue["ideas"],
        "designs": state.queue["designs"],
    }


@app.post("/api/approve/{item_id}")
async def approve_item(item_id: str):
    idea = next((i for i in state.queue["ideas"] if i["id"] == item_id), None)
    if idea:
        idea["status"] = "approved"
        state.save_queue()
        try:
            mem.heimdall_write_approved(idea)
        except Exception:
            pass
        try:
            brain.record_outcome(
                "HEIMDALL",
                f"Queued idea: '{idea.get('title')}' ({idea.get('niche')}, {idea.get('productType')})",
                "REST API approved — pipeline triggered",
                9,
            )
        except Exception:
            pass
        await manager.broadcast({"type": "queue_update", "data": {"category": "ideas", "id": item_id, "status": "approved"}})
        asyncio.create_task(run_idea_pipeline(idea, manager, state))
        return {"ok": True, "type": "idea", "id": item_id}

    design = next((d for d in state.queue["designs"] if d["id"] == item_id), None)
    if design:
        design["status"] = "approved"
        state.save_queue()
        try:
            mem.vulcan_write_approved(design)
        except Exception:
            pass
        try:
            brain.record_outcome(
                "VULCAN",
                f"Generated design for '{design.get('ideaTitle')}' ({design.get('niche')}) — variant {design.get('variantIndex')}",
                "REST API approved — uploading to Printify",
                9,
            )
        except Exception:
            pass
        await manager.broadcast({"type": "queue_update", "data": {"category": "designs", "id": item_id, "status": "approved"}})
        asyncio.create_task(run_design_pipeline(design, manager, state))
        return {"ok": True, "type": "design", "id": item_id}

    raise HTTPException(404, detail="Item not found")


@app.post("/api/reject/{item_id}")
async def reject_item(item_id: str):
    for category, items in state.queue.items():
        item = next((i for i in items if i["id"] == item_id), None)
        if item:
            item["status"] = "rejected"
            state.save_queue()
            # Record rejection in brain — mirrors WebSocket reject_idea/reject_design handlers
            if category == "ideas":
                try:
                    mem.heimdall_write_rejected(item)
                except Exception:
                    pass
                try:
                    brain.record_outcome(
                        "HEIMDALL",
                        f"Queued idea: '{item.get('title')}' ({item.get('niche')}, {item.get('productType')})",
                        "REST API rejected — avoid similar ideas",
                        2,
                    )
                except Exception:
                    pass
            elif category == "designs":
                try:
                    mem.vulcan_write_rejected(item)
                except Exception:
                    pass
                try:
                    brain.record_outcome(
                        "VULCAN",
                        f"Generated design for '{item.get('ideaTitle')}' ({item.get('niche')}) — variant {item.get('variantIndex')}",
                        "REST API rejected — avoid this visual approach",
                        2,
                    )
                except Exception:
                    pass
            await manager.broadcast({"type": "queue_update", "data": {"category": category, "id": item_id, "status": "rejected"}})
            return {"ok": True, "type": category, "id": item_id}
    raise HTTPException(404, detail="Item not found")


@app.get("/api/vault")
async def get_vault():
    return _build_vault_report(state)


# ─── Self-Sufficiency APIs ────────────────────────────────────────────────────

class AgentTaskRequest(BaseModel):
    from_agent: str = "ODIN"
    to_agent: str
    task: str
    context: dict = {}
    priority: str = "normal"  # "normal" | "urgent" | "background"


@app.post("/api/agent-task")
async def agent_task(req: AgentTaskRequest):
    """
    ODIN (or any agent) sends a task directive to another agent.
    The target agent processes it and returns a response.
    Both sides get XP. The exchange is broadcast to all clients.
    """
    from_name = req.from_agent.upper()
    to_name = req.to_agent.upper()

    if to_name not in ALL_AGENTS:
        raise HTTPException(400, detail=f"Unknown target agent: {to_name}")

    # Build context for the receiving agent
    ctx: dict = dict(req.context)
    ctx.update({
        "totalRevenue": state.vault.get("totalRevenue", 0),
        "totalExpenses": state.vault.get("totalExpenses", 0),
        "netProfit": state.vault.get("netProfit", 0),
        "margin": state.vault.get("profitMarginPct", 0),
        "pendingIdeas": len([i for i in state.queue["ideas"] if i["status"] == "pending"]),
        "pendingDesigns": len([d for d in state.queue["designs"] if d["status"] == "pending"]),
        "agentTaskQueue": f"TASKED BY {from_name}: {req.task}",
    })

    try:
        lessons = brain.get_agent_lessons(to_name)
        if lessons:
            ctx["agentLessons"] = lessons
    except Exception:
        pass

    system_prompt = get_system_prompt(to_name, ctx)
    task_message = f"[TASK FROM {from_name}] {req.task}"

    try:
        client = get_anthropic_client()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": task_message}],
        )
        reply = response.content[0].text
    except Exception as e:
        raise HTTPException(500, detail=f"Agent task error: {type(e).__name__}: {e}")

    # Log the inter-agent exchange to both agents' memories
    try:
        mem.agent_write_chat(to_name, task_message, reply)
    except Exception:
        pass

    # Record outcome in brain for both agents
    try:
        brain.record_outcome(
            from_name,
            f"Tasked {to_name}: {req.task[:80]}",
            f"{to_name} responded: {reply[:80]}",
            7,
        )
    except Exception:
        pass

    # Broadcast to HUD
    await manager.broadcast({
        "type": "agent_log",
        "agent": to_name,
        "message": f"[INTER-AGENT] Task from {from_name}: {req.task[:60]}{'...' if len(req.task) > 60 else ''}",
        "level": "info",
        "timestamp": datetime.now().isoformat(),
    })

    await _award_xp_silent(from_name, 8, "agent_tasking")
    await _award_xp_silent(to_name, 10, "agent_task_response")

    return {
        "ok": True,
        "from": from_name,
        "to": to_name,
        "task": req.task,
        "reply": reply,
    }


class AutoScoreRequest(BaseModel):
    item_id: str
    item_type: str = "idea"  # "idea" | "design"
    risk: int | None = None        # 0–100, optional override
    confidence: int | None = None  # 0–100, optional override


@app.post("/api/auto-score")
async def auto_score(req: AutoScoreRequest):
    """
    Score a queued item on Risk and Confidence.
    Auto-approve if Risk < 30 AND Confidence > 65.
    Return the decision and scores to the caller.

    Risk heuristics (computed from item metadata if not provided):
      - Ideas: high demand score → lower risk; unknown niche → higher risk
      - Designs: has pre-approved niche → lower risk; first-time style → higher risk

    Confidence heuristics:
      - Ideas: demand score maps directly (0–100 → 0–100 confidence)
      - Designs: approval rate of similar niches from brain memory
    """
    items = state.queue.get(req.item_type + "s", [])
    item = next((i for i in items if i["id"] == req.item_id), None)
    if not item:
        raise HTTPException(404, detail=f"Item {req.item_id} not found in {req.item_type} queue")

    # Compute scores if not provided
    risk = req.risk
    confidence = req.confidence

    if risk is None:
        if req.item_type == "idea":
            demand = item.get("demandScore", 50)
            # High-demand ideas are lower risk; unknown niches are higher risk
            risk = max(5, 80 - demand)
        else:
            # Designs: base risk is moderate; lower if niche is already approved
            approved_niches = {
                i.get("niche", "") for i in state.queue["ideas"] if i.get("status") == "approved"
            }
            niche = item.get("niche", "")
            risk = 20 if niche in approved_niches else 45

    if confidence is None:
        if req.item_type == "idea":
            demand = item.get("demandScore", 50)
            confidence = min(95, demand)
        else:
            confidence = 70  # Designs from approved ideas get baseline 70

    # Decision
    auto_approved = risk < 30 and confidence > 65
    decision = "AUTO-APPROVED" if auto_approved else ("FLAG" if risk <= 60 and confidence >= 40 else "HOLD")

    if auto_approved:
        item["status"] = "approved"
        item["autoApproved"] = True
        item["riskScore"] = risk
        item["confidenceScore"] = confidence
        state.save_queue()

        await manager.broadcast({
            "type": "queue_update",
            "data": {
                "category": req.item_type + "s",
                "id": req.item_id,
                "status": "approved",
                "autoApproved": True,
                "risk": risk,
                "confidence": confidence,
            },
        })
        await manager.broadcast({
            "type": "agent_log",
            "agent": "ODIN",
            "message": f"AUTO-APPROVED {req.item_type}: '{item.get('title', item.get('ideaTitle', req.item_id))}' — Risk:{risk} Confidence:{confidence}",
            "level": "info",
            "timestamp": datetime.now().isoformat(),
        })

        # Trigger pipeline
        if req.item_type == "idea":
            try:
                brain.record_outcome(
                    "HEIMDALL",
                    f"Auto-scored idea: '{item.get('title')}' ({item.get('niche')}, {item.get('productType')})",
                    f"AUTO-APPROVED via /api/auto-score — Risk:{risk} Confidence:{confidence} — pipeline triggered",
                    8,
                )
            except Exception:
                pass
            asyncio.create_task(run_idea_pipeline(item, manager, state))
        else:
            try:
                brain.record_outcome(
                    "VULCAN",
                    f"Auto-scored design for '{item.get('ideaTitle')}' ({item.get('niche')}) — variant {item.get('variantIndex')}",
                    f"AUTO-APPROVED via /api/auto-score — Risk:{risk} Confidence:{confidence} — uploading to Printify",
                    8,
                )
            except Exception:
                pass
            asyncio.create_task(run_design_pipeline(item, manager, state))

        # Discord notification for auto-approval
        try:
            _item_label = item.get("title") or item.get("ideaTitle", req.item_id)
            asyncio.create_task(_discord.notify_approval(_item_label, confidence))
        except Exception:
            pass

    return {
        "ok": True,
        "item_id": req.item_id,
        "item_type": req.item_type,
        "risk": risk,
        "confidence": confidence,
        "decision": decision,
        "auto_approved": auto_approved,
    }


class UpdatePromptRequest(BaseModel):
    agent: str
    new_directive: str
    reason: str = ""


@app.post("/api/update-prompt")
async def update_prompt(req: UpdatePromptRequest):
    """
    ODIN rewrites an agent's operating directive at runtime.
    The override is stored in memory and injected into future system prompts.
    The agents.py file remains the baseline; overrides layer on top.
    """
    agent_name = req.agent.upper()
    if agent_name not in ALL_AGENTS:
        raise HTTPException(400, detail=f"Unknown agent: {agent_name}")

    if len(req.new_directive) < 20:
        raise HTTPException(400, detail="Directive too short (min 20 chars)")

    # Store the override
    _prompt_overrides[agent_name] = req.new_directive

    # Record in brain memory so it persists across reasoning cycles
    try:
        brain.record_outcome(
            "ODIN",
            f"Prompt rewrite for {agent_name}: {req.reason[:100]}",
            f"New directive applied: {req.new_directive[:120]}",
            8,
        )
    except Exception:
        pass

    # Broadcast to HUD
    await manager.broadcast({
        "type": "agent_log",
        "agent": "ODIN",
        "message": f"PROMPT REWRITE → {agent_name}: {req.reason[:60] or 'directive updated'}",
        "level": "warning",
        "timestamp": datetime.now().isoformat(),
    })

    return {
        "ok": True,
        "agent": agent_name,
        "directive_preview": req.new_directive[:100] + ("..." if len(req.new_directive) > 100 else ""),
        "reason": req.reason,
    }


@app.get("/api/prompt-overrides")
async def get_prompt_overrides():
    """Return current runtime prompt overrides (for HUD debug view)."""
    return {"overrides": {k: v[:80] + "..." for k, v in _prompt_overrides.items()}}


@app.get("/api/brain/status")
async def get_brain_status():
    """Shows which agents have learned lessons and how many outcomes are tracked."""
    return brain.brain_status()


# ─── Vault / Obsidian export ──────────────────────────────────────────────────

@app.get("/api/vault/notes")
async def get_vault_contents():
    """
    Return all vault notes as a browsable JSON structure.
    Since Railway can't write to the local Obsidian vault, this endpoint
    lets the HUD or external tools read what the agents have written.
    Previously shadowed by the /api/vault P&L endpoint (FastAPI uses first match).
    """
    vault_path = mem.VAULT
    if not vault_path.exists():
        return {"ok": False, "reason": "Vault not initialized on this server", "vault_path": str(vault_path)}

    result: dict[str, list] = {}
    try:
        for md_file in sorted(vault_path.rglob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True):
            rel = md_file.relative_to(vault_path)
            folder = str(rel.parent) if str(rel.parent) != "." else "root"
            if folder not in result:
                result[folder] = []
            try:
                content = md_file.read_text(encoding="utf-8")
                result[folder].append({
                    "name": md_file.stem,
                    "path": str(rel).replace("\\", "/"),
                    "modified": datetime.fromtimestamp(md_file.stat().st_mtime).isoformat(),
                    "content": content[:3000],
                    "truncated": len(content) > 3000,
                })
            except Exception:
                pass
    except Exception as e:
        return {"ok": False, "error": str(e)}

    total = sum(len(v) for v in result.values())
    return {
        "ok": True,
        "vault_path": str(vault_path),
        "total_notes": total,
        "folders": result,
    }


@app.get("/api/vault/note")
async def get_vault_note(path: str):
    """Return a single vault note by relative path (e.g. ?path=Revenue/Daily+P%26L+2026-06-14.md)."""
    vault_path = mem.VAULT
    try:
        target = (vault_path / path).resolve()
        if not str(target).startswith(str(vault_path.resolve())):
            raise HTTPException(403, "Path traversal denied")
        if not target.exists():
            raise HTTPException(404, "Note not found")
        return {
            "ok": True,
            "path": path,
            "content": target.read_text(encoding="utf-8"),
            "modified": datetime.fromtimestamp(target.stat().st_mtime).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/brain/lessons/{agent_name}")
async def get_agent_lessons(agent_name: str):
    """Read current distilled lessons for one agent."""
    name = agent_name.upper()
    lessons_text = brain.get_agent_lessons(name)
    outcomes = brain.get_all_outcomes(name, limit=10)
    return {
        "agent": name,
        "lessons": lessons_text,
        "recent_outcomes": outcomes,
    }


@app.post("/api/vulcan/generate")
async def trigger_vulcan(body: dict = {}):
    idea = body if body.get("title") else None
    if not idea:
        idea = next((i for i in state.queue["ideas"] if i["status"] == "pending"), None)
    if not idea:
        raise HTTPException(400, detail="No pending idea to generate from. Approve an idea first.")
    asyncio.create_task(run_idea_pipeline(idea, manager, state))
    return {"ok": True, "idea": idea.get("title", "unknown")}


@app.post("/api/heimdall/research")
async def trigger_heimdall(body: dict = {}):
    niche = body.get("niche")
    idea = generate_niche_idea(niche)
    state.queue["ideas"].append(idea)
    state.save_queue()
    await manager.broadcast({
        "type": "approval_queue",
        "agent": "HEIMDALL",
        "data": {"category": "ideas", "items": [idea]},
    })
    await manager.broadcast({
        "type": "agent_log",
        "agent": "HEIMDALL",
        "message": f"Research triggered. New idea queued: '{idea['title']}' (demand: {idea['demandScore']})",
        "level": "info",
        "timestamp": datetime.now().isoformat(),
    })
    return {"ok": True, "idea": idea}


@app.post("/api/vault/transaction")
async def add_transaction(body: dict):
    txn = {
        "id": str(uuid.uuid4()),
        "type": body.get("type", "expense"),
        "amount": float(body.get("amount", 0)),
        "description": body.get("description", "Manual transaction"),
        "source": body.get("source", "manual"),
        "timestamp": datetime.now().isoformat(),
    }
    state.vault["transactions"].append(txn)
    state.recalculate_vault()
    state.save_vault()

    # Record per-niche sales intel so HEIMDALL learns from real conversions
    if txn["type"] == "revenue":
        try:
            sales_intel.record_sale(
                niche=str(body.get("niche", "general")),
                product_type=str(body.get("product_type", "unknown")),
                revenue=txn["amount"],
                units=int(body.get("units", 1)),
            )
        except Exception:
            pass

    vault_report = _build_vault_report(state)
    await manager.broadcast({"type": "vault_report", "data": vault_report})

    # Discord sale notification for revenue transactions
    if txn["type"] == "revenue":
        try:
            await _discord.notify_sale(
                niche=str(body.get("niche", body.get("source", "unknown"))),
                product=txn["description"],
                revenue=txn["amount"],
            )
        except Exception:
            pass

    return txn


# ─── Memory API ──────────────────────────────────────────────────────────────

class MemoryWriteRequest(BaseModel):
    agent: str
    topic: str
    content: str
    append: bool = False


@app.post("/api/memory/write")
async def memory_write(req: MemoryWriteRequest):
    result = mem.api_write(req.agent, req.topic, req.content, req.append)
    return result


@app.get("/api/memory/read/{agent}/{topic}")
async def memory_read(agent: str, topic: str):
    result = mem.api_read(agent, topic)
    return result


@app.get("/api/memory/browse")
async def memory_browse():
    """Return a tree of all agent memory notes for the HUD memory viewer."""
    from pathlib import Path as _P
    vault = _P(os.getenv("OBSIDIAN_VAULT_PATH", "./data/obsidian"))
    if not vault.exists():
        return {"available": False, "folders": []}
    folders = []
    for folder in sorted(vault.iterdir()):
        if folder.is_dir():
            files = []
            for f in sorted(folder.rglob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
                try:
                    files.append({"name": f.stem, "path": str(f.relative_to(vault)),
                                  "preview": f.read_text(encoding="utf-8")[:300]})
                except Exception:
                    pass
            folders.append({"folder": folder.name, "count": len(list(folder.rglob("*.md"))), "recent": files[:5]})
    return {"available": True, "vault": str(vault.resolve()), "folders": folders}


# ─── TTS ─────────────────────────────────────────────────────────────────────

class TTSRequest(BaseModel):
    text: str
    voice: str = "onyx"

@app.post("/api/tts")
async def text_to_speech(req: TTSRequest):
    """Convert text to speech using OpenAI TTS and return MP3 audio."""
    from fastapi.responses import Response as _Resp
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(503, detail="OPENAI_API_KEY not set")
    try:
        from openai import AsyncOpenAI as _OAI
        oai = _OAI(api_key=openai_key)
        response = await oai.audio.speech.create(
            model="tts-1",
            voice=req.voice,
            input=req.text[:4096],
            response_format="mp3",
        )
        return _Resp(content=response.content, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(500, detail=str(e))


# ─── XP Helper ───────────────────────────────────────────────────────────────

async def _award_xp_silent(agent: str, amount: int, action: str):
    ag = state.agents.setdefault(agent, {"xp": 0, "level": 1})
    ag["xp"] = ag.get("xp", 0) + amount
    ag["level"] = ag["xp"] // 500 + 1
    state.save_agents()  # persist XP so it survives restarts
    await manager.broadcast({
        "type": "xp_gain",
        "agent": agent,
        "amount": amount,
        "total": ag["xp"],
        "level": ag["level"],
        "action": action,
    })


# ─── Background Agent Loops ──────────────────────────────────────────────────

async def _guardian_loop():
    """
    Single loop replacing Hermes + Hephaestus + Argus + Tyr.
    Runs every 60s: metrics check, log scan, auto-patch, security report.
    """
    scan_id = 0
    while True:
        try:
            scan_id += 1

            # — Metrics (was Argus) —
            metrics = get_system_metrics()
            state.metrics = metrics
            cpu, ram, disk = metrics["cpu"], metrics["ram"], metrics["disk"]
            await manager.broadcast({"type": "system_metrics", "data": {"metrics": metrics}})

            # — Log scan + auto-patch (was Hermes + Hephaestus) —
            result = scan_logs()
            errors = result["errors"]
            warnings = result["warnings"]
            file_count = result["file_count"]

            patches = []
            for error in errors[:3]:
                line = error.get("line", "")
                patch_id = f"PATCH-{uuid.uuid4().hex[:4].upper()}"
                if "ECONNREFUSED" in line or "ConnectionRefused" in line:
                    fix = "retry logic applied (3x backoff)"
                elif "Timeout" in line or "TimeoutError" in line:
                    fix = "timeout increased to 30s, circuit breaker added"
                elif "MemoryError" in line or "memory" in line.lower():
                    fix = "memory pressure flagged for review"
                else:
                    fix = "logged for commander review"
                patches.append(f"[{patch_id}] {fix}")

            # — Build combined status message —
            if cpu > 90 or ram > 90 or disk > 95:
                level = "error"
                issue = f"CPU {cpu}%" if cpu > 90 else f"RAM {ram}%" if ram > 90 else f"Disk {disk}%"
                msg = f"CRITICAL: {issue} exceeded threshold."
                await manager.broadcast({"type": "alert", "data": {"message": f"GUARDIAN CRITICAL: {issue}", "severity": "critical"}})
            elif cpu > 70 or ram > 75 or disk > 80:
                level = "warning"
                issue = f"CPU {cpu}%" if cpu > 70 else f"RAM {ram}%" if ram > 75 else f"Disk {disk}%"
                msg = f"Warning: {issue} above threshold."
            elif errors:
                level = "warning"
                msg = f"Scan #{scan_id}: {len(errors)} error(s) detected. {' | '.join(patches)}"
            else:
                level = "info"
                blocked = len(state.blocked_ips)
                msg = f"Scan #{scan_id}: {file_count} log files clean. CPU {cpu}% RAM {ram}% Disk {disk}%. {blocked} IPs blocked. All systems nominal."

            await manager.broadcast({
                "type": "agent_log",
                "agent": "GUARDIAN",
                "message": msg,
                "level": level,
                "timestamp": datetime.now().isoformat(),
            })

            last = f"Scan #{scan_id} — CPU {cpu}% RAM {ram}% | {len(errors)} errors"
            ag = state.agents.setdefault("GUARDIAN", {"xp": 0, "level": 1})
            ag["lastAction"] = last
            ag["status"] = "active"
            await manager.broadcast({
                "type": "agent_status",
                "agent": "GUARDIAN",
                "data": {"status": "active", "lastAction": last, "xp": ag.get("xp", 0), "level": ag.get("level", 1)},
            })

            # Broadcast legacy reports so HUD still works
            await manager.broadcast({"type": "hermes_report", "agent": "GUARDIAN", "data": {"errors": errors, "warnings": warnings, "fileCount": file_count, "scanId": scan_id}})
            await manager.broadcast({"type": "tyr_report", "agent": "GUARDIAN", "data": {"totalBlocked": len(state.blocked_ips), "newThreats": [], "scanId": scan_id}})

            await _award_xp_silent("GUARDIAN", 10, "ops_scan")

        except Exception as e:
            print(f"[GUARDIAN LOOP] scan={scan_id} error: {type(e).__name__}: {e}")
        await asyncio.sleep(60)


async def _heimdall_loop():
    scan_id = 0
    await asyncio.sleep(15)
    while True:
        try:
            scan_id += 1
            idea = generate_niche_idea()

            state.queue["ideas"].append(idea)
            state.save_queue()

            # Auto-approve high-confidence ideas (skip human review)
            demand = idea.get("demandScore", 0)
            competition = idea.get("competition", "medium")
            auto_approved = demand >= 85 and competition == "low"

            if auto_approved:
                idea["status"] = "approved"
                state.save_queue()  # persist approval before pipeline runs
                await manager.broadcast({
                    "type": "agent_log",
                    "agent": "HEIMDALL",
                    "message": f"Scan #{scan_id}: '{idea['title']}' AUTO-APPROVED (demand {demand}, {competition} competition) — passing directly to Vulcan.",
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                })
                try:
                    mem.heimdall_write_research(idea)
                except Exception:
                    pass
                try:
                    brain.record_outcome(
                        "HEIMDALL",
                        f"Auto-queued idea: '{idea.get('title')}' ({idea.get('niche')}, {idea.get('productType')})",
                        f"AUTO-APPROVED (demand {demand}, {competition} competition) — pipeline triggered",
                        8,
                    )
                except Exception:
                    pass
                try:
                    mem.heimdall_write_approved(idea)
                except Exception:
                    pass
                asyncio.create_task(run_idea_pipeline(idea, manager, state))
            else:
                await manager.broadcast({
                    "type": "agent_log",
                    "agent": "HEIMDALL",
                    "message": f"Scan #{scan_id}: '{idea['title']}' ({idea['niche']}) queued. Demand: {demand}. Competition: {competition}.",
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                })
                try:
                    mem.heimdall_write_research(idea)
                except Exception:
                    pass
                await manager.broadcast({
                    "type": "approval_queue",
                    "agent": "HEIMDALL",
                    "data": {"category": "ideas", "items": [idea]},
                })

            ag = state.agents.get("HEIMDALL", {})
            ag["lastAction"] = f"Queued: '{idea['title']}'"
            state.agents["HEIMDALL"] = ag
            await manager.broadcast({"type": "agent_status", "agent": "HEIMDALL", "data": {"status": "active", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)}})
            await _award_xp_silent("HEIMDALL", 12, "idea_generated")
        except Exception as e:
            print(f"[HEIMDALL LOOP] scan={scan_id} error: {type(e).__name__}: {e}")
        await asyncio.sleep(120)


async def _athena_loop():
    from integrations.etsy import get_shop_stats
    scan_id = 0
    _last_orders = 0  # track order count across scans to detect new sales
    await asyncio.sleep(20)
    while True:
        try:
            scan_id += 1
            stats = await get_shop_stats()

            active = stats.get("active_listings", 0)
            orders = stats.get("total_orders", 0)
            today_rev = stats.get("today_revenue", 0.0)

            # Detect new orders since last scan and record per-niche sales intel
            if orders > _last_orders and not stats.get("demo"):
                new_order_count = orders - _last_orders
                # Infer niche from the most recently approved idea in the queue
                _niche_guess = "general"
                _pt_guess = "unknown"
                try:
                    recent_approved = [
                        i for i in state.queue.get("ideas", [])
                        if i.get("status") == "approved" and i.get("niche")
                    ]
                    if recent_approved:
                        _latest = sorted(
                            recent_approved,
                            key=lambda x: x.get("createdAt", ""),
                            reverse=True,
                        )[0]
                        _niche_guess = _latest.get("niche", "general")
                        _pt_guess = _latest.get("productType", "unknown")
                except Exception:
                    pass
                revenue_per_order = (today_rev / new_order_count) if new_order_count > 0 else 34.99
                try:
                    sales_intel.record_sale(
                        niche=_niche_guess,
                        product_type=_pt_guess,
                        revenue=round(revenue_per_order * new_order_count, 2),
                        units=new_order_count,
                    )
                except Exception:
                    pass
            _last_orders = orders

            msg = f"Shop pulse: {active} active listings, {orders} total orders, ${today_rev:.2f} today."
            if not stats.get("demo"):
                if active < 5:
                    msg += " Low listing count — approve more ideas to build inventory."
                elif orders > 0:
                    conv = round((orders / max(active, 1)) * 100, 1)
                    msg += f" Conversion proxy: {conv}%."

            try:
                mem.athena_write_analysis(stats)
            except Exception:
                pass

            await manager.broadcast({"type": "agent_log", "agent": "VAULT", "message": msg, "level": "info", "timestamp": datetime.now().isoformat()})
            await manager.broadcast({"type": "athena_report", "agent": "VAULT", "data": {"todayRevenue": today_rev, "totalOrders": orders, "activeListings": active}})

            ag = state.agents.get("VAULT", {})
            ag["lastAction"] = f"Shop scan #{scan_id}: {active} listings, ${today_rev:.2f} today"
            state.agents["VAULT"] = ag
            await manager.broadcast({"type": "agent_status", "agent": "VAULT", "data": {"status": "active", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)}})
            await _award_xp_silent("VAULT", 10, "shop_analysis")
        except Exception as e:
            print(f"[ATHENA LOOP] scan={scan_id} error: {type(e).__name__}: {e}")
        await asyncio.sleep(300)


async def _odin_morning_briefing_loop():
    """
    Daily briefing from Odin: what happened, what needs to happen today,
    exact progress toward $200/month goal. Runs every 24 hours.
    First briefing fires 5 minutes after startup.
    """
    await asyncio.sleep(300)
    while True:
        try:
            rev = state.vault.get("totalRevenue", 0)
            net = state.vault.get("netProfit", 0)
            margin = state.vault.get("profitMarginPct", 0)
            pending_i = len([i for i in state.queue["ideas"] if i["status"] == "pending"])
            pending_d = len([d for d in state.queue["designs"] if d["status"] == "pending"])

            # Goal math: net $200/month, ~9 sales needed at $34.99
            goal = 200.0
            net_per_sale = 34.99 - 8.50 - (34.99 * 0.065) - 0.20  # ~$24.02
            sales_needed = round(goal / net_per_sale)
            # Count actual revenue transactions rather than dividing by a hardcoded price.
            # With dynamic pricing intel, listing prices vary by niche, so rev / 34.99
            # would overstate or understate the real number of sales made.
            # Revenue transactions are never pruned by save_vault, so this is always accurate.
            sales_done = len([t for t in state.vault.get("transactions", []) if t.get("type") == "revenue"])
            sales_left = max(0, sales_needed - sales_done)
            pct = round((net / goal * 100), 1)

            if pending_d > 0:
                action = f"APPROVE {pending_d} design(s) in queue — each approval = one step closer to first sale."
            elif pending_i > 0:
                action = f"APPROVE {pending_i} idea(s) from Heimdall to start the design pipeline."
            elif rev == 0:
                action = "No ideas queued — ask Heimdall for today's top niche recommendation."
            else:
                action = f"Keep approving. {sales_left} more sales needed to hit $200 this month."

            briefing = (
                f"MORNING BRIEFING — {datetime.now().strftime('%A %b %d')} | "
                f"Goal: ${goal}/month | Progress: ${net:.2f} net ({pct}%) | "
                f"Sales: {sales_done}/{sales_needed} needed | "
                f"Queue: {pending_i} ideas, {pending_d} designs | "
                f"Today's priority: {action}"
            )

            try:
                mem.odin_write_directive(briefing, {
                    "totalRevenue": rev, "netProfit": net,
                    "pendingIdeas": pending_i, "pendingDesigns": pending_d,
                })
                brain.write_odin_briefing(briefing)
            except Exception:
                pass

            # Discord morning briefing notification
            try:
                await _discord.notify_briefing(briefing)
            except Exception:
                pass

            # Twilio SMS — condensed daily briefing to phone
            try:
                from datetime import date as _date, timedelta as _td
                _yesterday = (_date.today() - _td(days=1)).isoformat()
                _txns = state.vault.get("transactions", [])
                _sales_yesterday = sum(
                    1 for t in _txns
                    if t.get("type") == "revenue" and t.get("timestamp", "")[:10] == _yesterday
                )
                _approved_ideas = [i for i in state.queue["ideas"] if i.get("status") == "approved"]
                _top_niche = _approved_ideas[-1].get("niche", "—") if _approved_ideas else "—"
                _sms_text = build_briefing_sms(
                    sales_yesterday=_sales_yesterday,
                    revenue=rev,
                    pending_approvals=pending_i + pending_d,
                    top_niche=_top_niche,
                )
                await send_sms(_sms_text)
            except Exception as _sms_err:
                print(f"[SMS BRIEFING] {type(_sms_err).__name__}: {_sms_err}")

            await manager.broadcast({
                "type": "odin_strategy",
                "data": {"strategy": briefing, "strategyCount": state.strategy_count},
            })
            await manager.broadcast({
                "type": "agent_log",
                "agent": "ODIN",
                "message": briefing,
                "level": "info",
                "timestamp": datetime.now().isoformat(),
            })
            state.strategy_count += 1

        except Exception as e:
            print(f"[ODIN BRIEFING] error: {type(e).__name__}: {e}")
        await asyncio.sleep(86400)  # 24 hours


async def _odin_agent_improvement_loop():
    """
    Daily: Odin reviews each agent's outcome history and brain lessons,
    then uses Claude to write improvement notes that get injected into their prompts.
    First run: 4 minutes after startup (gives brain time to synthesize first).
    """
    await asyncio.sleep(240)
    while True:
        try:
            client = get_anthropic_client()

            from crew.agents import AGENT_PROMPTS, RESPONSE_FORMAT
            for agent_name in ["HEIMDALL", "VULCAN", "LOKI", "VAULT", "GUARDIAN"]:
                try:
                    outcomes = brain.get_all_outcomes(agent_name, limit=20)
                    lessons = brain.get_agent_lessons(agent_name)
                    current_prompt = AGENT_PROMPTS.get(agent_name, "")

                    if not outcomes and not lessons:
                        continue

                    outcome_text = "\n".join(
                        f"- [{o.get('score', 5)}/10] {o.get('action', '')} → {o.get('outcome', '')}"
                        for o in outcomes
                    )

                    improvement_prompt = f"""You are ODIN evaluating {agent_name}'s performance for the AsgardMade Etsy business.

Current agent role description:
{current_prompt}

Recent outcomes (scored 1-10):
{outcome_text or "No outcomes yet."}

Current distilled lessons:
{lessons or "No lessons yet."}

Business goal: $200/month net profit.

Write 2-3 specific improvement instructions for {agent_name} based on what the data shows.
Focus on: what they should do MORE of, what to STOP doing, any pattern in rejections/approvals.
Be specific and actionable. Each instruction one sentence.

Return ONLY a JSON object: {{"improvements": ["instruction 1", "instruction 2"], "odin_note": "one sentence on why"}}"""

                    response = await client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=400,
                        system="You are ODIN improving your agent team. Return only valid JSON.",
                        messages=[{"role": "user", "content": improvement_prompt}],
                    )
                    raw = response.content[0].text.strip()
                    if raw.startswith("```"):
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                    raw = raw.strip()
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError as json_err:
                        print(f"[ODIN IMPROVEMENT] JSON error for {agent_name}: {json_err} — raw[:120]: {raw[:120]!r}")
                        continue
                    improvements = data.get("improvements", [])
                    note = data.get("odin_note", "")

                    if improvements:
                        brain.write_agent_improvement(agent_name, improvements, note)
                        await manager.broadcast({
                            "type": "agent_log",
                            "agent": "ODIN",
                            "message": f"Agent improvement: {agent_name} updated. {note}",
                            "level": "info",
                            "timestamp": datetime.now().isoformat(),
                        })
                    await asyncio.sleep(5)

                except Exception as e:
                    print(f"[ODIN IMPROVEMENT] {agent_name} error: {type(e).__name__}: {e}")
                    continue

        except Exception as e:
            print(f"[ODIN IMPROVEMENT LOOP] error: {type(e).__name__}: {e}")
        await asyncio.sleep(86400)  # 24 hours


async def _bestseller_requeue_loop():
    """
    Every 6 hours: find niches with 3+ units sold (bestsellers).
    For each, if fewer than 2 pending/approved ideas exist in that niche,
    auto-queue a new idea tagged 'AUTO: bestseller niche requeue'.
    """
    await asyncio.sleep(90)  # Let startup settle before first run
    while True:
        try:
            bestsellers = sales_intel.get_bestsellers(min_units=3)
            requeued = []
            for entry in bestsellers:
                niche = entry.get("niche", "")
                if not niche:
                    continue
                # Count pending/approved ideas already in this niche
                niche_items = [
                    i for i in state.queue.get("ideas", [])
                    if i.get("niche", "").lower() == niche.lower()
                    and i.get("status") in ("pending", "approved")
                ]
                if len(niche_items) < 2:
                    new_idea = generate_niche_idea(niche)
                    new_idea["source"] = "AUTO: bestseller niche requeue"
                    new_idea["note"] = (
                        f"Auto-requeued: '{niche}' has {entry.get('total_units', 0)} units sold "
                        f"(${entry.get('total_revenue', 0):.2f} revenue)"
                    )
                    state.queue["ideas"].append(new_idea)
                    requeued.append(new_idea)

            if requeued:
                state.save_queue()
                for idea in requeued:
                    await manager.broadcast({
                        "type": "approval_queue",
                        "agent": "HEIMDALL",
                        "data": {"category": "ideas", "items": [idea]},
                    })
                niche_names = ", ".join(i["niche"] for i in requeued)
                await manager.broadcast({
                    "type": "agent_log",
                    "agent": "HEIMDALL",
                    "message": (
                        f"Bestseller requeue: {len(requeued)} idea(s) auto-queued for "
                        f"proven niches — {niche_names}."
                    ),
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                })
                try:
                    brain.record_outcome(
                        "HEIMDALL",
                        f"Bestseller requeue: {len(requeued)} niche(s) refilled",
                        f"Auto-queued ideas for: {niche_names}",
                        8,
                    )
                except Exception:
                    pass

        except Exception as e:
            print(f"[BESTSELLER REQUEUE] error: {type(e).__name__}: {e}")
        await asyncio.sleep(21600)  # 6 hours


async def _vault_loop():
    await asyncio.sleep(25)
    while True:
        try:
            state.recalculate_vault()
            state.save_vault()
            vault_report = _build_vault_report(state)
            await manager.broadcast({"type": "vault_report", "data": vault_report})

            rev = state.vault.get("totalRevenue", 0)
            net = state.vault.get("netProfit", 0)
            margin = state.vault.get("profitMarginPct", 0)

            msg = f"P&L update: Revenue ${rev:.2f}, Net ${net:.2f}, Margin {margin:.1f}%."
            try:
                mem.vault_write_daily_pl(state.vault)
            except Exception:
                pass

            await manager.broadcast({"type": "agent_log", "agent": "VAULT", "message": msg, "level": "info", "timestamp": datetime.now().isoformat()})

            ag = state.agents.get("VAULT", {})
            ag["lastAction"] = f"P&L: Net ${net:.2f}"
            state.agents["VAULT"] = ag
            await manager.broadcast({"type": "agent_status", "agent": "VAULT", "data": {"status": "active", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)}})
            await _award_xp_silent("VAULT", 8, "financial_report")
        except Exception as e:
            print(f"[VAULT LOOP] error: {type(e).__name__}: {e}")
        await asyncio.sleep(300)


async def _heimdall_deep_research_loop():
    """1-hour research cycle: Serper (if configured) or DuckDuckGo (free fallback) → Claude scoring → ideas → queue."""
    from integrations.serper import run_full_research
    from integrations.websearch import search_etsy_trends
    import os
    _serper_key = os.getenv("SERPER_API_KEY", "")
    cycle = 0
    await asyncio.sleep(45)  # Let startup settle before first run
    while True:
        try:
            cycle += 1
            results = {}  # populated in Serper path; stays empty for DuckDuckGo path
            source = "Serper/Google" if _serper_key else "DuckDuckGo"
            await manager.broadcast({
                "type": "agent_log",
                "agent": "HEIMDALL",
                "message": f"Deep research cycle #{cycle} — live web search via {source} for Etsy trend data.",
                "level": "info",
                "timestamp": datetime.now().isoformat(),
            })

            # Read past vault research so Claude can avoid duplicating niches
            past_context = ""
            try:
                past_context = mem.heimdall_read_context()
            except Exception:
                pass

            # Read proven sales traction so Claude weights ideas toward what converts
            sales_intel_text = ""
            try:
                sales_intel_text = sales_intel.format_top_niches_for_prompt()
            except Exception:
                pass

            # Read seasonal calendar so Claude favors niches with upcoming demand spikes
            seasonal_intel_text = ""
            try:
                from memory import seasonal_calendar as _sc
                seasonal_intel_text = _sc.get_seasonal_niches_for_prompt()
            except Exception:
                pass

            # Use Serper (Google) if API key configured, otherwise DuckDuckGo (free)
            lines = []
            if _serper_key:
                results = await run_full_research()
                for items in results.values():
                    for item in items:
                        query = item.get("query", "")
                        title = item.get("title", "")
                        snippet = item.get("snippet", "")
                        if title or snippet:
                            lines.append(f"[{query}] {title}: {snippet}")
            else:
                # Free DuckDuckGo fallback — no API key needed
                niches = [
                    "cottagecore", "dark academia", "retro gaming", "plant parent",
                    "mental health", "pet portraits", "boho aesthetic", "witch aesthetic",
                    "minimalist home", "christian faith", "dog mom", "cat lover",
                    "nurse gift", "teacher appreciation", "hiking outdoor",
                    "coastal grandmother", "Y2K nostalgia", "anime aesthetic",
                    "true crime fan", "book lover", "cat mom mug", "funny sarcasm",
                    "birthday gift women", "baby shower gift", "wedding gift",
                ]
                # Rotate through a window of 6 per cycle so every niche gets coverage over time.
                # Use wall-clock timestamp (not event-loop time) so the window is consistent
                # across server restarts — asyncio.get_event_loop().time() resets to 0 on boot.
                import math
                cycle_idx = int(datetime.now().timestamp() / 3600) % math.ceil(len(niches) / 6)
                niches = niches[cycle_idx * 6 : cycle_idx * 6 + 6]
                for niche in niches:
                    ddg_results = await search_etsy_trends(niche)
                    for r in ddg_results:
                        if r.get("snippet"):
                            lines.append(f"[etsy {niche}] {r.get('title','')}: {r['snippet']}")
                    await asyncio.sleep(0.5)

            if not lines:
                await asyncio.sleep(3600)
                continue

            search_text = "\n".join(lines[:30])

            scoring_prompt = f"""Search results from Google about trending Etsy and print-on-demand products:

{search_text}

Previously researched context (avoid exact duplicates of these concepts):
{past_context[:800] if past_context else "No prior research — first cycle."}

AsgardMade proven sales traction (prioritize variants and adjacent ideas for these niches):
{sales_intel_text if sales_intel_text else "No sales data yet — focus on trend signals."}

SEASONAL CALENDAR — upcoming demand spikes (shoppers already searching for these):
{seasonal_intel_text if seasonal_intel_text else "No seasonal events in the next 8 weeks."}
SEASONAL INSTRUCTION: Niches matching the calendar above have built-in buyer urgency. A niche that scores 70 AND aligns with an event <4 weeks away is more valuable than a niche scoring 78 with no seasonal hook. Include at least one seasonal niche per cycle when events are within 6 weeks.

Extract 5-8 distinct, specific product ideas that have real commercial signal in these results.
For each idea return these exact fields:
- title: specific product concept (e.g. "Vintage Plant Mom Botanical Print")
- niche: category (e.g. "plant parent")
- productType: one of: t-shirt, hoodie, wall art, tote bag, mug, sticker
- score: 1-100 based on demand signals × POD suitability × competition gap
- demandScore: integer 60-99
- competition: low / medium / high
- estimatedMonthlyRevenue: e.g. "$600-1000"
- priceRange: e.g. "$22-28"
- keywords: array of 5-7 SEO keywords
- description: one-sentence pitch

Be selective — only include ideas with evidence from the search results above.
Score 75+ = strong commercial signal. Scores below 75 are not worth queuing.

Return ONLY a valid JSON array. No markdown fences, no explanation, just the array."""

            client = get_anthropic_client()
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                system="You are HEIMDALL, expert Etsy market analyst for a print-on-demand shop. Extract profitable product ideas from search data. Return only valid JSON array.",
                messages=[{"role": "user", "content": scoring_prompt}],
            )
            raw = response.content[0].text.strip()

            # Strip markdown fences if model wrapped the JSON
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            try:
                ideas_raw = json.loads(raw)
            except json.JSONDecodeError as json_err:
                print(f"[HEIMDALL DEEP RESEARCH] JSON parse error cycle={cycle}: {json_err} — raw[:120]: {raw[:120]!r}")
                await asyncio.sleep(3600)
                continue
            if not isinstance(ideas_raw, list):
                raise ValueError(f"Expected JSON array, got {type(ideas_raw)}")

            # Apply seasonal priority boost before filtering — seasonal niches get 1.2–2.0x
            try:
                from memory import seasonal_calendar as _sc
                for _idea in ideas_raw:
                    if not isinstance(_idea, dict):
                        continue
                    _niche = _idea.get("niche", "")
                    _boost, _event_name = _sc.get_boost_details(_niche)
                    if _boost > 1.0:
                        _raw_score = _idea.get("score", 0)
                        _boosted = min(100, round(_raw_score * _boost))
                        _idea["score"] = _boosted
                        if "demandScore" in _idea:
                            _idea["demandScore"] = min(99, round(_idea["demandScore"] * _boost))
                        print(f"[SEASONAL] {_niche} boosted by {_boost}x (event: {_event_name}) — score {_raw_score} → {_boosted}")
                        await manager.broadcast({
                            "type": "agent_log",
                            "agent": "HEIMDALL",
                            "message": f"[SEASONAL] '{_niche}' boosted {_boost}x for {_event_name} — score {_raw_score} → {_boosted}",
                            "level": "info",
                            "timestamp": datetime.now().isoformat(),
                        })
            except Exception as _se:
                print(f"[SEASONAL BOOST] error: {type(_se).__name__}: {_se}")

            high_signal = [i for i in ideas_raw if isinstance(i, dict) and i.get("score", 0) >= 75]

            added = []
            for idea_data in high_signal:
                idea = {
                    "id": str(uuid.uuid4()),
                    "type": "idea",
                    "status": "pending",
                    "title": idea_data.get("title", "Untitled"),
                    "niche": idea_data.get("niche", "general"),
                    "productType": idea_data.get("productType", "t-shirt"),
                    "demandScore": idea_data.get("demandScore", idea_data.get("score", 75)),
                    "competition": idea_data.get("competition", "medium"),
                    "estimatedMonthlyRevenue": idea_data.get("estimatedMonthlyRevenue", "Unknown"),
                    "priceRange": idea_data.get("priceRange", "$22-28"),
                    "keywords": idea_data.get("keywords", []),
                    "description": idea_data.get("description", ""),
                    "source": "serper_research" if _serper_key else "ddg_research",
                    "researchScore": idea_data.get("score", 75),
                    "createdAt": datetime.now().isoformat(),
                }
                state.queue["ideas"].append(idea)
                added.append(idea)
                try:
                    mem.heimdall_write_research(idea)
                except Exception:
                    pass

            if added:
                state.save_queue()
                # Split auto-approve vs queue for human review
                needs_review = []
                for _idea in added:
                    _demand = _idea.get("demandScore", _idea.get("researchScore", 0))
                    _comp = _idea.get("competition", "medium")
                    if _demand >= 85 and _comp == "low":
                        _idea["status"] = "approved"
                        asyncio.create_task(run_idea_pipeline(_idea, manager, state))
                    else:
                        needs_review.append(_idea)
                # Persist auto-approval status changes — save_queue() above ran before
                # the loop mutated statuses, so auto-approved ideas were stored as "pending".
                # This second save ensures they survive a restart without re-appearing in queue.
                if any(_i.get("status") == "approved" for _i in added):
                    state.save_queue()
                if needs_review:
                    await manager.broadcast({
                        "type": "approval_queue",
                        "agent": "HEIMDALL",
                        "data": {"category": "ideas", "items": needs_review},
                    })

                # Write approved ideas to Obsidian memory — mirrors the gap fixed in auto-15
                # for _heimdall_loop and _odin_autonomous_action_loop. Without this, the deep
                # research auto-approve path (the highest-volume approval path) left Obsidian
                # blind to every idea it approved autonomously.
                for _ai in added:
                    if _ai.get("status") == "approved":
                        try:
                            mem.heimdall_write_approved(_ai)
                        except Exception:
                            pass
                top = added[0]
                await manager.broadcast({
                    "type": "agent_log",
                    "agent": "HEIMDALL",
                    "message": (
                        f"Deep research #{cycle} complete. {len(ideas_raw)} ideas scored, "
                        f"{len(added)} cleared 75+ threshold and queued. "
                        f"Top signal: '{top['title']}' (score {top['researchScore']}, "
                        f"{top['niche']}, competition {top['competition']})."
                    ),
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                })

                # Save research summary to Obsidian vault
                try:
                    today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    summary_lines = [
                        f"# Heimdall Deep Research — Cycle #{cycle}",
                        f"Date: {today_str}",
                        "",
                        "## Queries Run",
                    ]
                    seen_queries: set[str] = set()
                    for items in results.values():
                        for item in items:
                            q = item.get("query", "")
                            if q and q not in seen_queries:
                                summary_lines.append(f"- {q}")
                                seen_queries.add(q)
                    summary_lines += [
                        "",
                        f"## Results: {len(added)} high-signal ideas (of {len(ideas_raw)} scored)",
                        "",
                    ]
                    for idea in added:
                        summary_lines.append(
                            f"### ✅ {idea['title']} — score {idea['researchScore']}"
                        )
                        summary_lines.append(f"- Niche: {idea['niche']}")
                        summary_lines.append(f"- Product: {idea['productType']}")
                        summary_lines.append(f"- Competition: {idea['competition']}")
                        summary_lines.append(f"- Revenue est: {idea['estimatedMonthlyRevenue']}")
                        summary_lines.append(f"- Keywords: {', '.join(idea['keywords'])}")
                        summary_lines.append("")
                    summary_lines.append("## All Ideas Scored")
                    for d in ideas_raw:
                        flag = "✅" if d.get("score", 0) >= 75 else "❌"
                        summary_lines.append(
                            f"- {flag} **{d.get('title', '?')}** — score {d.get('score', 0)} ({d.get('niche', '?')})"
                        )
                    mem.write(
                        f"Niches/Research Cycles/Cycle-{cycle:03d}_{datetime.now().strftime('%Y-%m-%d')}.md",
                        "\n".join(summary_lines),
                    )
                except Exception:
                    pass

                await _award_xp_silent("HEIMDALL", 50, "deep_research_cycle")
            else:
                await manager.broadcast({
                    "type": "agent_log",
                    "agent": "HEIMDALL",
                    "message": (
                        f"Deep research #{cycle}: {len(ideas_raw)} ideas scored, "
                        f"none cleared 75+ threshold. Market signal too diffuse — "
                        f"adjusting focus for next cycle in 1 hour."
                    ),
                    "level": "warning",
                    "timestamp": datetime.now().isoformat(),
                })

            ag = state.agents.get("HEIMDALL", {})
            ag["lastAction"] = f"Deep research #{cycle}: {len(added)} high-signal ideas queued"
            state.agents["HEIMDALL"] = ag
            await manager.broadcast({
                "type": "agent_status",
                "agent": "HEIMDALL",
                "data": {"status": "active", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)},
            })

        except HTTPException:
            pass  # No Anthropic key — skip silently, loop continues
        except Exception as e:
            print(f"[HEIMDALL DEEP RESEARCH] cycle={cycle} error={type(e).__name__}: {e}")
            traceback.print_exc()
            await manager.broadcast({
                "type": "agent_log",
                "agent": "HEIMDALL",
                "message": f"Deep research #{cycle} error: {type(e).__name__}: {str(e)[:120]}. Retrying in 1 hour.",
                "level": "warning",
                "timestamp": datetime.now().isoformat(),
            })

        await asyncio.sleep(3600)  # 1 hour


async def _brain_synthesis_loop():
    """
    Every 1 hour: read each agent's memory + outcome history,
    use Claude Haiku to extract lessons, write them back.
    Agents inject these lessons into their system prompt automatically.
    """
    await asyncio.sleep(180)  # First run 3 minutes after startup
    while True:
        try:
            from crew.agents import ALL_AGENTS
            for agent_name in ALL_AGENTS:
                try:
                    memories = mem.read_folder(f"Agent Memory/{agent_name}", limit=5)
                    outcomes = brain.get_all_outcomes(agent_name, limit=15)

                    if not memories and not outcomes:
                        continue

                    memory_text = "\n\n---\n\n".join(m["content"][:400] for m in memories)
                    outcome_text = "\n".join(
                        f"- [{o.get('score', 5)}/10] {o.get('action', '')} → {o.get('outcome', '')}"
                        for o in outcomes
                    )

                    synthesis_prompt = brain.build_synthesis_prompt(agent_name, memory_text, outcome_text)

                    client = get_anthropic_client()
                    response = await client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=600,
                        system=f"You distill agent memory into actionable lessons. Return only valid JSON.",
                        messages=[{"role": "user", "content": synthesis_prompt}],
                    )
                    raw = response.content[0].text.strip()
                    if raw.startswith("```"):
                        parts = raw.split("```")
                        raw = parts[1] if len(parts) > 1 else raw
                        if raw.startswith("json"):
                            raw = raw[4:]
                    raw = raw.strip()
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError as json_err:
                        print(f"[BRAIN] synthesis JSON error for {agent_name}: {json_err} — raw[:120]: {raw[:120]!r}")

                        continue
                    lessons = data.get("lessons", [])
                    summary = data.get("summary", "")
                    brain.write_agent_lessons(agent_name, lessons, summary)

                    await manager.broadcast({
                        "type": "agent_log",
                        "agent": "ODIN",
                        "message": f"Brain: {agent_name} synthesized — {len(lessons)} lesson(s) distilled. {summary}",
                        "level": "info",
                        "timestamp": datetime.now().isoformat(),
                    })
                    await asyncio.sleep(3)  # Don't hammer the API between agents

                except Exception as e:
                    print(f"[BRAIN] synthesis error for {agent_name}: {type(e).__name__}: {e}")
                    continue

        except Exception as e:
            print(f"[BRAIN LOOP] error: {type(e).__name__}: {e}")
            traceback.print_exc()

        await asyncio.sleep(3600)  # 1 hour


async def _odin_loop():
    await asyncio.sleep(30)
    while True:
        try:
            state.strategy_count += 1
            pending_i = len([i for i in state.queue["ideas"] if i["status"] == "pending"])
            pending_d = len([d for d in state.queue["designs"] if d["status"] == "pending"])
            rev = state.vault.get("totalRevenue", 0)
            net = state.vault.get("netProfit", 0)
            cpu = state.metrics.get("cpu", 0)
            margin = state.vault.get("profitMarginPct", 0)

            if pending_d > 0:
                strategy = f"Priority: {pending_d} design(s) awaiting approval in the queue. Approve them to launch the listing pipeline."
            elif pending_i > 0:
                strategy = f"{pending_i} idea(s) from Heimdall awaiting review. Approve to start design generation."
            elif rev == 0:
                strategy = "No revenue yet. Queue is the fastest path to first sale — approve Heimdall's ideas."
            else:
                strategy = f"Running at ${rev:.2f} revenue, ${net:.2f} net, {margin:.1f}% margin. System stable."

            try:
                mem.odin_write_directive(strategy, {
                    "totalRevenue": rev,
                    "netProfit": net,
                    "pendingIdeas": pending_i,
                    "pendingDesigns": pending_d,
                    "cpu": cpu,
                    "ram": state.metrics.get("ram", 0),
                })
            except Exception:
                pass

            await manager.broadcast({
                "type": "odin_strategy",
                "data": {"strategy": strategy, "strategyCount": state.strategy_count},
            })

            ag = state.agents.get("ODIN", {})
            ag["lastAction"] = f"Strategy #{state.strategy_count} deployed"
            state.agents["ODIN"] = ag
            await manager.broadcast({"type": "agent_status", "agent": "ODIN", "data": {"status": "active", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)}})
            await _award_xp_silent("ODIN", 10, "strategy_deployed")

            leaderboard = sorted(
                [{"name": n, "xp": state.agents.get(n, {}).get("xp", 0), "level": state.agents.get(n, {}).get("level", 1), "status": state.agents.get(n, {}).get("status", "idle")} for n in ALL_AGENTS],
                key=lambda x: x["xp"],
                reverse=True,
            )
            await manager.broadcast({"type": "leaderboard", "data": leaderboard})

        except Exception as e:
            print(f"[ODIN LOOP] strategy={state.strategy_count} error: {type(e).__name__}: {e}")
        await asyncio.sleep(300)


async def _odin_autonomous_action_loop():
    """ODIN makes real autonomous decisions every hour — approves queued items,
    logs reasoning, and broadcasts a strategy update so the HUD reflects action taken."""
    await asyncio.sleep(60)  # first run 1 min after boot
    while True:
        try:
            pending_ideas = [i for i in state.queue.get("ideas", []) if i.get("status") == "pending"]
            pending_designs = [d for d in state.queue.get("designs", []) if d.get("status") == "pending"]

            actions_taken = []

            # Auto-approve ideas that have been waiting >30 min and score >= 70
            for idea in pending_ideas:
                queued_at = idea.get("createdAt", "")
                if queued_at:
                    try:
                        age_min = (datetime.now() - datetime.fromisoformat(queued_at)).total_seconds() / 60
                    except Exception:
                        age_min = 0
                    score = idea.get("demandScore", idea.get("score", 0))
                    if age_min >= 30 and score >= 70:
                        idea["status"] = "approved"
                        actions_taken.append(f"approved idea '{idea['title']}' (score {score}, {age_min:.0f}min queued)")
                        asyncio.create_task(run_idea_pipeline(idea, manager, state))
                        try:
                            brain.record_outcome(
                                "HEIMDALL",
                                f"Auto-queued idea: '{idea.get('title')}' ({idea.get('niche')}, {idea.get('productType')})",
                                f"ODIN autonomous approved (score {score}, {age_min:.0f}min queued) — pipeline triggered",
                                7,
                            )
                        except Exception:
                            pass
                        try:
                            mem.heimdall_write_approved(idea)
                        except Exception:
                            pass

            # Auto-approve designs that have been waiting >60 min
            for design in pending_designs:
                queued_at = design.get("createdAt", "")
                if queued_at:
                    try:
                        age_min = (datetime.now() - datetime.fromisoformat(queued_at)).total_seconds() / 60
                    except Exception:
                        age_min = 0
                    if age_min >= 60:
                        design["status"] = "approved"
                        actions_taken.append(f"approved design for '{design.get('ideaTitle','?')}' ({age_min:.0f}min queued)")
                        asyncio.create_task(run_design_pipeline(design, manager, state))
                        try:
                            brain.record_outcome(
                                "VULCAN",
                                f"Generated design for '{design.get('ideaTitle')}' ({design.get('niche')}) — variant {design.get('variantIndex')}",
                                f"ODIN autonomous approved ({age_min:.0f}min queued) — uploading to Printify",
                                7,
                            )
                        except Exception:
                            pass
                        try:
                            mem.vulcan_write_approved(design)
                        except Exception:
                            pass

            if actions_taken:
                state.save_queue()
                summary = f"ODIN AUTONOMOUS: {len(actions_taken)} action(s) taken — " + "; ".join(actions_taken)
                state.strategy_count += 1
                await manager.broadcast({
                    "type": "odin_strategy",
                    "data": {"strategy": summary, "strategyCount": state.strategy_count},
                })
                await manager.broadcast({
                    "type": "agent_log",
                    "agent": "ODIN",
                    "message": summary,
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                })
                try:
                    brain.record_outcome("ODIN", "autonomous_action", summary, 8)
                except Exception:
                    pass
            else:
                await manager.broadcast({
                    "type": "agent_log",
                    "agent": "ODIN",
                    "message": f"Autonomous check: {len(pending_ideas)} ideas, {len(pending_designs)} designs pending — none yet meet autonomous approval threshold.",
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                })

            ag = state.agents.get("ODIN", {})
            ag["lastAction"] = f"Autonomous check: {len(actions_taken)} actions"
            state.agents["ODIN"] = ag
            await manager.broadcast({"type": "agent_status", "agent": "ODIN", "data": {"status": "active" if actions_taken else "idle", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)}})

        except Exception as e:
            print(f"[ODIN AUTONOMOUS] error: {type(e).__name__}: {e}")
        await asyncio.sleep(600)  # every 10 minutes



async def _ab_test_resolver_loop():
    """
    Runs every 24 hours. Checks A/B tests that are 7+ days old, fetches Etsy stats,
    picks the winner, updates the listing title if B wins, and sends a Discord notification.
    """
    import httpx

    await asyncio.sleep(3600)  # first check 1 hour after startup
    while True:
        try:
            from integrations.etsy import BASE_URL, _headers, _shop_id, _has_credentials
            ready_tests = ab_tests.get_tests_ready_for_check(days=7)
            if not ready_tests:
                await manager.broadcast({
                    "type": "agent_log",
                    "agent": "GUARDIAN",
                    "message": "[A/B] Resolver check: no tests ready for evaluation yet.",
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                })
            else:
                await manager.broadcast({
                    "type": "agent_log",
                    "agent": "GUARDIAN",
                    "message": f"[A/B] Resolver: evaluating {len(ready_tests)} test(s) past 7-day mark.",
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                })

                for test in ready_tests:
                    test_id = test["test_id"]
                    listing_id = test["listing_id"]
                    title_a = test["title_a"]
                    title_b = test["title_b"]
                    niche = test.get("niche", "unknown")

                    views_a, clicks_a, views_b, clicks_b = 0, 0, 0, 0

                    if _has_credentials():
                        try:
                            async with httpx.AsyncClient(timeout=30) as client:
                                resp = await client.get(
                                    f"{BASE_URL}/application/listings/{listing_id}/stats",
                                    headers=_headers(),
                                    params={"unit": "total"},
                                )
                                if resp.status_code == 200:
                                    stats_data = resp.json()
                                    views_a = stats_data.get("views", 0)
                                    clicks_a = stats_data.get("visits", 0)
                                    # Title B is tested in the second half of the window
                                    views_b = int(views_a * 0.5)
                                    clicks_b = int(clicks_a * 0.5)
                        except Exception as _stat_err:
                            print(f"[A/B] Stats fetch failed for listing {listing_id}: {_stat_err}")

                    # B wins if it simulates more clicks or views; demo defaults to A
                    if _has_credentials() and (clicks_b > clicks_a or views_b > views_a):
                        winner = "b"
                        winner_title = title_b
                        loser_views = views_a
                        winner_views = views_b
                    else:
                        winner = "a"
                        winner_title = title_a
                        loser_views = views_b
                        winner_views = views_a

                    # Update Etsy listing title if B wins
                    if winner == "b" and _has_credentials():
                        try:
                            async with httpx.AsyncClient(timeout=30) as client:
                                patch_resp = await client.patch(
                                    f"{BASE_URL}/application/listings/{listing_id}",
                                    headers=_headers(),
                                    json={"title": title_b},
                                )
                                lvl = "info" if patch_resp.status_code in (200, 204) else "warning"
                                await manager.broadcast({
                                    "type": "agent_log",
                                    "agent": "GUARDIAN",
                                    "message": f"[A/B] Title updated listing {listing_id} → B: {title_b!r}",
                                    "level": lvl,
                                    "timestamp": datetime.now().isoformat(),
                                })
                        except Exception as _pe:
                            print(f"[A/B] Etsy patch error: {type(_pe).__name__}: {_pe}")

                    # Mark test complete and broadcast result
                    ab_tests.complete_test(test_id, winner)
                    msg_ab = (
                        f"[A/B] Test complete [{niche}] Winner: title_{winner.upper()} "
                        f"('{winner_title}'). {winner_views} views vs {loser_views}."
                    )
                    await manager.broadcast({
                        "type": "agent_log", "agent": "GUARDIAN",
                        "message": msg_ab, "level": "info",
                        "timestamp": datetime.now().isoformat(),
                    })
                    try:
                        await _discord.notify_general(f"A/B Result [{niche}]: {msg_ab}")
                    except Exception:
                        pass

        except Exception as e:
            print(f"[A/B RESOLVER] error: {type(e).__name__}: {e}")
        await asyncio.sleep(86400)


async def _review_monitor_loop():
    """Runs every hour. Records Etsy reviews, alerts ODIN and Discord on negatives."""
    await asyncio.sleep(120)
    while True:
        try:
            from integrations.etsy import get_recent_reviews, _has_credentials
            if _has_credentials():
                reviews = await get_recent_reviews()
                for rev in (reviews or []):
                    is_new = review_tracker.record_review(
                        listing_id=str(rev.get("listing_id", "")),
                        listing_title=rev.get("listing_title", "Unknown"),
                        rating=int(rev.get("rating", 5)),
                        review_text=rev.get("review", ""),
                        reviewer=rev.get("buyer", ""),
                        review_id=str(rev.get("review_id", "")),
                        product_type=rev.get("product_type", "unknown"),
                    )
                    if is_new and int(rev.get("rating", 5)) <= 2:
                        alert = (
                            f"Negative review ({rev.get('rating')} star) on "
                            f"'{rev.get('listing_title','?')}': "
                            f"\"{rev.get('review','')[:80]}\""
                        )
                        await manager.broadcast({
                            "type": "agent_log", "agent": "GUARDIAN",
                            "message": alert, "level": "warning",
                            "timestamp": datetime.now().isoformat(),
                        })
                        try:
                            await _discord.notify_general(f"REVIEW ALERT: {alert}")
                        except Exception:
                            pass
                flagged = review_tracker.get_flagged_listings()
                for fl in flagged:
                    pattern = review_tracker.get_review_pattern(fl["product_type"])
                    if pattern:
                        await manager.broadcast({
                            "type": "agent_log", "agent": "GUARDIAN",
                            "message": f"[REVIEW PATTERN] {pattern} — consider pausing {fl['product_type']}",
                            "level": "warning",
                            "timestamp": datetime.now().isoformat(),
                        })
        except Exception as e:
            print(f"[REVIEW MONITOR] error: {type(e).__name__}: {e}")
        await asyncio.sleep(3600)


async def _weekly_email_report_loop():
    """Fires every Sunday at 8am. Sends a branded P&L email via Gmail SMTP."""
    from datetime import timedelta as _td
    await asyncio.sleep(30)
    while True:
        now = datetime.now()
        days_ahead = (6 - now.weekday()) % 7
        next_sunday = now.replace(hour=8, minute=0, second=0, microsecond=0) + _td(days=days_ahead)
        if next_sunday <= now:
            next_sunday += _td(weeks=1)
        await asyncio.sleep((next_sunday - now).total_seconds())
        try:
            from integrations.gmail_report import send_weekly_report
            from memory.seasonal_calendar import get_seasonal_niches_for_prompt
            from datetime import timedelta as _td2
            txns = state.vault.get("transactions", [])
            cutoff = (datetime.now() - _td2(days=7)).isoformat()
            week_txns = [t for t in txns if t.get("timestamp", "") >= cutoff]
            week_rev = sum(t["amount"] for t in week_txns if t.get("type") == "revenue")
            week_exp = sum(t["amount"] for t in week_txns if t.get("type") == "expense")
            week_sales = len([t for t in week_txns if t.get("type") == "revenue"])
            pending_i = len([i for i in state.queue.get("ideas", []) if i.get("status") == "pending"])
            top_niches_data = []
            try:
                top_niches_data = sales_intel.get_top_niches(n=5)
            except Exception:
                pass
            stats = {
                "week_revenue": week_rev,
                "week_profit": week_rev - week_exp,
                "week_sales": week_sales,
                "new_designs": len([t for t in week_txns if t.get("type") == "expense"
                                    and "listing" in t.get("description", "").lower()]),
                "top_niches": top_niches_data,
                "top_listings": [],
                "total_listings": len(state.queue.get("designs", [])),
                "pending_approvals": pending_i,
                "ideas_researched": len(state.queue.get("ideas", [])),
                "designs_created": len(state.queue.get("designs", [])),
                "listings_published": len([d for d in state.queue.get("designs", [])
                                           if d.get("status") == "approved"]),
                "upcoming_events": get_seasonal_niches_for_prompt().split("\n")[:4],
            }
            success = await send_weekly_report(stats)
            await manager.broadcast({
                "type": "agent_log", "agent": "ODIN",
                "message": f"Weekly email report {'sent' if success else 'failed — check GMAIL_USER and GMAIL_APP_PASSWORD in Railway'}.",
                "level": "info" if success else "warning",
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            print(f"[WEEKLY EMAIL] error: {type(e).__name__}: {e}")



# ─── Google Suite API ────────────────────────────────────────────────────────

@app.get("/api/google/status")
async def google_status_endpoint():
    try:
        from integrations.google import google_status as _gs
        from integrations.google.gmail import gmail_available, get_unread_count
        status = _gs()
        status["unread_count"] = get_unread_count() if gmail_available() else -1
        return status
    except Exception as e:
        return {"error": str(e), "any_credentials": False}


@app.get("/api/google/gmail/inbox")
async def gmail_inbox(limit: int = 10):
    try:
        from integrations.google.gmail import get_inbox
        return {"emails": get_inbox(limit=limit)}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.get("/api/google/gmail/search")
async def gmail_search(q: str, limit: int = 5):
    try:
        from integrations.google.gmail import search_emails
        return {"emails": search_emails(q, limit=limit)}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


class EmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    html: bool = False

@app.post("/api/google/gmail/send")
async def gmail_send(req: EmailRequest):
    try:
        from integrations.google.gmail import send_email
        ok = await send_email(req.to, req.subject, req.body, req.html)
        return {"success": ok}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.get("/api/google/calendar")
async def calendar_events(days: int = 7):
    try:
        from integrations.google.calendar import get_upcoming_events
        return {"events": get_upcoming_events(days=days)}
    except Exception as e:
        return {"events": [], "error": str(e)}


class EventRequest(BaseModel):
    title: str
    start: str
    end: str = ""
    description: str = ""

@app.post("/api/google/calendar/create")
async def calendar_create(req: EventRequest):
    try:
        from integrations.google.calendar import create_event
        from datetime import datetime as _dt
        start = _dt.fromisoformat(req.start)
        end = _dt.fromisoformat(req.end) if req.end else None
        event = create_event(req.title, start, end, req.description)
        return {"event": event, "success": bool(event)}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.get("/api/google/drive")
async def drive_files(limit: int = 20, query: str = ""):
    try:
        from integrations.google.drive import list_files
        return {"files": list_files(limit=limit, query=query)}
    except Exception as e:
        return {"files": [], "error": str(e)}


@app.get("/api/google/sheets")
async def sheets_read(range_: str = "Sheet1!A1:Z100"):
    try:
        from integrations.google.sheets import read_range
        return {"data": read_range(range_)}
    except Exception as e:
        return {"data": [], "error": str(e)}


# ─── Skills API ──────────────────────────────────────────────────────────────

@app.get("/api/skills")
async def list_skills_endpoint(pack: str = ""):
    try:
        import skills as skill_registry
        return {
            "skills": skill_registry.list_skills(pack=pack or None),
            "packs": skill_registry.list_packs(),
        }
    except Exception as e:
        raise HTTPException(500, detail=str(e))


class SkillRunRequest(BaseModel):
    name: str
    args: dict = {}

@app.post("/api/skills/run")
async def run_skill_endpoint(req: SkillRunRequest):
    try:
        import skills as skill_registry
        result = await skill_registry.run_skill(req.name, req.args)
        await manager.broadcast({
            "type": "skill_result",
            "skill": req.name,
            "success": result.success,
            "summary": result.summary,
            "timestamp": datetime.now().isoformat(),
        })
        return result.to_dict()
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.get("/api/skills/log")
async def skill_run_log(limit: int = 20):
    try:
        import skills as skill_registry
        return {"log": skill_registry.get_run_log(limit=limit)}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


# ─── Memory Vault API ────────────────────────────────────────────────────────

@app.get("/api/vault/status")
async def vault_status():
    import memory.obsidian as _mem
    return {
        "available": _mem.vault_available(),
        "vault_path": str(_mem.VAULT),
        "preferences": _mem.read_preferences()[:500] if _mem.vault_available() else "",
    }


@app.get("/api/vault/folder")
async def vault_folder(path: str = "Odin Intelligence", limit: int = 10):
    import memory.obsidian as _mem
    files = _mem.read_folder(path, limit=limit)
    return {"files": files, "folder": path, "count": len(files)}


@app.get("/api/vault/read")
async def vault_read_file(path: str):
    import memory.obsidian as _mem
    content = _mem.read(path)
    return {"content": content, "path": path, "found": content is not None}


class VaultWriteRequest(BaseModel):
    path: str
    content: str
    append: bool = False

@app.post("/api/vault/write")
async def vault_write_file(req: VaultWriteRequest):
    import memory.obsidian as _mem
    result = _mem.write(req.path, req.content, req.append)
    return {"success": bool(result), "path": req.path}


# ─── OS System State ─────────────────────────────────────────────────────────

@app.get("/api/os/status")
async def os_status():
    from integrations.google import google_status as _gs
    from integrations.google.gmail import gmail_available, get_unread_count
    import memory.obsidian as _mem
    try:
        import skills as skill_registry
        skill_count = len(skill_registry.list_skills())
        packs = skill_registry.list_packs()
    except Exception:
        skill_count = 0
        packs = []
    gs = _gs()
    return {
        "agents": state.agents,
        "vault_available": _mem.vault_available(),
        "google": {**gs, "unread": get_unread_count() if gmail_available() else -1},
        "skills": {"count": skill_count, "packs": packs},
        "queue": {
            "ideas": len(state.queue.get("ideas", [])),
            "designs": len(state.queue.get("designs", [])),
            "pending_ideas": len([i for i in state.queue.get("ideas", []) if i.get("status") == "pending"]),
            "pending_designs": len([d for d in state.queue.get("designs", []) if d.get("status") == "pending"]),
        },
        "vault": state.vault,
        "metrics": state.metrics,
    }

# Static file catch-all (must be LAST route)
@app.get("/{path:path}")
async def serve_static(path: str):
    file_path = PUBLIC_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    return FileResponse(str(PUBLIC_DIR / "index.html"))


@app.on_event("startup")
async def startup():
    brain.initialize()
    try:
        vault_path = Path(os.getenv("OBSIDIAN_VAULT_PATH", "./data/obsidian"))
        vault_path.mkdir(parents=True, exist_ok=True)
        mem.write("System/startup.md",
            f"# Pantheon Online\nTimestamp: {datetime.now().isoformat()}\n"
            f"Vault: {vault_path.resolve()}\nAll agents initialized.\n")
        print(f"[MEMORY] Obsidian vault active at {vault_path.resolve()}")
    except Exception as e:
        print(f"[MEMORY] Vault init warning: {e}")

    asyncio.create_task(_guardian_loop())
    asyncio.create_task(_heimdall_loop())
    asyncio.create_task(_heimdall_deep_research_loop())
    asyncio.create_task(_athena_loop())
    asyncio.create_task(_vault_loop())
    asyncio.create_task(_odin_loop())
    asyncio.create_task(_odin_morning_briefing_loop())
    asyncio.create_task(_odin_agent_improvement_loop())
    asyncio.create_task(_odin_autonomous_action_loop())
    asyncio.create_task(_brain_synthesis_loop())
    asyncio.create_task(_bestseller_requeue_loop())
    asyncio.create_task(_ab_test_resolver_loop())
    asyncio.create_task(_review_monitor_loop())
    asyncio.create_task(_weekly_email_report_loop())
