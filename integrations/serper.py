"""
Serper API integration — real Google search results for Heimdall research.
https://serper.dev  (POST to google.serper.dev/search with X-API-KEY header)

Demo fallback activates automatically when SERPER_API_KEY is not set.
"""

import os
import httpx

SERPER_URL = "https://google.serper.dev/search"

# The 5 core queries Heimdall runs every research cycle
CORE_QUERIES = [
    "trending etsy products 2026",
    "best selling print on demand niches 2026",
    "etsy bestseller dog mom gifts",
    "etsy trending art prints 2026",
    "printify top selling products",
]

_DEMO_SNIPPETS = [
    {"title": "Top Etsy trends 2026", "snippet": "Cottagecore botanical wall art, dog mom t-shirts, and retro gaming prints are driving the highest search volume on Etsy this year.", "link": "https://demo.example.com/1"},
    {"title": "Best selling POD niches", "snippet": "Mental health awareness hoodies, plant parent mugs, and dark academia aesthetic posters are the top-performing print-on-demand categories.", "link": "https://demo.example.com/2"},
    {"title": "Etsy bestsellers Q2 2026", "snippet": "Personalized pet portraits continue to dominate with 91-97 demand scores. Witchy aesthetic and minimalist line art showing strong upward trends.", "link": "https://demo.example.com/3"},
    {"title": "Print on demand product research", "snippet": "Coffee culture tumblers and hiking lifestyle wall art have low competition with steady year-round demand — ideal for new POD shops.", "link": "https://demo.example.com/4"},
    {"title": "Etsy art print trending searches", "snippet": "Space exploration science posters, pride celebration tote bags, and vintage botanical prints are surging in Etsy search data for 2026.", "link": "https://demo.example.com/5"},
]


async def _search(query: str, num: int = 8) -> list[dict]:
    """Execute a single Serper search. Returns list of organic result dicts."""
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return [dict(item, query=query, demo=True) for item in _DEMO_SNIPPETS]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                SERPER_URL,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": num},
            )
            resp.raise_for_status()
            data = resp.json()
            organic = data.get("organic", [])
            return [{"query": query, "title": r.get("title", ""), "snippet": r.get("snippet", ""), "link": r.get("link", "")} for r in organic]
    except Exception as e:
        print(f"[SERPER] search error for '{query}': {type(e).__name__}: {e}")
        return [dict(item, query=query, demo=True) for item in _DEMO_SNIPPETS[:3]]


async def search_trending_niches() -> list[dict]:
    """Search for currently trending Etsy niches and POD categories."""
    queries = [
        "trending etsy products 2026",
        "best selling print on demand niches 2026",
        "printify top selling products",
    ]
    results = []
    for q in queries:
        hits = await _search(q, num=8)
        results.extend(hits)
    return results


async def search_etsy_keywords(niche: str) -> list[dict]:
    """Search for keyword and product opportunities within a specific niche."""
    queries = [
        f"etsy bestseller {niche} gifts",
        f"etsy trending {niche} 2026",
        f"print on demand {niche} products",
    ]
    results = []
    for q in queries:
        hits = await _search(q, num=6)
        for h in hits:
            h["niche"] = niche
        results.extend(hits)
    return results


async def search_competitor_products(niche: str) -> list[dict]:
    """Search for competitor products and popular items in a niche."""
    queries = [
        f"etsy {niche} t-shirt bestseller",
        f"etsy {niche} wall art popular",
    ]
    results = []
    for q in queries:
        hits = await _search(q, num=6)
        for h in hits:
            h["niche"] = niche
        results.extend(hits)
    return results


async def search_seasonal_trends() -> list[dict]:
    """Search for seasonal and current trend signals."""
    queries = [
        "etsy trending art prints 2026",
        "etsy bestseller dog mom gifts",
        "etsy top sellers summer 2026",
    ]
    results = []
    for q in queries:
        hits = await _search(q, num=8)
        results.extend(hits)
    return results


async def run_full_research() -> dict[str, list]:
    """
    Run all Heimdall core research queries.
    Returns categorised results ready for Claude scoring.
    """
    trending = await search_trending_niches()
    seasonal = await search_seasonal_trends()
    return {
        "trending": trending,
        "seasonal": seasonal,
    }
