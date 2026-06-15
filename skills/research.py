"""
Research skill pack — web research, trend analysis, competitor research, niche discovery.
"""

import asyncio
import httpx
from datetime import datetime
from skills import SkillMeta, SkillResult, register


# ─── Web Search ──────────────────────────────────────────────────────────────

async def _web_search(args: dict) -> SkillResult:
    """Search the web using DuckDuckGo and return top results."""
    query = args.get("query", "")
    limit = int(args.get("limit", 5))
    if not query:
        return SkillResult(success=False, output=None, error="query is required")
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=limit):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")[:300],
                })
        if not results:
            return SkillResult(success=False, output=[], error="No results found", summary="0 results")
        summary = f"Found {len(results)} results for '{query}'"
        return SkillResult(success=True, output=results, summary=summary)
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))


# ─── Trend Research ──────────────────────────────────────────────────────────

async def _trend_research(args: dict) -> SkillResult:
    """Research trending topics in a niche using multiple search angles."""
    niche = args.get("niche", "")
    if not niche:
        return SkillResult(success=False, output=None, error="niche is required")

    queries = [
        f"{niche} trending 2025 etsy",
        f"{niche} best selling print on demand",
        f"{niche} gift ideas popular",
    ]

    all_results = []
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for q in queries:
                for r in ddgs.text(q, max_results=3):
                    all_results.append({
                        "query": q,
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")[:200],
                    })
                await asyncio.sleep(0.3)
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))

    return SkillResult(
        success=True,
        output=all_results,
        summary=f"Researched {len(all_results)} trend signals for '{niche}'",
        metadata={"niche": niche, "queries": queries},
    )


# ─── Competitor Analysis ─────────────────────────────────────────────────────

async def _competitor_analysis(args: dict) -> SkillResult:
    """Analyze Etsy competitors for a niche/product type."""
    niche = args.get("niche", "")
    product = args.get("product_type", "t-shirt")
    if not niche:
        return SkillResult(success=False, output=None, error="niche is required")

    queries = [
        f"site:etsy.com {niche} {product} best seller",
        f"etsy {niche} {product} high sales reviews",
        f"{niche} {product} etsy shop popular listings",
    ]

    results = []
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for q in queries:
                for r in ddgs.text(q, max_results=4):
                    title = r.get("title", "")
                    url = r.get("href", "")
                    snippet = r.get("body", "")[:300]
                    # Extract price if visible in snippet
                    price = None
                    import re
                    price_match = re.search(r'\$(\d+\.?\d*)', snippet)
                    if price_match:
                        price = float(price_match.group(1))
                    results.append({
                        "title": title, "url": url, "snippet": snippet,
                        "price": price, "query": q,
                    })
                await asyncio.sleep(0.4)
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))

    prices = [r["price"] for r in results if r.get("price")]
    avg_price = round(sum(prices) / len(prices), 2) if prices else None

    return SkillResult(
        success=True,
        output={
            "results": results,
            "avg_competitor_price": avg_price,
            "total_found": len(results),
        },
        summary=f"Found {len(results)} competitor listings for {niche} {product}" +
                (f" — avg price ${avg_price}" if avg_price else ""),
        metadata={"niche": niche, "product_type": product},
    )


# ─── Niche Discovery ─────────────────────────────────────────────────────────

async def _niche_discovery(args: dict) -> SkillResult:
    """Discover untapped niches for print on demand."""
    category = args.get("category", "aesthetic")
    exclude = args.get("exclude", [])

    seed_queries = [
        f"trending {category} niche print on demand 2025",
        f"underserved {category} market etsy 2025",
        f"new {category} subculture gift ideas",
        f"emerging {category} community products",
    ]

    raw_results = []
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for q in seed_queries:
                for r in ddgs.text(q, max_results=3):
                    raw_results.append({
                        "title": r.get("title", ""),
                        "snippet": r.get("body", "")[:250],
                        "source": q,
                    })
                await asyncio.sleep(0.3)
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))

    return SkillResult(
        success=True,
        output=raw_results,
        summary=f"Discovered {len(raw_results)} niche signals in '{category}' category",
        metadata={"category": category, "queries_run": len(seed_queries)},
    )


# ─── URL Fetch ───────────────────────────────────────────────────────────────

async def _fetch_url(args: dict) -> SkillResult:
    """Fetch and extract text content from a URL."""
    url = args.get("url", "")
    if not url:
        return SkillResult(success=False, output=None, error="url is required")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            text = resp.text
            # Basic HTML stripping
            import re
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return SkillResult(
                success=True,
                output=text[:3000],
                summary=f"Fetched {len(text)} chars from {url}",
                metadata={"url": url, "status": resp.status_code},
            )
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))


# ─── Keyword Research ────────────────────────────────────────────────────────

async def _keyword_research(args: dict) -> SkillResult:
    """Generate keyword variations and search volume signals for a topic."""
    topic = args.get("topic", "")
    if not topic:
        return SkillResult(success=False, output=None, error="topic is required")

    # Generate keyword variations
    variations = [
        topic,
        f"{topic} gift",
        f"{topic} shirt",
        f"{topic} mug",
        f"funny {topic}",
        f"cute {topic}",
        f"{topic} lover",
        f"{topic} aesthetic",
        f"{topic} decor",
        f"personalized {topic}",
    ]

    results = []
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for kw in variations[:6]:
                suggestions = list(ddgs.suggestions(kw))[:5]
                results.append({
                    "keyword": kw,
                    "suggestions": [s.get("phrase", "") for s in suggestions],
                })
                await asyncio.sleep(0.2)
    except Exception as e:
        return SkillResult(success=False, output={"variations": variations}, error=str(e))

    return SkillResult(
        success=True,
        output={"keywords": results, "seed_variations": variations},
        summary=f"Generated {len(results)} keyword clusters for '{topic}'",
    )


# ─── Register all ────────────────────────────────────────────────────────────

def register_all():
    register(SkillMeta(
        name="web_search",
        description="Search the web using DuckDuckGo and return top results",
        pack="research",
        fn=_web_search,
        args_schema={"query": "Search query string", "limit": "Max results (default 5)"},
        tags=["search", "web", "research"],
        icon="🔍",
    ))
    register(SkillMeta(
        name="trend_research",
        description="Research trending topics and signals for a specific niche",
        pack="research",
        fn=_trend_research,
        args_schema={"niche": "The niche to research (e.g. 'cottagecore', 'fishing')"},
        tags=["trends", "niche", "etsy"],
        icon="📈",
    ))
    register(SkillMeta(
        name="competitor_analysis",
        description="Analyze Etsy competitor listings for a niche and product type",
        pack="research",
        fn=_competitor_analysis,
        args_schema={"niche": "Target niche", "product_type": "Product type (default: t-shirt)"},
        tags=["competitors", "etsy", "pricing"],
        icon="🔎",
    ))
    register(SkillMeta(
        name="niche_discovery",
        description="Discover underserved niches and emerging communities for POD",
        pack="research",
        fn=_niche_discovery,
        args_schema={"category": "Broad category (e.g. 'aesthetic', 'hobby', 'profession')",
                     "exclude": "List of niches to exclude"},
        tags=["discovery", "niche", "market"],
        icon="🗺",
    ))
    register(SkillMeta(
        name="fetch_url",
        description="Fetch and extract text content from any URL",
        pack="research",
        fn=_fetch_url,
        args_schema={"url": "URL to fetch"},
        tags=["web", "scrape", "content"],
        icon="🌐",
    ))
    register(SkillMeta(
        name="keyword_research",
        description="Generate keyword variations and search suggestions for a topic",
        pack="research",
        fn=_keyword_research,
        args_schema={"topic": "Topic or niche to research keywords for"},
        tags=["keywords", "seo", "etsy"],
        icon="🏷",
    ))
