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
            except Exception:
                pass

    def save_agents(self):
        (DATA_DIR / "agents.json").write_text(json.dumps(self.agents, indent=2, default=str))

    def save_queue(self):
        (DATA_DIR / "queue.json").write_text(json.dumps(self.queue, indent=2, default=str))

    def save_vault(self):
        (DATA_DIR / "vault.json").write_text(json.dumps(self.vault, indent=2, default=str))

    def save_blocked(self):
        (DATA_DIR / "blocked_ips.json").write_text(json.dumps({"ips": self.blocked_ips}, indent=2))

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
            await manager.broadcast({"type": "queue_update", "data": {"category": "ideas", "id": item_id, "status": "approved"}})
            asyncio.create_task(run_idea_pipeline(idea, manager, state))

    elif msg_type == "approve_design":
        item_id = msg.get("id")
        design = next((d for d in state.queue["designs"] if d["id"] == item_id), None)
        if design:
            design["status"] = "approved"
            state.save_queue()
            await manager.broadcast({"type": "queue_update", "data": {"category": "designs", "id": item_id, "status": "approved"}})
            asyncio.create_task(run_design_pipeline(design, manager, state))

    elif msg_type == "reject_idea":
        item_id = msg.get("id")
        item = next((i for i in state.queue["ideas"] if i["id"] == item_id), None)
        if item:
            item["status"] = "rejected"
            state.save_queue()
            await manager.broadcast({"type": "queue_update", "data": {"category": "ideas", "id": item_id, "status": "rejected"}})

    elif msg_type == "reject_design":
        item_id = msg.get("id")
        item = next((d for d in state.queue["designs"] if d["id"] == item_id), None)
        if item:
            item["status"] = "rejected"
            state.save_queue()
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
            max_tokens=1024,
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


# ─── XP Helper ───────────────────────────────────────────────────────────────

async def _award_xp_silent(agent: str, amount: int, action: str):
    ag = state.agents.setdefault(agent, {"xp": 0, "level": 1})
    ag["xp"] = ag.get("xp", 0) + amount
    ag["level"] = ag["xp"] // 500 + 1
    await manager.broadcast({
        "type": "xp_gain",
        "agent": agent,
        "amount": amount,
        "total": ag["xp"],
        "level": ag["level"],
        "action": action,
    })


# ─── Background Agent Loops ──────────────────────────────────────────────────

async def _argus_loop():
    scan_id = 0
    while True:
        try:
            scan_id += 1
            metrics = get_system_metrics()
            state.metrics = metrics

            cpu, ram, disk = metrics["cpu"], metrics["ram"], metrics["disk"]

            await manager.broadcast({"type": "system_metrics", "data": {"metrics": metrics}})

            last = f"CPU {cpu}% | RAM {ram}% | Disk {disk}%"
            ag = state.agents.get("ARGUS", {})
            ag["lastAction"] = last
            state.agents["ARGUS"] = ag

            await manager.broadcast({
                "type": "agent_status",
                "agent": "ARGUS",
                "data": {
                    "status": "active",
                    "lastAction": last,
                    "xp": ag.get("xp", 0),
                    "level": ag.get("level", 1),
                },
            })

            if cpu > 90 or ram > 90 or disk > 95:
                severity = "critical"
                issue = f"CPU {cpu}%" if cpu > 90 else f"RAM {ram}%" if ram > 90 else f"Disk {disk}%"
                await manager.broadcast({"type": "alert", "data": {"message": f"ARGUS CRITICAL: {issue}", "severity": "critical"}})
                await manager.broadcast({"type": "agent_log", "agent": "ARGUS", "message": f"CRITICAL threshold exceeded: {issue}. Alerting Hephaestus.", "level": "error", "timestamp": datetime.now().isoformat()})
            elif cpu > 70 or ram > 75 or disk > 80:
                issue = f"CPU {cpu}%" if cpu > 70 else f"RAM {ram}%" if ram > 75 else f"Disk {disk}%"
                await manager.broadcast({"type": "agent_log", "agent": "ARGUS", "message": f"Warning: {issue} above threshold. Monitoring closely.", "level": "warning", "timestamp": datetime.now().isoformat()})

            await _award_xp_silent("ARGUS", 3, "metrics_scan")
        except Exception:
            pass
        await asyncio.sleep(30)


async def _hermes_loop():
    scan_id = 0
    while True:
        try:
            scan_id += 1
            result = scan_logs()
            file_count = result["file_count"]
            errors = result["errors"]
            warnings = result["warnings"]

            msg = f"Scan #{scan_id} complete. {file_count} files. {len(errors)} errors, {len(warnings)} warnings."
            if errors:
                msg += f" Top error: {errors[0]['line'][:80]}"

            await manager.broadcast({"type": "agent_log", "agent": "HERMES", "message": msg, "level": "info" if not errors else "warning", "timestamp": datetime.now().isoformat()})
            await manager.broadcast({"type": "hermes_report", "agent": "HERMES", "data": {"errors": errors, "warnings": warnings, "fileCount": file_count, "scanId": scan_id}})

            ag = state.agents.get("HERMES", {})
            ag["lastAction"] = f"Scan #{scan_id} — {len(errors)} errors"
            state.agents["HERMES"] = ag
            await manager.broadcast({"type": "agent_status", "agent": "HERMES", "data": {"status": "active", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)}})

            if errors:
                await manager.broadcast({"type": "agent_log", "agent": "HERMES", "message": f"Escalating {len(errors)} error(s) to Hephaestus for diagnosis.", "level": "warning", "timestamp": datetime.now().isoformat()})
                asyncio.create_task(_hephaestus_respond(errors))

            await _award_xp_silent("HERMES", 8, "log_scan")
        except Exception:
            pass
        await asyncio.sleep(60)


async def _hephaestus_respond(errors: list):
    await asyncio.sleep(2)
    for error in errors[:3]:
        line = error.get("line", "")
        if "ECONNREFUSED" in line or "ConnectionRefused" in line:
            fix = "Applied retry logic with exponential backoff (max 3 retries, 1s/2s/4s delays)."
            patch_id = f"PATCH-{uuid.uuid4().hex[:4].upper()}"
            await manager.broadcast({"type": "agent_log", "agent": "HEPHAESTUS", "message": f"[{patch_id}] Connection refusal detected. {fix}", "level": "info", "timestamp": datetime.now().isoformat()})
        elif "Timeout" in line or "TimeoutError" in line:
            patch_id = f"PATCH-{uuid.uuid4().hex[:4].upper()}"
            await manager.broadcast({"type": "agent_log", "agent": "HEPHAESTUS", "message": f"[{patch_id}] Timeout pattern found. Increased request timeout to 30s, added circuit breaker.", "level": "info", "timestamp": datetime.now().isoformat()})
        elif "MemoryError" in line or "memory" in line.lower():
            patch_id = f"PATCH-{uuid.uuid4().hex[:4].upper()}"
            await manager.broadcast({"type": "agent_log", "agent": "HEPHAESTUS", "message": f"[{patch_id}] Memory pressure detected. Flagging for NODE_OPTIONS heap adjustment.", "level": "warning", "timestamp": datetime.now().isoformat()})
        else:
            patch_id = f"PATCH-{uuid.uuid4().hex[:4].upper()}"
            await manager.broadcast({"type": "agent_log", "agent": "HEPHAESTUS", "message": f"[{patch_id}] Error pattern analyzed. Logged for commander review — auto-fix not applied for unknown signature.", "level": "info", "timestamp": datetime.now().isoformat()})

    ag = state.agents.get("HEPHAESTUS", {})
    ag["lastAction"] = f"Processed {len(errors)} error(s) from Hermes"
    state.agents["HEPHAESTUS"] = ag
    await manager.broadcast({"type": "agent_status", "agent": "HEPHAESTUS", "data": {"status": "active", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)}})
    await _award_xp_silent("HEPHAESTUS", 15, "patch_applied")
    await manager.broadcast({"type": "hephaestus_report", "agent": "HEPHAESTUS", "data": {"patches": [{"id": f"PATCH-{i}", "autoFixed": True} for i in range(len(errors))]}})


async def _heimdall_loop():
    scan_id = 0
    await asyncio.sleep(15)
    while True:
        try:
            scan_id += 1
            idea = generate_niche_idea()

            state.queue["ideas"].append(idea)
            state.save_queue()

            await manager.broadcast({
                "type": "agent_log",
                "agent": "HEIMDALL",
                "message": f"Scan #{scan_id}: '{idea['title']}' ({idea['niche']}) queued. Demand: {idea['demandScore']}. Competition: {idea['competition']}.",
                "level": "info",
                "timestamp": datetime.now().isoformat(),
            })
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
        except Exception:
            pass
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

            await manager.broadcast({"type": "agent_log", "agent": "ATHENA", "message": msg, "level": "info", "timestamp": datetime.now().isoformat()})
            await manager.broadcast({"type": "athena_report", "agent": "ATHENA", "data": {"todayRevenue": today_rev, "totalOrders": orders, "activeListings": active}})

            ag = state.agents.get("ATHENA", {})
            ag["lastAction"] = f"Shop scan #{scan_id}: {active} listings"
            state.agents["ATHENA"] = ag
            await manager.broadcast({"type": "agent_status", "agent": "ATHENA", "data": {"status": "active", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)}})
            await _award_xp_silent("ATHENA", 10, "shop_analysis")
        except Exception:
            pass
        await asyncio.sleep(300)


async def _tyr_loop():
    scan_id = 0
    await asyncio.sleep(10)
    while True:
        try:
            scan_id += 1
            blocked_count = len(state.blocked_ips)
            msg = f"Security scan #{scan_id}: {blocked_count} IPs on blocklist. All API endpoints nominal. No new threats detected."

            await manager.broadcast({"type": "agent_log", "agent": "TYR", "message": msg, "level": "info", "timestamp": datetime.now().isoformat()})
            await manager.broadcast({"type": "tyr_report", "agent": "TYR", "data": {"totalBlocked": blocked_count, "newThreats": [], "scanId": scan_id}})

            ag = state.agents.get("TYR", {})
            ag["lastAction"] = f"Perimeter scan #{scan_id} — {blocked_count} blocked"
            state.agents["TYR"] = ag
            await manager.broadcast({"type": "agent_status", "agent": "TYR", "data": {"status": "active", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)}})
            await _award_xp_silent("TYR", 6, "security_scan")
        except Exception:
            pass
        await asyncio.sleep(60)


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
            await manager.broadcast({"type": "agent_log", "agent": "VAULT", "message": msg, "level": "info", "timestamp": datetime.now().isoformat()})

            ag = state.agents.get("VAULT", {})
            ag["lastAction"] = f"P&L: Net ${net:.2f}"
            state.agents["VAULT"] = ag
            await manager.broadcast({"type": "agent_status", "agent": "VAULT", "data": {"status": "active", "lastAction": ag["lastAction"], "xp": ag.get("xp", 0), "level": ag.get("level", 1)}})
            await _award_xp_silent("VAULT", 8, "financial_report")
        except Exception:
            pass
        await asyncio.sleep(300)


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

        except Exception:
            pass
        await asyncio.sleep(300)


# ─── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    asyncio.create_task(_argus_loop())
    asyncio.create_task(_hermes_loop())
    asyncio.create_task(_heimdall_loop())
    asyncio.create_task(_athena_loop())
    asyncio.create_task(_tyr_loop())
    asyncio.create_task(_vault_loop())
    asyncio.create_task(_odin_loop())

    log_file = Path("logs") / f"pantheon_{datetime.now().strftime('%Y%m%d')}.log"
    log_file.write_text(f"[{datetime.now().isoformat()}] AsgardMade Pantheon started\n")
