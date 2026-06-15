from __future__ import annotations

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


"""
Etsy SEO rules (2024):
- Title: 140 chars max. Lead with highest-search keywords. Include product type,
  gift angle, recipient, occasion. No filler words at the start.
- Tags: Exactly 13 tags, each ≤20 chars. Multi-word tags outperform single words.
  Cover: product type, niche, recipient, occasion, style, use-case.
- Description: First 160 chars are indexed most. Lead with main keyword phrase.
  Use line breaks for readability. Hit every tag keyword naturally in the text.
"""

# Gift recipient personas matched to niche keywords
_GIFT_PERSONAS = {
    "cat": "cat lover", "dog": "dog lover", "pet": "pet owner",
    "coffee": "coffee lover", "wine": "wine lover", "beer": "beer lover",
    "fitness": "gym lover", "yoga": "yoga lover", "hiking": "hiker",
    "gaming": "gamer", "anime": "anime fan", "music": "music lover",
    "teacher": "teacher", "nurse": "nurse", "nurse": "nurse",
    "mom": "mom", "dad": "dad", "sister": "sister", "brother": "brother",
    "grandma": "grandma", "grandpa": "grandpa",
    "astrology": "astrology lover", "space": "space lover",
    "plant": "plant mom", "garden": "gardener",
    "ocean": "ocean lover", "beach": "beach lover",
    "book": "book lover", "reader": "bookworm",
}

_OCCASIONS = ["birthday gift", "christmas gift", "holiday gift",
               "mothers day gift", "fathers day gift", "graduation gift",
               "anniversary gift", "valentines day gift", "gift for her", "gift for him"]

_PRODUCT_SEARCH_TERMS = {
    "t-shirt": ["tee shirt", "graphic tee", "unisex tshirt"],
    "hoodie": ["hooded sweatshirt", "pullover hoodie", "cozy hoodie"],
    "mug": ["coffee mug", "ceramic mug", "11oz mug", "funny mug"],
    "tote bag": ["canvas tote", "reusable bag", "shopping tote"],
    "poster": ["wall art print", "art poster", "room decor print"],
    "wall art": ["wall art print", "home decor art", "printable wall art"],
    "phone case": ["phone cover", "iphone case", "samsung case"],
    "sticker": ["vinyl sticker", "laptop sticker", "waterproof sticker"],
    "sweatshirt": ["crewneck sweatshirt", "cozy sweatshirt"],
}


def _get_persona(niche: str, keywords: list) -> str:
    """Find best gift recipient persona for this niche."""
    combined = (niche + " " + " ".join(keywords)).lower()
    for key, persona in _GIFT_PERSONAS.items():
        if key in combined:
            return persona
    return niche.lower() + " lover"


def build_title(idea_title: str, niche: str, product_type: str = "t-shirt",
                keywords: list | None = None) -> str:
    """
    Build a keyword-optimized Etsy title.
    Structure: [Main keyword phrase], [Product type] [Gift angle] - [Niche] [Occasion]
    Leads with highest-searched terms, 140 char max.
    """
    keywords = keywords or []
    pt = product_type.lower().strip()
    persona = _get_persona(niche, keywords)
    occasion = "Gift"

    # Build keyword-leading title
    # Pattern: "{title} {product_type} | {niche} gift | {occasion} for {persona}"
    core = f"{idea_title} {pt.title()}"
    gift_angle = f"{niche.title()} Gift | {persona.title()}"
    occasions_str = " | Birthday Christmas Holiday"

    title = f"{core} | {gift_angle}{occasions_str}"
    if len(title) > 140:
        title = f"{core} | {gift_angle}"
    if len(title) > 140:
        title = f"{idea_title} | {niche.title()} {pt.title()} Gift"
    return title[:140]


def build_tags(niche: str, keywords: list, product_type: str = "t-shirt") -> list:
    """
    Build 13 high-value Etsy tags.
    Strategy: product type variants + niche multi-word + gift angles + occasions.
    Each tag ≤20 chars. Multi-word = broader match = more impressions.
    """
    tags = []
    pt = product_type.lower().strip()
    niche_lower = niche.lower().strip()

    # 1. Product type variants (2-3 tags)
    pt_variants = _PRODUCT_SEARCH_TERMS.get(pt, [pt, f"{pt} gift", f"custom {pt}"])
    tags.extend(pt_variants[:2])

    # 2. Niche + product combos (2 tags)
    tags.append(f"{niche_lower} {pt}"[:20])
    tags.append(f"{niche_lower} gift"[:20])

    # 3. Gift persona tag (1 tag)
    persona = _get_persona(niche, keywords)
    tags.append(f"{persona} gift"[:20])

    # 4. Occasion tags (2 tags)
    tags.append("birthday gift")
    tags.append("christmas gift")

    # 5. Keywords from idea (fill remaining slots up to 13)
    for kw in keywords:
        kw_clean = kw.lower().strip()[:20]
        if kw_clean and kw_clean not in tags and len(tags) < 13:
            tags.append(kw_clean)

    # 6. Fill with niche-adjacent tags if still under 13
    fillers = ["unique gift idea", "gift for her", "gift for him",
               "novelty gift", f"{niche_lower} lover"[:20], "funny gift",
               "cute gift", "trendy gift"]
    for f in fillers:
        if len(tags) >= 13:
            break
        if f[:20] not in tags:
            tags.append(f[:20])

    return tags[:13]


def build_description(idea_title: str, niche: str, keywords: list,
                      product_type: str = "t-shirt", price_usd: float = 24.99) -> str:
    """
    Build an SEO-rich Etsy description.
    First 160 chars indexed most heavily — lead with main keyword phrase.
    Include all tag keywords naturally. Format for Etsy's mobile-first audience.
    """
    keywords = keywords or []
    pt = product_type.lower()
    persona = _get_persona(niche, keywords)
    kw_list = ", ".join(k.lower() for k in keywords[:6]) if keywords else niche.lower()

    # First 160 chars are the Etsy SEO goldmine
    first_line = (
        f"✨ {idea_title} — {niche.title()} {pt.title()} | Perfect {persona.title()} gift!\n\n"
    )

    body = (
        f"Looking for the perfect {niche.lower()} gift? This {pt} features a bold, "
        f"one-of-a-kind design that {persona}s absolutely love. "
        f"Whether it's a birthday, Christmas, holiday, or 'just because' gift — "
        f"this {pt} delivers every time.\n\n"
        f"⭐ WHAT YOU'LL LOVE:\n"
        f"• Unique {niche.lower()} design — not sold in stores\n"
        f"• Premium print quality — vibrant colors that last\n"
        f"• Printed on demand — made fresh just for you\n"
        f"• Makes the perfect gift for: {kw_list}\n\n"
        f"📦 SHIPPING:\n"
        f"• Production: 2-5 business days\n"
        f"• Delivery: 5-10 business days (US)\n"
        f"• Ships worldwide\n\n"
        f"💬 QUESTIONS? Message us — we respond within 24 hours.\n\n"
        f"🔍 Also search: {niche.lower()} {pt}, {persona} gift, "
        f"{niche.lower()} lover gift, funny {niche.lower()} {pt}, "
        f"cute {niche.lower()} gift, {pt} for {persona}"
    )

    return (first_line + body)[:4000]


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
