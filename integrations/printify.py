from __future__ import annotations

import os
from pathlib import Path
import httpx


BASE_URL = "https://api.printify.com/v1"

# Blueprint IDs — Printify catalog (provider 99 = Printify Choice, auto-selects cheapest fulfiller).
#
# CONFIRMED WORKING (real products verified in live Printify store):
#   blueprint 6  + provider 99  → Gildan 5000 / Bella+Canvas T-Shirt  ✅
#   blueprint 92 + provider 99  → Hoodie (AWDIS or similar)            ✅
#
# UNCONFIRMED — use /api/debug/printify/catalog to verify.
# If a blueprint has no variants, _get_best_variants() falls back to CONFIRMED_FALLBACK
# (blueprint 6 t-shirt) so the pipeline always produces a real product, not an error.
BLUEPRINTS = {
    "t-shirt":    {"blueprint_id": 6,   "print_provider_id": 99},   # ✅ Confirmed working
    "hoodie":     {"blueprint_id": 92,  "print_provider_id": 99},   # ✅ Confirmed working
    "sweatshirt": {"blueprint_id": 92,  "print_provider_id": 99},   # Same as hoodie
    "mug":        {"blueprint_id": 462, "print_provider_id": 99},   # 11oz ceramic mug — verify via /catalog
    "tote bag":   {"blueprint_id": 532, "print_provider_id": 99},   # Canvas tote — verify via /catalog
    "poster":     {"blueprint_id": 446, "print_provider_id": 99},   # Premium matte poster — verify
    "wall art":   {"blueprint_id": 446, "print_provider_id": 99},   # Same as poster
    "phone case": {"blueprint_id": 5,   "print_provider_id": 99},   # Phone case — verify
    "sticker":    {"blueprint_id": 358, "print_provider_id": 99},   # Sticker sheet — verify
    "canvas":     {"blueprint_id": 242, "print_provider_id": 99},   # Canvas print — verify
}

# Guaranteed fallback when product-specific blueprint has no variants.
# Blueprint 6 (t-shirt) is confirmed to always have variants with provider 99.
CONFIRMED_FALLBACK = {"blueprint_id": 6, "print_provider_id": 99}

DEFAULT_BLUEPRINT = {"blueprint_id": 6, "print_provider_id": 99}

# In-process cache so we don't hammer the Printify catalog API on every call
_variant_cache: dict[str, list] = {}


def _headers() -> dict:
    # .strip() is critical — Railway env vars can have trailing newlines which
    # cause httpx to raise "Illegal header value" and silently kill all API calls
    return {
        "Authorization": f"Bearer {os.getenv('PRINTIFY_API_KEY', '').strip()}",
        "Content-Type": "application/json",
    }


def _shop_id() -> str:
    return os.getenv("PRINTIFY_SHOP_ID", "").strip()


def _has_credentials() -> bool:
    return bool(os.getenv("PRINTIFY_API_KEY", "").strip()) and bool(os.getenv("PRINTIFY_SHOP_ID", "").strip())


# Public base URL for this Railway deployment.
# Printify fetches images via URL — more reliable than base64 (which fails with error 10300).
_RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
_PUBLIC_BASE = (
    f"https://{_RAILWAY_PUBLIC_DOMAIN}"
    if _RAILWAY_PUBLIC_DOMAIN
    else "https://web-production-ed5a5.up.railway.app"
)


async def upload_image(image_url: str, filename: str = "design.png") -> dict:
    """Upload an image to Printify CDN.

    Handles both:
    - External URLs (http/https) → send URL directly to Printify
    - Local paths (/generated/...) → convert to public Railway URL so Printify fetches it.
      Using URL-based upload instead of base64 — base64 upload fails with Printify error 10300.

    Always returns a dict; never raises. On any failure, returns demo: True with an error key
    so pipeline.py can log the real reason instead of silently going demo.
    """
    if not _has_credentials():
        print("[PRINTIFY] upload_image: credentials not set (PRINTIFY_API_KEY or PRINTIFY_SHOP_ID missing)")
        return {"id": "demo_image_id", "preview_url": image_url, "demo": True, "error": "credentials_missing"}

    if image_url.startswith("/generated/"):
        # Build the public Railway URL so Printify can download the image directly.
        # This avoids the base64 "contents" field which Printify consistently rejects (error 10300).
        public_url = f"{_PUBLIC_BASE}{image_url}"
        print(f"[PRINTIFY] upload_image: converting local path to public URL: {public_url}")
        payload = {"file_name": filename, "url": public_url}
    else:
        payload = {"file_name": filename, "url": image_url}

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                f"{BASE_URL}/uploads/images.json",
                headers=_headers(),
                json=payload,
            )
            if resp.status_code not in (200, 201):
                body = resp.text[:400]
                print(f"[PRINTIFY] upload_image HTTP {resp.status_code}: {body}")
                return {"id": "demo_image_id", "preview_url": image_url, "demo": True,
                        "error": f"HTTP {resp.status_code}: {body}"}
            data = resp.json()
            img_id = data.get("id", "")
            if not img_id:
                print(f"[PRINTIFY] upload_image: no 'id' in response: {str(data)[:200]}")
                return {"id": "demo_image_id", "preview_url": image_url, "demo": True,
                        "error": "no_id_in_response"}
            print(f"[PRINTIFY] upload_image success: image_id={img_id}")
            return {"id": img_id, "preview_url": data.get("preview_url", image_url), "demo": False}
    except httpx.TimeoutException as e:
        print(f"[PRINTIFY] upload_image timeout after 90s: {e}")
        return {"id": "demo_image_id", "preview_url": image_url, "demo": True, "error": "timeout"}
    except Exception as e:
        print(f"[PRINTIFY] upload_image exception: {type(e).__name__}: {e}")
        return {"id": "demo_image_id", "preview_url": image_url, "demo": True, "error": str(e)}


async def _fetch_variants(blueprint_id: int, provider_id: int) -> list:
    """
    Fetch real variant IDs from Printify catalog API.
    Cached per-process to avoid repeated API calls.
    Returns list of variant dicts with 'id', 'title', 'is_available'.
    """
    cache_key = f"{blueprint_id}_{provider_id}"
    if cache_key in _variant_cache:
        return _variant_cache[cache_key]

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{BASE_URL}/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/variants.json",
                headers=_headers(),
            )
            if resp.status_code == 200:
                variants = resp.json().get("variants", [])
                available = [v for v in variants if v.get("is_available", True)]
                _variant_cache[cache_key] = available
                return available
    except Exception as e:
        print(f"[PRINTIFY] Variant fetch failed for blueprint {blueprint_id}: {e}")
    return []


async def _get_best_variants(blueprint_id: int, provider_id: int, max_variants: int = 5) -> list[int]:
    """
    Return up to max_variants IDs for the most popular sizes/colors.

    Fallback chain:
    1. Try requested blueprint + provider
    2. Try same blueprint with providers 29 (Monster Digital) and 3 (Printful)
    3. If still nothing, fall back to CONFIRMED_FALLBACK (blueprint 6 t-shirt + provider 99)
       so the pipeline always creates a real product instead of returning demo_novaria.
    """
    variants = await _fetch_variants(blueprint_id, provider_id)

    # Try alternative providers for the SAME blueprint before giving up
    if not variants and blueprint_id != CONFIRMED_FALLBACK["blueprint_id"]:
        for fallback_provider in [29, 3, 75]:
            variants = await _fetch_variants(blueprint_id, fallback_provider)
            if variants:
                print(f"[PRINTIFY] Blueprint {blueprint_id}: no variants for provider {provider_id}, using provider {fallback_provider}")
                break
    # Last resort: fall back to confirmed t-shirt blueprint so we always
    # return a real product instead of an empty list.
    if not variants:
        variants = await _fetch_variants(
            CONFIRMED_FALLBACK["blueprint_id"],
            CONFIRMED_FALLBACK["print_provider_id"],
        )
        if variants:
            print(f"[PRINTIFY] Falling back to confirmed blueprint {CONFIRMED_FALLBACK['blueprint_id']} (t-shirt)")

    if not variants:
        return []

    # Pick popular sizes/colors: S, M, L, XL in black or white first
    priority_keywords = ["black", "white", "navy", " s ", " m ", " l ", " xl "]
    scored = []
    for v in variants:
        t = (v.get("title") or "").lower()
        score = sum(1 for kw in priority_keywords if kw in f" {t} ")
        scored.append((score, v["id"]))
    scored.sort(key=lambda x: -x[0])
    return [vid for _, vid in scored[:max_variants]] or [v["id"] for v in variants[:max_variants]]


# Public alias used by server.py debug endpoints
PRINTIFY_BASE = BASE_URL


def printify_available() -> bool:
    return _has_credentials()


async def create_product(
    title: str,
    description: str,
    image_id: str,
    product_type: str = "t-shirt",
    price_cents: int = 3499,
) -> dict:
    """
    Create a Printify product with variants and print areas.
    Returns {"id": product_id, "demo": bool}.
    Falls back gracefully when credentials are missing or blueprint has no variants.
    """
    if not _has_credentials():
        return {"id": f"demo_{image_id[:8]}", "demo": True}

    bp = BLUEPRINTS.get(product_type.lower().strip(), DEFAULT_BLUEPRINT)
    blueprint_id   = bp["blueprint_id"]
    provider_id    = bp["print_provider_id"]

    variant_ids = await _get_best_variants(blueprint_id, provider_id, max_variants=5)
    if not variant_ids:
        print(f"[PRINTIFY] No variants found for blueprint {blueprint_id} — using demo product")
        return {"id": f"demo_{image_id[:8]}", "demo": True}

    variants = [
        {"id": vid, "price": price_cents, "is_enabled": True}
        for vid in variant_ids
    ]

    # Standard front print area placement id — works for most products
    print_areas = [
        {
            "variant_ids": variant_ids,
            "placeholders": [
                {
                    "position": "front",
                    "images": [
                        {
                            "id": image_id,
                            "x": 0.5,
                            "y": 0.5,
                            "scale": 1.0,
                            "angle": 0,
                        }
                    ],
                }
            ],
        }
    ]

    payload = {
        "title": title[:140],
        "description": description[:2000],
        "blueprint_id": blueprint_id,
        "print_provider_id": provider_id,
        "variants": variants,
        "print_areas": print_areas,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE_URL}/shops/{_shop_id()}/products.json",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            product_id = data.get("id") or data.get("data", {}).get("id", "")
            if not product_id:
                print(f"[PRINTIFY] Unexpected response shape: {str(data)[:200]}")
                return {"id": f"demo_{image_id[:8]}", "demo": True}
            print(f"[PRINTIFY] Product created: {product_id}")
            return {"id": str(product_id), "demo": False}
    except httpx.HTTPStatusError as e:
        print(f"[PRINTIFY] create_product HTTP {e.response.status_code}: {e.response.text[:300]}")
        return {"id": f"demo_{image_id[:8]}", "demo": True}
    except Exception as e:
        print(f"[PRINTIFY] create_product error: {type(e).__name__}: {e}")
        return {"id": f"demo_{image_id[:8]}", "demo": True}


async def publish_product(product_id: str) -> dict:
    """
    Push a Printify product to all connected sales channels (Etsy shop).
    Must be called after create_product to make the listing visible.
    """
    if not _has_credentials() or product_id.startswith("demo_"):
        return {"success": False, "demo": True}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/shops/{_shop_id()}/products/{product_id}/publishing_succeeded.json",
                headers=_headers(),
                json={
                    "title": True,
                    "description": True,
                    "images": True,
                    "variants": True,
                    "tags": True,
                    "keyFeatures": True,
                      "shipping_template": True,
                },
            )
            if resp.status_code in (200, 204):
                print(f"[PRINTIFY] Product {product_id} published to sales channels.")
                return {"success": True}
            print(f"[PRINTIFY] publish_product {resp.status_code}: {resp.text[:200]}")
            return {"success": False, "status": resp.status_code}
    except Exception as e:
        print(f"[PRINTIFY] publish_product error: {e}")
        return {"success": False, "error": str(e)}


async def generate_mockups(product_id: str, image_url: str = "") -> list[str]:
    """
    Fetch Printify-generated mockup images for a product.
    Returns list of image URLs. Falls back to [image_url] if product is demo or API fails.
    """
    if not _has_credentials() or product_id.startswith("demo_"):
        return [image_url] if image_url else []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/shops/{_shop_id()}/products/{product_id}.json",
                headers=_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                images = data.get("images", [])
                urls = [img["src"] for img in images if img.get("src")]
                if urls:
                    return urls
    except Exception as e:
        print(f"[PRINTIFY] generate_mockups error: {e}")
    return [image_url] if image_url else []
