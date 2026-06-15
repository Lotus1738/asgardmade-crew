import os
import httpx

BASE_URL = "https://openapi.etsy.com/v3"

LISTING_FEE = 0.20
TRANSACTION_FEE_RATE = 0.065


def _headers() -> dict:
    return {
        "x-api-key": os.getenv("ETSY_API_KEY", ""),
        "Content-Type": "application/json",
    }


def _shop_id() -> str:
    return os.getenv("ETSY_SHOP_ID", "")


def _has_credentials() -> bool:
    return bool(os.getenv("ETSY_API_KEY")) and bool(os.getenv("ETSY_SHOP_ID"))


def build_tags(niche: str, keywords: list[str]) -> list[str]:
    """Build up to 13 Etsy tags: niche anchor + keyword list."""
    base_tags = [niche.lower().strip()]
    cleaned = [k.lower().strip() for k in keywords if k.lower().strip() != niche.lower().strip()]
    combined = (base_tags + cleaned)[:13]
    return combined


def build_title(idea_title: str, niche: str) -> str:
    """Build an SEO-optimized Etsy title (max 140 chars)."""
    title = f"{idea_title} | {niche.title()} Gift | Unique Print on Demand Design"
    return title[:140]


def build_description(idea_title: str, niche: str, keywords: list[str]) -> str:
    kw_line = ", ".join(keywords[:8])
    return (
        f"{idea_title}\n\n"
        f"A unique {niche} design, perfect for anyone who loves {niche.lower()} aesthetics. "
        f"Printed on demand with high-quality materials.\n\n"
        f"❆ Perfect gift for: {kw_line}\n"
        f"❆ High-quality print on demand\n"
        f"❆ Ships within 3-5 business days\n\n"
        f"Questions? Message us — we respond within 24 hours."
    )


async def create_listing(
    title: str,
    description: str,
    tags: list[str],
    price_usd: float = 24.99,
    quantity: int = 999,
) -> dict:
    """Create an Etsy listing. Returns demo data if no credentials."""
    if not _has_credentials():
        import random
        listing_id = random.randint(1000000000, 9999999999)
        return {
            "listing_id": listing_id,
            "title": title,
            "price": price_usd,
            "url": f"https://www.etsy.com/listing/{listing_id}",
            "demo": True,
        }

    payload = {
        "quantity": quantity,
        "title": title,
        "description": description,
        "price": price_usd,
        "who_made": "i_did",
        "when_made": "made_to_order",
        "taxonomy_id": 1,
        "tags": tags[:13],
        "materials": ["polyester", "cotton"],
        "shipping_profile_id": None,
        "state": "active",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/application/shops/{_shop_id()}/listings",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "listing_id": data.get("listing_id"),
            "title": title,
            "price": price_usd,
            "url": data.get("url", ""),
            "demo": False,
        }


async def get_recent_reviews(min_rating: int = 1, max_rating: int = 2, limit: int = 25) -> list[dict]:
    """
    Fetch recent shop reviews with rating between min_rating and max_rating.
    Returns a list of review dicts. Falls back to empty list on error or missing creds.

    Each dict contains:
      review_id, listing_id, listing_title, rating, review, create_timestamp, reviewer
    """
    if not _has_credentials():
        return []

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/application/shops/{_shop_id()}/reviews",
                headers=_headers(),
                params={"limit": limit, "offset": 0},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            results = data.get("results", [])
            filtered = []
            for r in results:
                rating = r.get("rating", 5)
                if min_rating <= rating <= max_rating:
                    filtered.append({
                        "review_id": str(r.get("review_id", "")),
                        "listing_id": str(r.get("listing_id", "")),
                        "listing_title": r.get("title", "Unknown Listing"),
                        "rating": rating,
                        "review": r.get("review", ""),
                        "create_timestamp": r.get("create_timestamp", 0),
                        "reviewer": r.get("buyer_user_id", "anonymous"),
                    })
            return filtered
        except Exception:
            return []


async def get_shop_stats() -> dict:
    """Fetch basic shop performance stats."""
    if not _has_credentials():
        return {
            "active_listings": 0,
            "total_orders": 0,
            "today_revenue": 0.0,
            "demo": True,
        }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/application/shops/{_shop_id()}",
                headers=_headers(),
            )
            data = resp.json() if resp.status_code == 200 else {}
            return {
                "active_listings": data.get("listing_active_count", 0),
                "total_orders": data.get("transaction_sold_count", 0),
                "today_revenue": 0.0,
                "demo": False,
            }
        except Exception:
            return {"active_listings": 0, "total_orders": 0, "today_revenue": 0.0, "demo": True}
