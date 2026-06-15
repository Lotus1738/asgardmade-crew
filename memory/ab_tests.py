"""
A/B title testing engine for AsgardMade Pantheon.

Manages active title tests per Etsy listing:
- LOKI creates a test when publishing each listing (title_a vs title_b)
- GUARDIAN checks stats after 7 days and picks the winner
- Winning patterns are injected back into LOKI's prompt to improve future titles
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_FILE = Path("data/ab_tests.json")


def _load() -> list[dict]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except Exception:
            pass
    return []


def _save(tests: list[dict]) -> None:
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(tests, indent=2, default=str))


def create_test(listing_id: str, title_a: str, title_b: str, niche: str) -> dict:
    """Create a new A/B title test and persist it. Returns the test dict."""
    tests = _load()
    test = {
        "test_id": str(uuid.uuid4()),
        "listing_id": str(listing_id),
        "title_a": title_a,
        "title_b": title_b,
        "current_title": "a",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "niche": niche,
        "status": "active",
        "winner": None,
    }
    tests.append(test)
    _save(tests)
    return test


def get_active_tests() -> list[dict]:
    """Return all tests with status='active'."""
    return [t for t in _load() if t.get("status") == "active"]


def get_tests_ready_for_check(days: int = 7) -> list[dict]:
    """Return active tests that are at least `days` old."""
    now = datetime.now(timezone.utc)
    ready = []
    for t in get_active_tests():
        try:
            started = datetime.fromisoformat(t["started_at"])
            # Make timezone-aware if naive
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            age_days = (now - started).days
            if age_days >= days:
                ready.append(t)
        except Exception:
            pass
    return ready


def complete_test(test_id: str, winner: str) -> None:
    """Mark a test complete with the given winner ('a' or 'b')."""
    tests = _load()
    for t in tests:
        if t["test_id"] == test_id:
            t["status"] = "complete"
            t["winner"] = winner
            t["completed_at"] = datetime.now(timezone.utc).isoformat()
            break
    _save(tests)


def get_winning_patterns() -> str:
    """
    Return a summary string of what title patterns have won A/B tests.
    Injected into LOKI's prompt so future titles learn from real results.
    """
    tests = [t for t in _load() if t.get("status") == "complete" and t.get("winner")]
    if not tests:
        return "No A/B test results yet — keep publishing listings to build data."

    b_wins = [t for t in tests if t["winner"] == "b"]
    a_wins = [t for t in tests if t["winner"] == "a"]
    total = len(tests)

    lines = [
        f"A/B TEST RESULTS ({total} completed tests):",
        f"Title B won: {len(b_wins)}/{total} times ({round(len(b_wins)/total*100)}%)",
        f"Title A won: {len(a_wins)}/{total} times ({round(len(a_wins)/total*100)}%)",
        "",
        "Recent winning titles (winner indicated):",
    ]

    # Show up to 5 most recent completed tests
    recent = sorted(tests, key=lambda x: x.get("completed_at", ""), reverse=True)[:5]
    for t in recent:
        winner_title = t["title_b"] if t["winner"] == "b" else t["title_a"]
        loser_title = t["title_a"] if t["winner"] == "b" else t["title_b"]
        lines.append(f"  ✓ [{t['niche']}] WON: \"{winner_title}\"")
        lines.append(f"       vs LOST: \"{loser_title}\"")

    # Derive simple heuristics from win patterns
    b_win_titles = [t["title_b"] for t in b_wins]
    year_wins = sum(1 for title in b_win_titles if "2026" in title or "2025" in title)
    gift_wins = sum(1 for title in b_win_titles if "gift" in title.lower())
    product_lead_wins = sum(
        1 for t in b_wins
        if t["title_b"].split()[0].lower() in ("nurse", "cat", "dog", "plant", "book", "coffee", "mom", "dad")
    )

    lines.append("")
    lines.append("Observed patterns in winning titles:")
    if year_wins > len(b_wins) * 0.4:
        lines.append("  → Including year (e.g. '2026') in the title tends to win")
    if gift_wins > len(b_wins) * 0.4:
        lines.append("  → 'Gift for [persona]' framing tends to win")
    if product_lead_wins > len(b_wins) * 0.3:
        lines.append("  → Leading with the buyer persona / product type tends to win")
    if len(b_wins) > len(a_wins):
        lines.append("  → In general, variant titles (B) are outperforming original titles (A) — be bolder with variants")
    elif len(a_wins) > len(b_wins):
        lines.append("  → Original titles (A) are holding — focus on keyword precision over creativity in variants")

    return "\n".join(lines)
