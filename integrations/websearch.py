"""
Web search integration for Pantheon agents.

Uses the duckduckgo-search library (already in requirements.txt — no API key needed).
Gives HEIMDALL, ODIN, and other agents live market intelligence for free.

Usage:
    from integrations.websearch import search, search_etsy_trends, search_niche_intel

    results = await search_etsy_trends("cottagecore")
    intel   = await search_niche_intel("dark academia")
    current = await search_current_events("etsy algorithm changes")
"""

import asyncio
import re
from typing import Optional

try:
    from duckduckgo_search import DDGS
    _HAS_DDG = True
except ImportError:
    _HAS_DDG = False


def _sync_search(query: str, max_results: int = 8) -> list[dict]:
    """Synchronous DuckDuckGo search — run via asyncio executor."""
    if not _HAS_DDG:
        return []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, region="wt-wt"))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in results
        ]
    except Exception as e:
        print(f"[WEBSEARCH] DuckDuckGo error for '{query}': {type(e).__name__}: {e}")
        return []


async def search(query: str, max_results: int = 8) -> list[dict]:
    """
    Async web search via DuckDuckGo. No API key required.
    Returns list of: {"title": str, "url": str, "snippet": str}
    """
    if not _HAS_DDG:
        print("[WEBSEARCH] duckduckgo-search not installed — run: pip install duckduckgo-search")
        return []
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_search, query, max_results)


async def search_etsy_trends(niche: str) -> list[dict]:
    """
    Multi-query niche trend search for HEIMDALL.
    Hits 3 angles: bestsellers, trending POD, profitability signals.
    """
    queries = [
        f"{niche} etsy best sellers 2026",
        f"{niche} print on demand trending",
        f"etsy {niche} profitable niche low competition",
    ]
    all_results = []
    for q in queries:
        results = await search(q, max_results=4)
        all_results.extend(results)
        await asyncio.sleep(0.3)  # polite rate limiting
    # Deduplicate by URL
    seen = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    return unique[:12]


async def search_niche_intel(niche: str) -> dict:
    """
    Full niche intelligence scan for HEIMDALL scoring.
    Returns demand/competition signals extracted from search results.
    """
    results = await search_etsy_trends(niche)
    snippets_text = " ".join(r.get("snippet", "") for r in results)

    demand_signals = len(re.findall(
        r"trending|popular|best.sell|high demand|viral|growing|hot|top sell|surge|spike",
        snippets_text, re.IGNORECASE
    ))
    competition_signals = len(re.findall(
        r"saturated|competitive|too many|overcrowded|flooded|crowded",
        snippets_text, re.IGNORECASE
    ))
    seasonal_hits = re.findall(
        r"holiday|christmas|summer|spring|fall|halloween|valentine|mother'?s|father'?s|back.to.school",
        snippets_text, re.IGNORECASE
    )

    return {
        "niche": niche,
        "results_found": len(results),
        "demand_signals": demand_signals,
        "competition_signals": competition_signals,
        "seasonal_tags": list(set(s.lower() for s in seasonal_hits)),
        "top_snippets": [r["snippet"] for r in results[:3] if r.get("snippet")],
        "raw_results": results,
    }


async def search_competitor_intel(niche: str, max_results: int = 5) -> list[dict]:
    """ODIN uses this to monitor what competitor Etsy shops are doing."""
    return await search(f"top etsy shops {niche} print on demand 2026", max_results)


async def search_current_events(topic: str) -> list[dict]:
    """General search for ODIN strategy — market shifts, platform updates, etc."""
    return await search(f"{topic} 2026", max_results=6)


async def search_platform_news() -> list[dict]:
    """ODIN monitors Etsy/Printify platform changes that affect strategy."""
    queries = [
        "etsy algorithm update 2026",
        "etsy fee changes 2026",
        "printify new features 2026",
    ]
    results = []
    for q in queries:
        results.extend(await search(q, max_results=3))
        await asyncio.sleep(0.2)
    return results[:9]
