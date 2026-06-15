import json
import os
import time
from pathlib import Path
import httpx

BASE_URL = "https://openapi.etsy.com/v3"

LISTING_FEE = 0.20
TRANSACTION_FEE_RATE = 0.065

_TOKENS_PATH = Path("data/etsy_tokens.json")


def _load_token() -> str:
    if _TOKENS_PATH.exists():
        try:
            data = json.loads(_TOKENS_PATH.read_text())
            token = data.get("access_token", "")
            if token:
                return token
        except Exception:
            pass
    return os.getenv("ETSY_OAUTH_TOKEN", "")


def _headers(write=False):
    raw_key = os.getenv("ETSY_API_KEY", "")
    h = {"x-api-key": raw_key, "Content-Type": "application/json"}
    if write:
        token = _load_token()
        if token:
            h["Authorization"] = "Bearer " + token
    return h


def _shop_id():
    return os.getenv("ETSY_SHOP_ID", "")


def _has_credentials():
    return bool(os.getenv("ETSY_API_KEY")) and bool(os.getenv("ETSY_SHOP_ID"))


def _can_write():
    return _has_credentials() and bool(_load_token())


def build_tags(niche, keywords):
    base_tags = [niche.lower().strip()]
    cleaned = [k.lower().strip() for k in keywords if k.lower().strip() != niche.lower().strip()]
    return (base_tags + cleaned)[:13]


def build_title(idea_title, niche):
    title = idea_title + " | " + niche.title() + " Gift | Unique Print on Demand Design"
    return title[:140]


def build_description(idea_title, niche, keywords):
    kw_line = ", ".join(keywords[:8])
    return (
        idea_title + "\n\n"
        "A unique " + niche + " design, perfect for anyone who loves " + niche.lower() + " aesthetics. "
        "Printed on demand with high-quality materials.\n\n"
        "Perfect gift for: " + kw_line + "\n"
        "High-quality print on demand\n"
        "Ships within 3-5 business days\n\n"
        "Questions? Message us - we respond within 24 hours."
    )


async def create_listing(title, description, tags, price_usd=24.99, quantity=999):
    if not _can_write():
        import random
        listing_id = random.randint(1000000000, 9999999999)
        return {"listing_id": listing_id, "title": title, "price": price_usd,
                "url": "https://www.etsy.com/listing/" + str(listing_id), "demo": True}

    payload = {
        "quantity": quantity, "title": title, "description": description,
        "price": price_usd, "who_made": "i_did", "when_made": "made_to_order",
        "taxonomy_id": 1, "tags": tags[:13], "materials": ["polyester", "cotton"],
        "shipping_profile_id": None, "state": "active",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            BASE_URL + "/application/shops/" + _shop_id() + "/listings",
            headers=_headers(write=True), json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"listing_id": data.get("listing_id"), "title": title,
                "price": price_usd, "url": data.get("url", ""), "demo": False}


async def get_recent_reviews(min_rating=1, max_rating=2, limit=25):
    if not _has_credentials():
        return []
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                BASE_URL + "/application/shops/" + _shop_id() + "/reviews",
                headers=_headers(), params={"limit": limit, "offset": 0},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            filtered = []
            for r in data.get("results", []):
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


async def get_shop_stats():
    if not _has_credentials():
        return {"active_listings": 0, "total_orders": 0, "today_revenue": 0.0, "demo": True}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                BASE_URL + "/application/shops/" + _shop_id(),
                headers=_headers(),
            )
            data = resp.json() if resp.status_code == 200 else {}
            return {"active_listings": data.get("listing_active_count", 0),
                    "total_orders": data.get("transaction_sold_count", 0),
                    "today_revenue": 0.0, "demo": False}
        except Exception:
            return {"active_listings": 0, "total_orders": 0, "today_revenue": 0.0, "demo": True}
