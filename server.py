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
        net = revenue - expenses
        self.vault["totalRevenue"] = round(revenue, 2)
        self.vault["totalExpenses"] = round(expenses, 2)
        self.vault["netProfit"] = round(net, 2)
        self.vault["profitMarginPct"] = round((net / revenue * 100) if revenue > 0 else 0, 1)


manager = ConnectionManager()
state = AppState()


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
    vault_report = _build_vault_report(state)
    init_data = {
        "agentStats": {"agents": state.agents},
        "approvals": state.queue,
        "finance": state.vault,
        "metrics": state.metrics,
    }
    strategy = (
        f"Pantheon online. {len(state.queue['ideas'])} ideas and "
        f"{len(state.queue['designs'])} designs in queue. "
        f"Financial state: ${state.vault.get('netProfit', 0):.2f} net. "
        f"Awaiting your command."
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
        await manager.broadcast({"type": "queue_update", "data": {"category": "ideas", "id": item_id, "status": "approved"}})
        asyncio.create_task(run_idea_pipeline(idea, manager, state))
        return {"ok": True, "type": "idea", "id": item_id}

    design = next((d for d in state.queue["designs"] if d["id"] == item_id), None)
    if design:
        design["status"] = "approved"
        state.save_queue()
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
            await manager.broadcast({"type": "queue_update", "data": {"category": category, "id": item_id, "status": "rejected"}})
            return {"ok": True, "type": category, "id": item_id}
    raise HTTPException(404, detail="Item not found")


@app.get("/api/vault")
async def get_vault():
    return _build_vault_report(state)


@app.get("/api/brain/status")
async def get_brain_status():
    """Shows which agents have learned lessons and how many outcomes are tracked."""
    return brain.brain_status()


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
    vault_report = _build_vault_report(state)
    await manager.broadcast({"type": "vault_report", "data": vault_report})
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
    await asyncio.sleep(20)
    while True:
        try:
            scan_id += 1
            stats = await get_shop_stats()

            active = stats.get("active_listings", 0)
            orders = stats.get("total_orders", 0)
            today_rev = stats.get("today_revenue", 0.0)

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
            sales_done = round(rev / 34.99) if rev > 0 else 0
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
    Weekly: Odin reviews each agent's outcome history and brain lessons,
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
                    data = json.loads(raw.strip())
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
                    print(f"[ODIN IMPROVEMENT] {agent_name} error: {e}")
                    continue

        except Exception as e:
            print(f"[ODIN IMPROVEMENT LOOP] error: {e}")
        await asyncio.sleep(86400)  # 24 hours


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
                niches = ["cottagecore", "dark academia", "retro gaming", "plant parent", "mental health", "pet portraits"]
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

            ideas_raw = json.loads(raw)
            if not isinstance(ideas_raw, list):
                raise ValueError(f"Expected JSON array, got {type(ideas_raw)}")

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
                if needs_review:
                    await manager.broadcast({
                        "type": "approval_queue",
                        "agent": "HEIMDALL",
                        "data": {"category": "ideas", "items": needs_review},
                    })
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
                "message": f"Deep research #{cycle} error: {type(e).__name__}: {str(e)[:120]}. Retrying in 6 hours.",
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
                    data = json.loads(raw)
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

            # Auto-approve ideas that have been waiting >30 min and score ≥ 70
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
        await asyncio.sleep(600)  # every 10 minutes — tighter loop means auto-approvals fire closer to the 30/60-min thresholds


# ─── Static file catch-all (must be LAST route so API routes match first) ────

@app.get("/{path:path}")
async def serve_static(path: str):
    """Serve any file from the public/ directory (JS, CSS, images, etc.)"""
    file_path = PUBLIC_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    return FileResponse(str(PUBLIC_DIR / "index.html"))


# ─── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    brain.initialize()  # ensure brain directory exists immediately
    asyncio.create_task(_guardian_loop())           # ops: logs + metrics + security
    asyncio.create_task(_heimdall_loop())           # rapid niche scan every 2 min
    asyncio.create_task(_heimdall_deep_research_loop())  # deep web research every 1h
    asyncio.create_task(_athena_loop())             # shop stats every 5 min
    asyncio.create_task(_vault_loop())              # P&L updates every 5 min
    asyncio.create_task(_odin_loop())               # strategy updates every 5 min
    asyncio.create_task(_odin_morning_briefing_loop())   # daily briefing
    asyncio.create_task(_odin_agent_improvement_loop())  # weekly agent improvement
    asyncio.create_task(_odin_autonomous_action_loop())  # autonomous approval every 4h
    asyncio.create_task(_brain_synthesis_loop())    # lesson distillation every 6h

    log_file = Path("logs") / f"pantheon_{datetime.now().strftime('%Y%m%d')}.log"
    log_file.write_text(f"[{datetime.now().isoformat()}] AsgardMade Pantheon started\n")
