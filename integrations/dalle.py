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


async def generate_design(idea_title: str, niche: str, product_type: str) -> dict:
    """Generate a DALL-E 3 design. Falls back to demo image if no API key."""
    global _demo_counter
    client = _get_client()

    if client is None:
        _demo_counter = (_demo_counter + 1) % len(DEMO_IMAGES)
        return {
            "url": DEMO_IMAGES[_demo_counter],
            "prompt": _build_prompt(idea_title, niche, product_type),
            "demo": True,
            "revised_prompt": None,
        }

    prompt = _build_prompt(idea_title, niche, product_type)
    response = await client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    return {
        "url": response.data[0].url,
        "prompt": prompt,
        "demo": False,
        "revised_prompt": response.data[0].revised_prompt,
    }


async def generate_variants(idea_title: str, niche: str, product_type: str, count: int = 2) -> list[dict]:
    tasks = [generate_design(idea_title, niche, product_type) for _ in range(count)]
    return await asyncio.gather(*tasks)
