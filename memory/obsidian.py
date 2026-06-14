"""
Obsidian vault memory system for AsgardMade Pantheon.

Agents read and write markdown notes to the vault so the system learns
over time from commander approvals, rejections, and chat feedback.
All functions fail silently if the vault path doesn't exist (Railway safety).

Vault path is set via OBSIDIAN_VAULT_PATH env var, defaulting to
C:\\Users\\Mario\\AsgardMade HQ
"""

import os
import traceback
from pathlib import Path
from datetime import datetime, date

VAULT = Path(os.getenv("OBSIDIAN_VAULT_PATH", r"C:\Users\Mario\AsgardMade HQ"))
PREFS_PATH = "Odin Intelligence/Commander Preferences.md"

_directive_counter = 0


# ─── Vault availability ──────────────────────────────────────────────────────

def vault_available() -> bool:
    return VAULT.exists()


# ─── Core read / write ───────────────────────────────────────────────────────

def write(rel_path: str, content: str, append: bool = False) -> str | None:
    if not vault_available():
        return None
    try:
        path = VAULT / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if append and path.exists():
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing + "\n\n---\n\n" + content, encoding="utf-8")
        else:
            path.write_text(content, encoding="utf-8")
        return str(path)
    except Exception as e:
        print(f"[MEMORY] write error {rel_path}: {e}")
        return None


def read(rel_path: str) -> str | None:
    if not vault_available():
        return None
    try:
        path = VAULT / rel_path
        return path.read_text(encoding="utf-8") if path.exists() else None
    except Exception:
        return None


def read_folder(rel_folder: str, limit: int = 5) -> list[dict]:
    if not vault_available():
        return []
    try:
        folder = VAULT / rel_folder
        if not folder.exists():
            return []
        files = sorted(folder.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        results = []
        for f in files[:limit]:
            try:
                results.append({"name": f.stem, "content": f.read_text(encoding="utf-8")[:2000]})
            except Exception:
                pass
        return results
    except Exception:
        return []


def list_files(rel_folder: str) -> list[str]:
    if not vault_available():
        return []
    try:
        folder = VAULT / rel_folder
        return [f.stem for f in sorted(folder.glob("*.md"))] if folder.exists() else []
    except Exception:
        return []


# ─── Commander Preferences ───────────────────────────────────────────────────

def read_preferences() -> str:
    content = read(PREFS_PATH)
    if not content:
        content = _default_preferences()
        write(PREFS_PATH, content)
    return content or ""


def update_preferences(section: str, entry: str, timestamp: str | None = None) -> None:
    if not vault_available():
        return
    try:
        ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")
        content = read_preferences()
        marker = f"## {section}"
        if marker not in content:
            content += f"\n\n{marker}\n"
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.strip() == marker:
                lines.insert(i + 1, f"- {ts}: {entry}")
                break
        content = _set_last_modified("\n".join(lines))
        write(PREFS_PATH, content)
    except Exception as e:
        print(f"[MEMORY] update_preferences error: {e}")


def _set_last_modified(content: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("Last updated:"):
            lines[i] = f"Last updated: {now}"
            return "\n".join(lines)
    return f"Last updated: {now}\n\n" + content


def _default_preferences() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""# Commander Preferences
Last updated: {now}

## Approved Niches

## Rejected Niches

## Approved Design Styles

## Rejected Design Styles

## Pricing Strategy
- Default listing price: $24.99

## Chat Feedback

## Strategic Directives
"""


# ─── HEIMDALL ────────────────────────────────────────────────────────────────

def heimdall_write_research(idea: dict) -> None:
    today = date.today().isoformat()
    niche = idea.get("niche", "General")
    safe_niche = _safe(niche)
    safe_title = _safe(idea.get("title", "idea"))[:50]
    content = f"""# {idea.get("title", "Untitled")}
Niche: {niche}
Date: {today}
Status: Pending Approval

## Market Data
- Demand Score: {idea.get("demandScore", "N/A")}
- Competition: {idea.get("competition", "N/A")}
- Estimated Monthly Revenue: {idea.get("estimatedMonthlyRevenue", "N/A")}
- Product Type: {idea.get("productType", "N/A")}
- Price Range: {idea.get("priceRange", "N/A")}

## Keywords
{chr(10).join(f"- {k}" for k in idea.get("keywords", []))}

## Description
{idea.get("description", "")}

## Idea ID
{idea.get("id", "")}
"""
    write(f"Niches/{safe_niche}/Pending/{today}_{safe_title}.md", content)


def heimdall_write_approved(idea: dict) -> None:
    niche = idea.get("niche", "General")
    safe_niche = _safe(niche)
    safe_title = _safe(idea.get("title", "idea"))[:60]
    content = f"""# ✅ APPROVED: {idea.get("title", "Untitled")}
Niche: {niche}
Approved: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Approval Signals
- Demand Score: {idea.get("demandScore", "N/A")}
- Competition: {idea.get("competition", "N/A")}
- Revenue Potential: {idea.get("estimatedMonthlyRevenue", "N/A")}
- Product Type: {idea.get("productType", "N/A")}

## Keywords
{", ".join(idea.get("keywords", []))}

## Learning
Commander approved this niche/style. Increase frequency of similar ideas.

## Idea ID
{idea.get("id", "")}
"""
    write(f"Niches/{safe_niche}/Approved/{safe_title}.md", content)
    update_preferences(
        "Approved Niches",
        f"{idea.get('title')} ({niche}) — demand {idea.get('demandScore', '?')}, {idea.get('productType', 'unknown')}"
    )
    # Briefing note for Vulcan to read before designing
    write(f"Niches/Briefings/{idea.get('id', 'unknown')}.md", f"""# Vulcan Briefing: {idea.get("title", "Untitled")}
From: Heimdall → To: Vulcan
Created: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Design Brief
Product: **{idea.get("title", "Untitled")}**
Niche: {niche}
Product Type: {idea.get("productType", "t-shirt")}

## Target Keywords
{", ".join(idea.get("keywords", [])[:7])}

## Market Context
- Demand Score: {idea.get("demandScore", "N/A")} — high demand, prioritize quality
- Competition: {idea.get("competition", "N/A")}
- Revenue Target: {idea.get("estimatedMonthlyRevenue", "N/A")}

## Instructions for Vulcan
1. Read /Odin Intelligence/Commander Preferences.md before designing
2. Check /Products/Approved/ for visual styles commander has approved
3. Avoid styles listed in /Products/Rejected/
4. Build a flat vector illustration optimized for {idea.get("productType", "t-shirt")} printing
""")


def heimdall_write_rejected(idea: dict) -> None:
    today = date.today().isoformat()
    niche = idea.get("niche", "General")
    safe_niche = _safe(niche)
    safe_title = _safe(idea.get("title", "idea"))[:50]
    content = f"""# ❌ REJECTED: {idea.get("title", "Untitled")}
Niche: {niche}
Rejected: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Context at Rejection
- Demand Score: {idea.get("demandScore", "N/A")}
- Competition: {idea.get("competition", "N/A")}
- Product Type: {idea.get("productType", "N/A")}

## Learning
Avoid this concept/style combination in this niche.
Keywords used: {", ".join(idea.get("keywords", []))}

## Idea ID
{idea.get("id", "")}
"""
    write(f"Niches/{safe_niche}/Rejected/{today}_{safe_title}.md", content)
    update_preferences("Rejected Niches", f"{idea.get('title')} ({niche}) — avoid similar")


def heimdall_read_context() -> str:
    """What Heimdall reads before generating a new idea."""
    approved = read_folder("Niches", limit=3)
    prefs = read_preferences()
    parts = ["## Heimdall Memory\n"]
    if approved:
        parts.append("### Recent Approved Niche Patterns\n" +
                     "\n---\n".join(f["content"][:600] for f in approved))
    parts.append(f"\n### Commander Preferences\n{prefs[:1200]}")
    return "\n\n".join(parts)


# ─── VULCAN ──────────────────────────────────────────────────────────────────

def vulcan_write_generated(design: dict) -> None:
    today = date.today().isoformat()
    safe_title = _safe(design.get("ideaTitle", "design"))[:50]
    v = design.get("variantIndex", 1)
    content = f"""# Design Generated: {design.get("ideaTitle", "Untitled")} (Variant {v})
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}
Niche: {design.get("niche", "General")}
Product Type: {design.get("productType", "t-shirt")}
Demo Mode: {design.get("demo", True)}

## DALL-E Prompt
{design.get("prompt", "N/A")}

## Image URL
{design.get("imageUrl", "N/A")}

## Status
Pending commander approval.

## Design ID
{design.get("id", "")}
"""
    write(f"Products/Generated/{today}_{safe_title}_v{v}.md", content)


def vulcan_write_approved(design: dict) -> None:
    safe_title = _safe(design.get("ideaTitle", "design"))[:60]
    content = f"""# ✅ APPROVED DESIGN: {design.get("ideaTitle", "Untitled")}
Approved: {datetime.now().strftime("%Y-%m-%d %H:%M")}
Niche: {design.get("niche", "General")}
Product Type: {design.get("productType", "t-shirt")}
Variant Selected: {design.get("variantIndex", 1)}

## Winning Prompt
{design.get("prompt", "N/A")}

## Why It Worked
- Niche: {design.get("niche", "General")} — commander approved this aesthetic
- Variant {design.get("variantIndex", 1)} was selected over alternatives

## Visual Style Notes
Flat vector, bold composition, {design.get("niche", "general")} aesthetic. Replicate this approach.

## Image
{design.get("imageUrl", "N/A")}

## Design ID
{design.get("id", "")}
"""
    write(f"Products/Approved/{safe_title}.md", content)
    update_preferences(
        "Approved Design Styles",
        f"{design.get('niche', 'General')} / {design.get('productType', 't-shirt')} — variant {design.get('variantIndex', 1)} approved"
    )
    # Briefing note for Loki
    write(f"Products/Briefings/{design.get('id', 'unknown')}.md", f"""# Loki Briefing: {design.get("ideaTitle", "Untitled")}
From: Vulcan → To: Loki
Created: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Listing Brief
Product: **{design.get("ideaTitle", "Untitled")}**
Niche: {design.get("niche", "General")}
Product Type: {design.get("productType", "t-shirt")}

## SEO Context
Target the {design.get("niche", "general").lower()} niche.
Keywords from Heimdall: {", ".join(design.get("keywords", []))}

## Pricing
$24.99 standard. Adjust only if Odin Directives say otherwise.

## Instructions for Loki
1. Read /Odin Intelligence/Commander Preferences.md before listing
2. Check /Products/Active Listings/ for top-performing title patterns
3. Use 13 tags — 4 high-volume anchors, 6 niche long-tails, 3 buyer-intent modifiers
4. Lead title with primary keyword for Etsy search rank
""")


def vulcan_write_rejected(design: dict) -> None:
    today = date.today().isoformat()
    safe_title = _safe(design.get("ideaTitle", "design"))[:50]
    content = f"""# ❌ REJECTED DESIGN: {design.get("ideaTitle", "Untitled")}
Rejected: {datetime.now().strftime("%Y-%m-%d %H:%M")}
Niche: {design.get("niche", "General")}
Variant: {design.get("variantIndex", 1)}

## Rejected Prompt
{design.get("prompt", "N/A")}

## Learning
This visual approach was rejected. Avoid similar prompt structures for {design.get("niche", "general")} niche.

## Design ID
{design.get("id", "")}
"""
    write(f"Products/Rejected/{today}_{safe_title}.md", content)
    update_preferences(
        "Rejected Design Styles",
        f"{design.get('niche', 'General')} variant {design.get('variantIndex', 1)} — avoid this prompt style"
    )


def vulcan_read_context(idea: dict) -> str:
    """What Vulcan reads before generating designs."""
    approved = read_folder("Products/Approved", limit=3)
    rejected = read_folder("Products/Rejected", limit=2)
    briefing = read(f"Niches/Briefings/{idea.get('id', '')}.md")
    prefs = read_preferences()
    parts = [f"## Vulcan Memory for: {idea.get('title', 'Unknown')}\n"]
    if briefing:
        parts.append(f"### Heimdall's Brief\n{briefing[:800]}")
    if approved:
        parts.append("### Approved Design Styles (replicate these patterns)\n" +
                     "\n---\n".join(f["content"][:500] for f in approved))
    if rejected:
        parts.append("### Rejected Styles (avoid these)\n" +
                     "\n---\n".join(f["content"][:300] for f in rejected))
    parts.append(f"### Commander Preferences\n{prefs[:800]}")
    return "\n\n".join(parts)


# ─── LOKI ────────────────────────────────────────────────────────────────────

def loki_write_listing(design: dict, listing: dict) -> None:
    safe_title = _safe(design.get("ideaTitle", "listing"))[:60]
    content = f"""# Listing: {listing.get("title", design.get("ideaTitle", "Untitled"))}
Created: {datetime.now().strftime("%Y-%m-%d %H:%M")}
Listing ID: {listing.get("listing_id", "N/A")}
Price: ${listing.get("price", 24.99):.2f}
Niche: {design.get("niche", "General")}
Product Type: {design.get("productType", "t-shirt")}
Demo: {listing.get("demo", True)}

## SEO Title
{listing.get("title", "N/A")}

## Tags Applied
{", ".join(listing.get("tags", []))}

## Performance Tracking
- Views: 0
- Favorites: 0
- Sales: 0
- Conversion Rate: N/A
- Last Updated: {date.today().isoformat()}

## Source
Idea: {design.get("ideaTitle", "N/A")}

## Notes
Update views/sales weekly. Identify title patterns from high converters.
"""
    write(f"Products/Active Listings/{safe_title}.md", content)


def loki_read_context(design: dict) -> str:
    """What Loki reads before creating a listing."""
    top = read_folder("Products/Active Listings", limit=3)
    briefing = read(f"Products/Briefings/{design.get('id', '')}.md")
    prefs = read_preferences()
    parts = ["## Loki Memory\n"]
    if briefing:
        parts.append(f"### Vulcan's Brief\n{briefing[:800]}")
    if top:
        parts.append("### Recent Active Listings (model successful patterns)\n" +
                     "\n---\n".join(f["content"][:400] for f in top))
    parts.append(f"### Commander Preferences\n{prefs[:600]}")
    return "\n\n".join(parts)


# ─── VAULT ───────────────────────────────────────────────────────────────────

def vault_write_transaction(txn: dict) -> None:
    today = date.today().isoformat()
    entry = (f"### {txn.get('type', 'unknown').upper()}: ${txn.get('amount', 0):.2f}\n"
             f"Time: {datetime.now().strftime('%H:%M')}\n"
             f"Description: {txn.get('description', 'N/A')}\n"
             f"Source: {txn.get('source', 'N/A')}\n"
             f"ID: {txn.get('id', 'N/A')}\n")
    write(f"Revenue/Transactions/{today}.md", entry, append=True)


def vault_write_daily_pl(vault_state: dict) -> None:
    today = date.today().isoformat()
    rev = vault_state.get("totalRevenue", 0)
    exp = vault_state.get("totalExpenses", 0)
    net = vault_state.get("netProfit", 0)
    margin = vault_state.get("profitMarginPct", 0)
    txn_count = len(vault_state.get("transactions", []))
    health = ("✅ Profitable" if net > 0
              else "⚠️ Operating at a loss" if net < 0
              else "⏳ No revenue yet — approve ideas to start the pipeline")
    note = ("Margin healthy for POD (target 45-60%)." if margin >= 45
            else "Margin below 45% — consider raising price by $2-3." if rev > 0
            else "Approve ideas and designs to build inventory.")
    content = f"""# Daily P&L Report: {today}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Summary
| Metric | Value |
|--------|-------|
| Total Revenue | ${rev:.2f} |
| Total Expenses | ${exp:.2f} |
| Net Profit | ${net:.2f} |
| Profit Margin | {margin:.1f}% |
| Transactions | {txn_count} |

## Health
{health}

## Note
{note}
"""
    write(f"Revenue/Daily P&L {today}.md", content)


def vault_write_monthly(vault_state: dict) -> None:
    month = datetime.now().strftime("%Y-%m")
    rev = vault_state.get("totalRevenue", 0)
    exp = vault_state.get("totalExpenses", 0)
    net = vault_state.get("netProfit", 0)
    content = f"""# Monthly Report: {month}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Revenue: ${rev:.2f}
## Expenses: ${exp:.2f}
## Net Profit: ${net:.2f}

## Trend
Compare to prior month in vault to assess growth trajectory.
"""
    write(f"Revenue/Monthly Reports/Report {month}.md", content)


# ─── ATHENA ──────────────────────────────────────────────────────────────────

def athena_write_analysis(stats: dict) -> None:
    today = date.today().isoformat()
    listings = stats.get("active_listings", 0)
    orders = stats.get("total_orders", 0)
    conv = round((orders / listings * 100), 1) if listings > 0 and orders > 0 else 0
    insights = []
    if listings < 5:
        insights.append("Critical: Low listing count limits Etsy search exposure")
    if conv > 5:
        insights.append(f"Strong conversion at {conv}% — current niches resonate")
    elif conv > 0:
        insights.append(f"Conversion at {conv}% — review listing titles and tags")
    if not insights:
        insights.append("Insufficient data — need active listings and orders")
    content = f"""# Athena Market Analysis: {today}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Shop Stats
- Active Listings: {listings}
- Total Orders: {orders}
- Today's Revenue: ${stats.get("today_revenue", 0):.2f}
- Conversion Proxy: {conv}%

## Insights
{chr(10).join(f"- {i}" for i in insights)}

## Recommended Action
{"Build listing inventory first." if listings < 10 else "Optimize conversion on existing listings."}
"""
    write(f"Odin Intelligence/Athena Analysis {today}.md", content)


# ─── ODIN ────────────────────────────────────────────────────────────────────

def odin_write_directive(strategy: str, context: dict) -> None:
    global _directive_counter
    _directive_counter += 1
    n = str(_directive_counter).zfill(3)
    content = f"""# Odin Directive #{n}
Issued: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Directive
{strategy}

## System Snapshot
- Revenue: ${context.get("totalRevenue", 0):.2f} | Net: ${context.get("netProfit", 0):.2f}
- Pending Ideas: {context.get("pendingIdeas", 0)} | Pending Designs: {context.get("pendingDesigns", 0)}
- CPU: {context.get("cpu", 0)}% | RAM: {context.get("ram", 0)}%

---
All agents read this before making decisions.
"""
    write(f"Odin Intelligence/Odin Directives/Directive-{n}.md", content)


def odin_write_weekly_synthesis(agents: dict, context: dict) -> None:
    from datetime import date as d
    cal = d.today().isocalendar()
    week_id = f"{cal[0]}-W{cal[1]:02d}"
    agent_rows = "\n".join(
        f"- {name}: {data.get('xp', 0)} XP, Lvl {data.get('level', 1)}, {data.get('status', 'idle')}"
        for name, data in agents.items()
    )
    content = f"""# Odin Weekly Synthesis: {week_id}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Financial State
- Revenue: ${context.get("totalRevenue", 0):.2f}
- Net Profit: ${context.get("netProfit", 0):.2f}
- Margin: {context.get("profitMarginPct", 0):.1f}%

## Agent Performance
{agent_rows}

## System Improvements
{_synthesis_recs(context)}

## Next Week Priorities
1. Clear approval queue before generating new items
2. Monitor top XP agents for output quality
3. Review Revenue/Daily P&L trend for trajectory
"""
    write(f"Odin Intelligence/Weekly Synthesis {week_id}.md", content)
    write(f"Odin Intelligence/Weekly Synthesis {week_id}.md", content)


def _synthesis_recs(ctx: dict) -> str:
    recs = []
    if ctx.get("netProfit", 0) == 0:
        recs.append("No revenue yet — prioritize idea and design approvals")
    if ctx.get("pendingIdeas", 0) > 3:
        recs.append(f"Approval backlog: {ctx.get('pendingIdeas')} ideas queued")
    if ctx.get("pendingDesigns", 0) > 0:
        recs.append(f"{ctx.get('pendingDesigns')} designs need commander review")
    if not recs:
        recs.append("System operating well — maintain current cadence")
    return "\n".join(f"- {r}" for r in recs)


# ─── Chat feedback capture ───────────────────────────────────────────────────

FEEDBACK_KEYWORDS = [
    "price", "niche", "style", "design", "focus on", "avoid", "prefer",
    "want", "always", "never", "more", "less", "stop", "start", "change",
    "like", "don't like", "instead", "only", "should", "must"
]


def capture_chat_feedback(agent: str, message: str, reply: str) -> None:
    msg_lower = message.lower()
    if len(message) > 20 and any(k in msg_lower for k in FEEDBACK_KEYWORDS):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"[{agent}] \"{message[:200]}\""
        update_preferences("Chat Feedback", entry, ts)


def read_odin_directives(limit: int = 3) -> str:
    directives = read_folder("Odin Intelligence/Odin Directives", limit=limit)
    if not directives:
        return ""
    return "### Latest Odin Directives\n" + "\n---\n".join(d["content"][:500] for d in directives)


# ─── Agent personal memory ───────────────────────────────────────────────────

def agent_write_chat(agent: str, user_message: str, agent_reply: str, interaction_type: str = "conversation") -> None:
    """Append a chat exchange to the agent's personal memory folder."""
    if not vault_available():
        return
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        today = date.today().isoformat()
        entry = f"""---
Date: {ts}
Agent: {agent}
Type: {interaction_type}
Summary: Commander asked about {user_message[:80].strip().rstrip('?.')}.
---

**Commander:** {user_message[:500]}

**{agent}:** {agent_reply[:800]}

"""
        write(f"Agent Memory/{agent}/{today}.md", entry, append=True)
    except Exception as e:
        print(f"[MEMORY] agent_write_chat error: {e}")


def agent_read_memory(agent: str, limit: int = 3) -> str:
    """Read the agent's personal memory folder for context before responding."""
    files = read_folder(f"Agent Memory/{agent}", limit=limit)
    if not files:
        return ""
    return f"### {agent} Recent Conversation Memory\n" + "\n---\n".join(f["content"][:600] for f in files)


# ─── API helpers ─────────────────────────────────────────────────────────────

_AGENT_FOLDERS = {
    "HEIMDALL": "Niches",
    "VULCAN": "Products",
    "LOKI": "Products/Active Listings",
    "VAULT": "Revenue",
    "ATHENA": "Odin Intelligence",
    "ODIN": "Odin Intelligence",
    "HERMES": "Odin Intelligence/Hermes Reports",
    "HEPHAESTUS": "Odin Intelligence/Hephaestus Patches",
    "ARGUS": "Odin Intelligence/Argus Reports",
    "TYR": "Odin Intelligence/Tyr Reports",
}


def api_write(agent: str, topic: str, content: str, append: bool = False) -> dict:
    folder = _AGENT_FOLDERS.get(agent.upper(), "Odin Intelligence")
    safe_topic = _safe(topic)[:60]
    rel_path = f"{folder}/{date.today().isoformat()}_{safe_topic}.md"
    path = write(rel_path, content, append=append)
    return {"ok": bool(path), "path": rel_path, "vault_available": vault_available()}


def api_read(agent: str, topic: str) -> dict:
    folder = _AGENT_FOLDERS.get(agent.upper(), "Odin Intelligence")
    if topic.lower() in ("preferences", "commander", "prefs"):
        return {"content": read_preferences(), "path": PREFS_PATH, "vault_available": vault_available()}
    files = read_folder(folder, limit=5)
    return {"files": files, "folder": folder, "count": len(files), "vault_available": vault_available()}


# ─── Utility ─────────────────────────────────────────────────────────────────

def _safe(s: str) -> str:
    return s.replace("/", "-").replace("\\", "-").replace(":", "").replace("*", "").replace("?", "").replace('"', "").replace("<", "").replace(">", "").replace("|", "").strip()
