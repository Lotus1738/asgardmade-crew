import os
import asyncio
from openai import AsyncOpenAI

_client: AsyncOpenAI | None = None


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


async def generate_design(idea_title: str, niche: str, product_type: str) -> dict:
    """Generate a DALL-E 3 design. Falls back to demo image on any failure."""
    client = _get_client()

    if client is None:
        return _demo_fallback(idea_title, niche, product_type, "OPENAI_API_KEY not set")

    prompt = _build_prompt(idea_title, niche, product_type)
    try:
        response = await asyncio.wait_for(
            client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            ),
            timeout=60.0,
        )
        return {
            "url": response.data[0].url,
            "prompt": prompt,
            "demo": False,
            "revised_prompt": response.data[0].revised_prompt,
        }
    except asyncio.TimeoutError:
        return _demo_fallback(idea_title, niche, product_type, "OpenAI timeout (>60s)")
    except Exception as e:
        # Surface the real error: auth failure, quota, rate limit, network, etc.
        err_type = type(e).__name__
        err_msg = str(e)[:120]
        raise RuntimeError(f"{err_type}: {err_msg}") from e


async def generate_variants(idea_title: str, niche: str, product_type: str, count: int = 2) -> list[dict]:
    """Generate variants sequentially to avoid rate limits (DALL-E 3 = 1 img/min on free tier)."""
    results = []
    for i in range(count):
        if i > 0:
            await asyncio.sleep(2)  # small gap between requests
        result = await generate_design(idea_title, niche, product_type)
        results.append(result)
    return results
