import os
import base64
from pathlib import Path
import httpx


BASE_URL = "https://api.printify.com/v1"

# Blueprint IDs for common POD products
BLUEPRINTS = {
    "t-shirt": {"blueprint_id": 6, "print_provider_id": 99},
    "hoodie": {"blueprint_id": 92, "print_provider_id": 99},
    "mug": {"blueprint_id": 68, "print_provider_id": 99},
    "tote bag": {"blueprint_id": 77, "print_provider_id": 99},
    "poster": {"blueprint_id": 45, "print_provider_id": 99},
    "sticker": {"blueprint_id": 358, "print_provider_id": 99},
    "phone case": {"blueprint_id": 5, "print_provider_id": 99},
}

DEFAULT_BLUEPRINT = {"blueprint_id": 6, "print_provider_id": 99}


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

    # Detect local file path (gpt-image-1 returns /generated/filename.png)
    if image_url.startswith("/generated/"):
        local_path = Path("public") / image_url.lstrip("/")
        if local_path.exists():
            img_bytes = local_path.read_bytes()
            b64_contents = base64.b64encode(img_bytes).decode("utf-8")
            payload = {"file_name": filename, "contents": b64_contents}
        else:
            raise FileNotFoundError(f"Generated image not found: {local_path}")
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


async def create_product(
    title: str,
    description: str,
    image_id: str,
    product_type: str = "t-shirt",
    price_cents: int = 2499,
) -> dict:
    """Create a product on Printify."""
    if not _has_credentials():
        return {
            "id": f"demo_product_{hash(title) % 100000:05d}",
            "title": title,
            "demo": True,
        }

    bp = BLUEPRINTS.get(product_type.lower(), DEFAULT_BLUEPRINT)

    payload = {
        "title": title,
        "description": description,
        "blueprint_id": bp["blueprint_id"],
        "print_provider_id": bp["print_provider_id"],
        "variants": [
            {
                "id": 17887,
                "price": price_cents,
                "is_enabled": True,
            }
        ],
        "print_areas": [
            {
                "variant_ids": [17887],
                "placeholders": [
                    {
                        "position": "front",
                        "images": [
                            {
                                "id": image_id,
                                "x": 0.5,
                                "y": 0.5,
                                "scale": 1,
                                "angle": 0,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{BASE_URL}/shops/{_shop_id()}/products.json",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"id": data["id"], "title": title, "demo": False}


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
