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


# Etsy SEO rules:
# - Title: 140 chars max. Lead with highest-search keywords.
# - Tags: Exactly 13 tags, each <= 20 chars.
# - Description: First 160 chars are indexed most.

# Gift recipient personas matched to niche keywords
_GIFT_PERSONAS = {
    "cat": "cat lover", "dog": "dog lover", "pet": "pet owner",
    "coffee": "coffee lover", "wine": "wine lover", "beer": "beer lover",
    "fitness": "gym lover", "yoga": "yoga lover", "hiking": "hiker",
    "gaming": "gamer", "anime": "anime fan", "music": "music lover",
    "teacher": "teacher", "nurse": "nurse",
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
    combined = (niche + " " + " ".join(keywords)).lower()
    for key, persona in _GIFT_PERSONAS.items():
        if key in combined:
            return persona
    return niche.lower() + " lover"


def build_title(idea_title: str, niche: str, product_type: str = "t-shirt",
                keywords: list | None = None) -> str:
    keywords = keywords or []
    pt = product_type.lower().strip()
    persona = _get_persona(niche, keywords)

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
    tags = []
    pt = product_type.lower().strip()
    niche_lower = niche.lower().strip()

    pt_variants = _PRODUCT_SEARCH_TERMS.get(pt, [pt, f"{pt} gift", f"custom {pt}"])
    tags.extend(pt_variants[:2])

    tags.append(f"{niche_lower} {pt}"[:20])
    tags.append(f"{niche_lower} gift"[:20])
    tags.append(f"{niche_lower} lover"[:20])

    persona = _get_persona(niche, keywords)
    tags.append(f"gift for {persona}"[:20])
    tags.append(f"{persona} gift"[:20])

    for kw in keywords[:3]:
        kw_clean = kw.lower().strip()[:20]
        if kw_clean and kw_clean not in tags:
            tags.append(kw_clean)

    for occ in _OCCASIONS:
        if len(tags) >= 13:
            break
        occ_clean = occ[:20]
        if occ_clean not in tags:
            tags.append(occ_clean)

    seen = set()
    unique = []
    for t in tags:
        t = t[:20].strip()
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:13]


def build_description(
    title: str,
    niche: str,
    keywords: list,
    product_type: str = "t-shirt",
    price_usd: float = 0.0,
) -> str:
    pt = product_type.lower().strip()
    persona = _get_persona(niche, keywords)
    kw_str = ", ".join(keywords[:5]) if keywords else niche
    price_line = f"Price: ${price_usd:.2f}" if price_usd else ""

    desc = (
        f"{title} - the perfect {pt} for any {persona}.\n\n"
        f"A unique, print-on-demand {niche} design that makes a great gift "
        f"for birthdays, holidays, and every occasion.\n\n"
        f"Keywords: {kw_str}\n\n"
        f"✅ High-quality print-on-demand {pt}\n"
        f"✅ Ships directly to your door\n"
        f"✅ Makes a perfect gift for {persona}s\n"
        f"✅ Unique design - not sold in stores\n\n"
    )
    if price_line:
        desc += f"{price_line}\n\n"
    desc += (
        "Please allow 3-7 business days for production + shipping. "
        "Message us with any questions!"
    )
    return desc[:2000]


async def get_shop_stats() -> dict:
    """
    Fetch shop-level statistics from the Etsy v3 API.
    Used by _athena_loop in server.py every 5 minutes.

    Returns dict with keys:
      active_listings (int)
      total_orders    (int)
      today_revenue   (float)
      demo            (bool)
    """
    if not _has_credentials():
        return {
            "active_listings": 0,
            "total_orders": 0,
            "today_revenue": 0.0,
            "demo": True,
            "error": "credentials_missing",
        }

    shop_id = _shop_id()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{BASE_URL}/application/shops/{shop_id}",
                headers=_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                active = int(data.get("listing_active_count", 0))
                orders = int(data.get("transaction_sold_count", 0))
                # Etsy v3 doesn't surface today's revenue directly.
                # Use 0.0 as placeholder; real revenue is tracked via vault transactions.
                return {
                    "active_listings": active,
                    "total_orders": orders,
                    "today_revenue": 0.0,
                    "demo": False,
                }
            else:
                body = resp.text[:200]
                print(f"[ETSY] get_shop_stats {resp.status_code}: {body}")
                return {
                    "active_listings": 0,
                    "total_orders": 0,
                    "today_revenue": 0.0,
                    "demo": True,
                    "error": f"HTTP {resp.status_code}: {body}",
                }
    except Exception as e:
        print(f"[ETSY] get_shop_stats error: {type(e).__name__}: {e}")
        return {
            "active_listings": 0,
            "total_orders": 0,
            "today_revenue": 0.0,
            "demo": True,
            "error": str(e),
        }


async def get_recent_reviews(limit: int = 25) -> list:
    """
    Fetch recent shop reviews from the Etsy v3 API.
    Used by _review_monitor_loop in server.py every hour.

    Returns list of dicts with keys:
      listing_id    (str)
      listing_title (str)
      rating        (int 1-5)
      review        (str)
      buyer         (str)
      review_id     (str)
      product_type  (str)  always 'unknown' - Etsy API does not expose this
    """
    if not _has_credentials():
        return []

    shop_id = _shop_id()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{BASE_URL}/application/shops/{shop_id}/reviews",
                headers=_headers(),
                params={"limit": limit, "offset": 0},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                normalised = []
                for r in results:
                    normalised.append({
                        "listing_id":    str(r.get("listing_id", "")),
                        "listing_title": r.get("listing_title", "Unknown listing"),
                        "rating":        int(r.get("rating", 5)),
                        "review":        r.get("review", ""),
                        "buyer":         r.get("buyer_user_id", ""),
                        "review_id":     str(r.get("review_id", "")),
                        "product_type":  "unknown",
                    })
                return normalised
            else:
                body = resp.text[:200]
                print(f"[ETSY] get_recent_reviews {resp.status_code}: {body}")
                return []
    except Exception as e:
        print(f"[ETSY] get_recent_reviews error: {type(e).__name__}: {e}")
        return []


async def create_listing(
    title: str,
    description: str,
    tags: list,
    price_usd: float = 34.99,
    image_ids: list | None = None,
) -> dict:
    """
    Create an Etsy listing via OAuth token (LOKI).
    Falls back to demo mode when OAuth token is not present.
    Returns {"listing_id": str, "url": str, "demo": bool}.
    """
    if not _can_write():
        import uuid as _uuid
        fake_id = str(_uuid.uuid4().int)[:9]
        return {
            "listing_id": fake_id,
            "url": f"https://www.etsy.com/listing/{fake_id}",
            "demo": True,
            "title_b": None,
        }

    shop_id = _shop_id()
    payload = {
        "title": title[:140],
        "description": description[:2000],
        "price": round(price_usd, 2),
        "quantity": 999,
        "who_made": "i_did",
        "when_made": "made_to_order",
        "is_supply": False,
        "state": "active",
        "taxonomy_id": 116,
        "tags": [t[:20] for t in tags[:13]],
        "materials": ["cotton"],
        "should_auto_renew": True,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/application/shops/{shop_id}/listings",
                headers=_headers(write=True),
                json=payload,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                listing_id = str(data.get("listing_id", ""))
                url = data.get("url", f"https://www.etsy.com/listing/{listing_id}")
                return {"listing_id": listing_id, "url": url, "demo": False}
            else:
                body = resp.text[:300]
                print(f"[ETSY] create_listing {resp.status_code}: {body}")
                import uuid as _uuid
                fake_id = str(_uuid.uuid4().int)[:9]
                return {"listing_id": fake_id, "url": "", "demo": True,
                        "error": f"HTTP {resp.status_code}: {body}"}
    except Exception as e:
        print(f"[ETSY] create_listing error: {type(e).__name__}: {e}")
        import uuid as _uuid
        fake_id = str(_uuid.uuid4().int)[:9]
        return {"listing_id": fake_id, "url": "", "demo": True, "error": str(e)}
