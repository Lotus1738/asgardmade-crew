import os
import asyncio

try:
    import higgsfield_client as _hf_sdk
    _SDK_AVAILABLE = True
except ImportError:
    _hf_sdk = None
    _SDK_AVAILABLE = False

DEMO_IMAGES = [
    "https://picsum.photos/seed/hf1/512/512",
    "https://picsum.photos/seed/hf2/512/512",
    "https://picsum.photos/seed/hf3/512/512",
    "https://picsum.photos/seed/hf4/512/512",
    "https://picsum.photos/seed/hf5/512/512",
    "https://picsum.photos/seed/hf6/512/512",
]

_demo_counter = 0

_CHARACTER_NICHES = {
    "cottagecore", "coquette", "dark academia", "witchy", "witch",
    "kawaii", "aesthetic", "lifestyle", "boho", "vintage", "nature",
    "fairy", "fairycore", "goblincore", "celestial", "mushroom",
    "botanical", "floral", "animal", "pet", "cat", "dog", "frog",
}

_PRECISION_NICHES = {
    "minimalist", "minimal", "line art", "lineart", "retro gaming",
    "retrogaming", "pixel art", "pixelart", "typography", "type",
    "geometric", "vector", "abstract", "monochrome",
}


def _model_for_niche(niche: str) -> str:
    niche_lower = niche.lower()
    if any(kw in niche_lower for kw in _CHARACTER_NICHES):
        return "higgsfield-ai/soul/standard"
    if any(kw in niche_lower for kw in _PRECISION_NICHES):
        return "higgsfield-ai/nano-banana-pro"
    return "bytedance/seedream/v4/text-to-image"


def _build_prompt(idea_title: str, niche: str, product_type: str) -> str:
    niche_lower = niche.lower()

    # Style per niche type
    if any(kw in niche_lower for kw in _PRECISION_NICHES):
        style = "clean line art, bold minimalist digital art"
        camera_sim = (
            "Shot on full-frame digital camera, 85mm lens, studio lighting. "
            "NOT photorealistic, NOT complex backgrounds, NOT cluttered. "
            "Subject occupies 60% of frame, rigid 1:1 canvas."
        )
    elif any(kw in niche_lower for kw in _CHARACTER_NICHES):
        style = "flat vector illustration, bold clean digital art"
        camera_sim = ""
    else:
        style = "flat vector illustration, minimalist digital art"
        camera_sim = ""

    prompt = (
        f"Subject: {idea_title}, specific and unambiguous. "
        f"Composition: square 1:1, centered subject, generous padding, macro detail. "
        f"Style: {style}. "
        f"Background: pure white #FFFFFF, mandatory for POD printing. "
        f"Constraints: no shadows, no gradients, no complex backgrounds, "
        f"no photorealism, no text unless requested. "
        f"Niche: {niche}. "
    )
    if camera_sim:
        prompt += camera_sim + " "
    prompt += f"2K resolution, 300dpi, crisp edges, print-ready for {product_type}."
    return prompt


def _demo_fallback(idea_title: str, niche: str, product_type: str, reason: str) -> dict:
    global _demo_counter
    _demo_counter = (_demo_counter + 1) % len(DEMO_IMAGES)
    return {
        "url": DEMO_IMAGES[_demo_counter],
        "prompt": _build_prompt(idea_title, niche, product_type),
        "demo": True,
        "demo_reason": reason,
        "revised_prompt": None,
        "model": "demo",
    }


def _parse_hf_key() -> tuple[str, str] | tuple[None, None]:
    hf_key = os.getenv("HF_KEY", "")
    if not hf_key or ":" not in hf_key:
        return None, None
    parts = hf_key.split(":", 1)
    return parts[0].strip(), parts[1].strip()


def _call_sdk(model: str, prompt: str, api_key: str, api_secret: str) -> dict:
    """Synchronous SDK call — run inside asyncio.to_thread."""
    result = _hf_sdk.subscribe(
        model,
        arguments={"prompt": prompt, "aspect_ratio": "1:1", "resolution": "2K"},
        api_key=api_key,
        api_secret=api_secret,
    )
    images = getattr(result, "images", None) or result.get("images", [])
    if not images:
        raise RuntimeError("Higgsfield SDK returned no images")
    img = images[0]
    url = getattr(img, "url", None) or (img if isinstance(img, str) else None)
    if not url:
        raise RuntimeError("Could not extract image URL from SDK result")
    return {"url": url}


async def _call_rest(model: str, prompt: str, api_key: str, api_secret: str) -> dict:
    """Async REST fallback using httpx."""
    import httpx

    api_url = f"https://platform.higgsfield.ai/{model}"
    headers = {
        "Authorization": f"Key {api_key}:{api_secret}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "resolution": "2K",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    images = data.get("images") or data.get("output") or []
    if isinstance(images, list) and images:
        first = images[0]
        url = first if isinstance(first, str) else first.get("url")
    elif isinstance(data, dict) and data.get("url"):
        url = data["url"]
    else:
        raise RuntimeError(f"No image URL in Higgsfield response: {list(data.keys())}")

    return {"url": url}


async def generate_design(idea_title: str, niche: str, product_type: str) -> dict:
    """Generate a design via Higgsfield. Falls back to demo on any failure."""
    api_key, api_secret = _parse_hf_key()

    if not api_key:
        return _demo_fallback(idea_title, niche, product_type, "HF_KEY not set")

    model = _model_for_niche(niche)
    prompt = _build_prompt(idea_title, niche, product_type)

    try:
        if _SDK_AVAILABLE:
            result = await asyncio.wait_for(
                asyncio.to_thread(_call_sdk, model, prompt, api_key, api_secret),
                timeout=120.0,
            )
        else:
            result = await asyncio.wait_for(
                _call_rest(model, prompt, api_key, api_secret),
                timeout=120.0,
            )

        return {
            "url": result["url"],
            "prompt": prompt,
            "demo": False,
            "revised_prompt": None,
            "model": model,
        }

    except asyncio.TimeoutError:
        return _demo_fallback(idea_title, niche, product_type, "Higgsfield timeout (>120s)")
    except Exception as e:
        err_type = type(e).__name__
        err_msg = str(e)[:120]
        return _demo_fallback(idea_title, niche, product_type, f"{err_type}: {err_msg}")


async def generate_variants(
    idea_title: str, niche: str, product_type: str, count: int = 2
) -> list[dict]:
    """Generate multiple design variants with a 2s delay between calls."""
    results = []
    for i in range(count):
        if i > 0:
            await asyncio.sleep(2)
        result = await generate_design(idea_title, niche, product_type)
        results.append(result)
    return results
