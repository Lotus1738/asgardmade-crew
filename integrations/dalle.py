import os
import asyncio
import base64
import uuid
from pathlib import Path
from openai import AsyncOpenAI

_client: AsyncOpenAI | None = None

# Where generated images get saved so the server can serve them
GENERATED_DIR = Path(__file__).parent.parent / "public" / "generated"


def _get_client() -> AsyncOpenAI | None:
    global _client
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=key)
    return _client


DEMO_IMAGES = [
    "https://picsum.photos/seed/pod1/512/512",
    "https://picsum.photos/seed/pod2/512/512",
    "https://picsum.photos/seed/pod3/512/512",
    "https://picsum.photos/seed/pod4/512/512",
    "https://picsum.photos/seed/pod5/512/512",
    "https://picsum.photos/seed/pod6/512/512",
]

_demo_counter = 0


def _build_prompt(idea_title: str, niche: str, product_type: str) -> str:
    return (
        f"Flat vector illustration for a print-on-demand {product_type}. "
        f"Theme: {idea_title}. Style: clean, bold, minimalist. "
        f"Niche aesthetic: {niche}. "
        "White background, centered composition, high contrast, no text, "
        "suitable for DTG printing, professional quality."
    )


def _demo_fallback(idea_title: str, niche: str, product_type: str, reason: str) -> dict:
    global _demo_counter
    _demo_counter = (_demo_counter + 1) % len(DEMO_IMAGES)
    return {
        "url": DEMO_IMAGES[_demo_counter],
        "prompt": _build_prompt(idea_title, niche, product_type),
        "demo": True,
        "demo_reason": reason,
        "revised_prompt": None,
    }


def _save_b64_image(b64_data: str) -> str:
    """Save a base64 image to disk and return the public URL path."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    filepath = GENERATED_DIR / filename
    image_bytes = base64.b64decode(b64_data)
    filepath.write_bytes(image_bytes)
    return f"/generated/{filename}"


async def generate_design(idea_title: str, niche: str, product_type: str) -> dict:
    """Generate an image using gpt-image-1. Falls back to demo on any failure."""
    client = _get_client()

    if client is None:
        return _demo_fallback(idea_title, niche, product_type, "OPENAI_API_KEY not set")

    prompt = _build_prompt(idea_title, niche, product_type)
    try:
        response = await asyncio.wait_for(
            client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            ),
            timeout=90.0,
        )

        item = response.data[0]

        # gpt-image-1 returns b64_json by default; fall back to url if present
        if hasattr(item, "b64_json") and item.b64_json:
            image_url = _save_b64_image(item.b64_json)
        elif hasattr(item, "url") and item.url:
            image_url = item.url
        else:
            return _demo_fallback(idea_title, niche, product_type, "No image data in response")

        return {
            "url": image_url,
            "prompt": prompt,
            "demo": False,
            "revised_prompt": getattr(item, "revised_prompt", None),
        }

    except asyncio.TimeoutError:
        return _demo_fallback(idea_title, niche, product_type, "OpenAI timeout (>90s)")
    except Exception as e:
        err_type = type(e).__name__
        err_msg = str(e)[:120]
        raise RuntimeError(f"{err_type}: {err_msg}") from e


async def generate_variants(idea_title: str, niche: str, product_type: str, count: int = 2) -> list[dict]:
    """Generate variants sequentially to avoid rate limits."""
    results = []
    for i in range(count):
        if i > 0:
            await asyncio.sleep(3)
        result = await generate_design(idea_title, niche, product_type)
        results.append(result)
    return results
