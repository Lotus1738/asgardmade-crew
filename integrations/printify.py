from __future__ import annotations

import os
import base64
from pathlib import Path
import httpx


BASE_URL = "https://api.printify.com/v1"

# Blueprint IDs — verified popular providers (Printify catalog as of 2024-2025)
# print_provider_id 99 = Printify Choice (aggregated best-price fulfillment)
# print_provider_id 29 = FYBY (t-shirts, reliable US fulfillment)
# These are the most commonly available — we fetch real variant IDs at runtime.
BLUEPRINTS = {
    "t-shirt":    {"blueprint_id": 6,   "print_provider_id": 99},
    "hoodie":     {"blueprint_id": 92,  "print_provider_id": 99},
    "mug":        {"blueprint_id": 68,  "print_provider_id": 99},
    "tote bag":   {"blueprint_id": 77,  "print_provider_id": 99},
    "poster":     {"blueprint_id": 45,  "print_provider_id": 99},
    "wall art":   {"blueprint_id": 45,  "print_provider_id": 99},
    "sticker":    {"blueprint_id": 358, "print_provider_id": 99},
    "phone case": {"blueprint_id": 5,   "print_provider_id": 99},
    "sweatshirt": {"blueprint_id": 92,  "print_provider_id": 99},
}

DEFAULT_BLUEPRINT = {"blueprint_id": 6, "print_provider_id": 99}

# In-process cache so we don't hammer the Printify catalog API on every call
_variant_cache: dict[str, list] = {}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.getenv('PRINTIFY_API_KEY', '')}",
        "Content-Type": "application/json",
    }


def _shop_id() -> str:
    return os.getenv("PRINTIFY_SHOP_ID", "")


def _has_credentials() -> bool:
    return bool(os.getenv("PRINTIFY_API_KEY")) and bool(os.getenv("PRINTIFY_SHOP_ID"))


async def upload_image(image_url: str, filename: str = "design.png") -> dict:
    """Upload an image to Printify CDN.

    Handles both:
    - External URLs (http/https) → send URL directly to Printify
    - Local paths (/generated/...) → read from disk, send as base64
      (gpt-image-1 saves to public/generated/ and returns a local path)
    """
    if not _has_credentials():
        return {"id": "demo_image_id", "preview_url": image_url, "demo": True}

    # Detect local file path (gpt-image-1 returns /generated/filename.jpg)
    # Check data/generated/ first (Railway volume — persists across redeploys)
    # Fall back to public/generated/ for legacy compatibility
    if image_url.startswith("/generated/"):
        local_path = Path("data") / image_url.lstrip("/")
        if not local_path.exists():
            local_path = Path("public") / image_url.lstrip("/")
        if local_path.exists():
            img_bytes = local_path.read_bytes()
            b64_contents = base64.b64encode(img_bytes).decode("utf-8")
            payload = {"file_name": filename, "contents": b64_contents}
        else:
            raise FileNotFoundError(f"Generated image not found: {local_path} (checked data/ and public/)")
    else:
        payload = {"file_name": filename, "url": image_url}

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{BASE_URL}/uploads/images.json",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"id": data["id"], "preview_url": data.get("preview_url", image_url), "demo": False}


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
    Falls back to trying alternative popular print providers if primary fails.
    """
    variants = await _fetch_variants(blueprint_id, provider_id)

    # If primary provider has no variants, try provider 29 (FYBY) then 3 (Printful)
    if not variants:
        for fallback_provider in [29, 3, 75]:
            variants = await _fetch_variants(blueprint_id, fallback_provider)
            if variants:
                break

    if not variants:
        return []

    # Prefer mid-range sizes (M/L/XL) and neutral colors (black, white, navy)
    preferred_keywords = ["medium", " m ", "large", " l ", "black", "white", "navy", "unisex"]
    preferred = []
    rest = []
    for v in variants:
        vtitle = (v.get("title", "") + " " + v.get("options", {}).get("color", "")).lower()
        if any(kw in vtitle for kw in preferred_keywords):
            preferred.append(v["id"])
        else:
            rest.append(v["id"])

    # Return up to max_variants — preferred sizes first
    selected = (preferred + rest)[:max_variants]
    return selected if selected else [variants[0]["id"]]


async def create_product(
    title: str,
    description: str,
    image_id: str,
    product_type: str = "t-shirt",
    price_cents: int = 2499,
) -> dict:
    """
    Create a product on Printify with real variant IDs fetched from the catalog.
    This replaces the old hardcoded variant_id=17887 approach that was silently failing.
    """
    if not _has_credentials():
        return {
            "id": f"demo_product_{hash(title) % 100000:05d}",
            "title": title,
            "demo": True,
        }

    bp = BLUEPRINTS.get(product_type.lower().strip(), DEFAULT_BLUEPRINT)
    blueprint_id = bp["blueprint_id"]
    provider_id = bp["print_provider_id"]

    # Fetch real variant IDs — don't hardcode them
    variant_ids = await _get_best_variants(blueprint_id, provider_id)
    if not variant_ids:
        print(f"[PRINTIFY] No variants found for blueprint {blueprint_id}, provider {provider_id}")
        return {
            "id": f"demo_novariants_{hash(title) % 100000:05d}",
            "title": title,
            "demo": True,
            "error": "No variants available",
        }

    variants_payload = [
        {"id": vid, "price": price_cents, "is_enabled": True}
        for vid in variant_ids
    ]

    payload = {
        "title": title,
        "description": description,
        "blueprint_id": blueprint_id,
        "print_provider_id": provider_id,
        "variants": variants_payload,
        "print_areas": [
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
        ],
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/shops/{_shop_id()}/products.json",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            print(f"[PRINTIFY] Product created: {data.get('id')} — {title}")
            return {"id": data["id"], "title": title, "demo": False}
        except httpx.HTTPStatusError as e:
            error_body = e.response.text[:500]
            print(f"[PRINTIFY] Product creation failed ({e.response.status_code}): {error_body}")
            return {
                "id": f"demo_error_{hash(title) % 100000:05d}",
                "title": title,
                "demo": True,
                "error": error_body,
            }


async def generate_mockups(
    product_id: str,
    blueprint_id: int = 0,
    image_url: str = "",
) -> list[str]:
    """
    Fetch Printify-generated mockup image URLs for an existing product.

    Printify auto-generates product mockups after a product is created.
    This retrieves them by GETting the product and extracting the images array.

    Args:
        product_id:   Printify product ID (returned by create_product).
        blueprint_id: Unused — kept for API symmetry / future use.
        image_url:    Fallback URL if no mockups can be fetched.

    Returns:
        List of public mockup image URLs. Falls back to [image_url] on error.
    """
    if not _has_credentials() or product_id.startswith("demo_"):
        return [image_url] if image_url else []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/shops/{_shop_id()}/products/{product_id}.json",
                headers=_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            images = data.get("images", [])
            urls = [img["src"] for img in images if img.get("src")]
            return urls if urls else ([image_url] if image_url else [])
    except Exception as e:
        print(f"[PRINTIFY MOCKUPS] Failed to fetch mockups for {product_id}: {type(e).__name__}: {e}")
        return [image_url] if image_url else []


async def publish_product(product_id: str) -> bool:
    """Publish a Printify product to the connected Etsy shop."""
    if not _has_credentials() or product_id.startswith("demo_"):
        return True

    payload = {
        "title": True,
        "description": True,
        "images": True,
        "variants": True,
        "tags": True,
        "keyFeatures": True,
        "shipping_template": True,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/shops/{_shop_id()}/products/{product_id}/publish.json",
            headers=_headers(),
            json=payload,
        )
        return resp.status_code in (200, 204)


def printify_available() -> bool:
    """Returns True if Printify API key and shop ID are configured."""
    return _has_credentials()
