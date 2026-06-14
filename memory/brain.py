"""
AsgardMade Brain — Self-improving memory layer.

Every 6 hours, Claude reads each agent's raw conversation logs and outcome
history, distills them into concrete lessons, and writes those lessons back.
On every chat call, the agent's lessons get injected into its system prompt
so it literally gets smarter from every interaction.

Storage: <OBSIDIAN_VAULT_PATH>/_brain/ (flat JSON files, no deps needed)
"""

import json
import os
import traceback
from datetime import datetime
from pathlib import Path

_VAULT = Path(os.getenv("OBSIDIAN_VAULT_PATH", r"C:\Users\Mario\AsgardMade HQ"))
BRAIN_DIR = _VAULT / "_brain"


# ─── Lessons (read / write) ──────────────────────────────────────────────────

def get_agent_lessons(agent_name: str) -> str:
    """
    Return this agent's current distilled lessons as a short text block.
    Called by server.py before every chat to inject into the system prompt.
    Returns empty string if no lessons exist yet.
    """
    lesson_file = BRAIN_DIR / f"{agent_name.upper()}_lessons.json"
    if not lesson_file.exists():
        return ""
    try:
        data = json.loads(lesson_file.read_text(encoding="utf-8"))
        lessons = data.get("lessons", [])
        if not lessons:
            return ""
        lines = ["Learned from past decisions (apply these automatically):"]
        for lesson in lessons[:6]:  # cap at 6 so prompt stays tight
            lines.append(f"- {lesson}")
        return "\n".join(lines)
    except Exception:
        return ""


def write_agent_lessons(agent_name: str, lessons: list, summary: str) -> None:
    """Write distilled lessons after a synthesis run."""
    try:
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        lesson_file = BRAIN_DIR / f"{agent_name.upper()}_lessons.json"
        data = {
            "agent": agent_name.upper(),
            "updated": datetime.now().isoformat(),
            "summary": summary,
            "lessons": lessons,
        }
        lesson_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[BRAIN] write_agent_lessons error for {agent_name}: {e}")


# ─── Outcome tracking ────────────────────────────────────────────────────────

def record_outcome(agent_name: str, action: str, outcome: str, score: int) -> None:
    """
    Record the result of an agent decision for future synthesis.
    score: 1-10 (10 = great result, 1 = bad outcome)

    Examples:
      record_outcome("HEIMDALL", "Queued 'Dog Mom Mug'", "Approved by commander", 9)
      record_outcome("VULCAN", "Generated flat vector dog design", "Rejected — too generic", 2)
      record_outcome("LOKI", "Listed at $34.99 with 13 tags", "3 views in first hour", 6)
    """
    try:
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        outcomes_file = BRAIN_DIR / f"{agent_name.upper()}_outcomes.jsonl"
        entry = json.dumps({
            "ts": datetime.now().isoformat(),
            "agent": agent_name.upper(),
            "action": action,
            "outcome": outcome,
            "score": score,
        }, ensure_ascii=False)
        with open(outcomes_file, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception as e:
        print(f"[BRAIN] record_outcome error: {e}")


def get_all_outcomes(agent_name: str, limit: int = 20) -> list:
    """Read the agent's recent outcome history."""
    outcomes_file = BRAIN_DIR / f"{agent_name.upper()}_outcomes.jsonl"
    if not outcomes_file.exists():
        return []
    try:
        lines = outcomes_file.read_text(encoding="utf-8").strip().split("\n")
        results = []
        for line in lines[-limit:]:
            stripped = line.strip()
            if stripped:
                results.append(json.loads(stripped))
        return results
    except Exception:
        return []


# ─── Synthesis prompt builder ─────────────────────────────────────────────────

def build_synthesis_prompt(agent_name: str, memory_text: str, outcome_text: str) -> str:
    """Build the Claude prompt for distilling an agent's memories into lessons."""
    return f"""You are analyzing the memory logs for {agent_name}, an AI agent running an automated Etsy print-on-demand business.

RECENT CONVERSATION LOGS:
{memory_text or "No conversation logs yet."}

PAST DECISION OUTCOMES:
{outcome_text or "No outcomes recorded yet."}

Extract 3-6 specific, actionable lessons that {agent_name} should permanently remember.
Focus on:
- What the commander (business owner) approves or rejects
- Patterns that led to good outcomes (high score)
- Mistakes to avoid (low score)
- Preferences or style choices revealed in conversations
- Niche/product/design signals that worked or flopped

Return ONLY this JSON object (no markdown, no explanation):
{{"lessons": ["specific lesson 1", "specific lesson 2", ...], "summary": "one sentence about what {agent_name} learned overall"}}"""


# ─── Brain health check ───────────────────────────────────────────────────────

def brain_status() -> dict:
    """Return a summary of brain state for debugging."""
    if not BRAIN_DIR.exists():
        return {"ready": False, "reason": "Brain directory does not exist yet"}
    files = list(BRAIN_DIR.glob("*.json"))
    outcome_files = list(BRAIN_DIR.glob("*.jsonl"))
    agents_with_lessons = [f.stem.replace("_lessons", "") for f in files if "_lessons" in f.name]
    agents_with_outcomes = [f.stem.replace("_outcomes", "") for f in outcome_files]
    return {
        "ready": True,
        "brain_dir": str(BRAIN_DIR),
        "agents_with_lessons": agents_with_lessons,
        "agents_with_outcomes": agents_with_outcomes,
        "total_files": len(files) + len(outcome_files),
    }
