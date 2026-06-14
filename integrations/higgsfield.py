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


def _model_for_niche(niche):
    n = niche.lower()
    if any(kw in n for kw in _CHARACTER_NICHES):
        return "higgsfield-ai/soul/standard"
    if any(kw in n for kw in _PRECISION_NICHES):
        return "higgsfield-ai/nano-banana-pro"
    return "bytedance/seedream/v4/text-to-image"


def _build_prompt(idea_title, niche, product_type):
    n = niche.lower()
    if any(kw in n for kw in _PRECISION_NICHES):
        style = "clean line art, bold minimalist digital art"
        extra = (
            "Shot on full-frame digital camera, 85mm lens, studio lighting. "
            "NOT photorealistic, NOT complex backgrounds, NOT cluttered. "
            "Subject occupies 60% of frame, rigid 1:1 canvas."
        )
    elif any(kw in n for kw in _CHARACTER_NICHES):
        style = "flat vector illustration, bold clean digital art"
        extra = ""
    else:
        style = "flat vector illustration, minimalist digital art"
        extra = ""

    parts = [
        "Subject: " + idea_title + ", specific and unambiguous.",
        "Composition: square 1:1, centered subject, generous padding, macro detail.",
        "Style: " + style + ".",
        "Background: pure white #FFFFFF, mandatory for POD printing.",
        "Constraints: no shadows, no gradients, no complex backgrounds, no photorealism, no text unless requested.",
        "Niche: " + niche + ".",
    ]
    if extra:
        parts.append(extra)
    parts.append("2K resolution, 300dpi, crisp edges, print-ready for " + product_type + ".")
    return " ".join(parts)


def _demo_fallback(idea_title, niche, product_type, reason):
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


def _parse_hf_key():
    hf_key = os.getenv("HF_KEY", "")
    if not hf_key or ":" not in hf_key:
        return None, None
    parts = hf_key.split(":", 1)
    return parts[0].strip(), parts[1].strip()


def _call_sdk(model, prompt, api_key, api_secret):
    result = _hf_sdk.subscribe(
        model,
        arguments={"prompt": prompt, "aspect_ratio": "1:1", "resolution": "1080p"},
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


async def _call_rest(model, prompt, api_key, api_secret):
    import httpx
    auth = {"Authorization": "Key " + api_key + ":" + api_secret}
    hdrs = dict(auth)
    hdrs["Content-Type"] = "application/json"
    payload = {"prompt": prompt, "aspect_ratio": "1:1", "resolution": "1080p"}
    submit_url = "https://platform.higgsfield.ai/" + model

    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(submit_url, json=payload, headers=hdrs)
        r.raise_for_status()
        sd = r.json()

    rid = sd.get("request_id")
    if not rid:
        raise RuntimeError("No request_id in: " + str(sd))

    status_url = sd.get("status_url") or (
        "https://platform.higgsfield.ai/requests/" + rid + "/status"
    )

    async with httpx.AsyncClient(timeout=15.0) as p:
        for _ in range(40):
            await asyncio.sleep(3)
            pr = await p.get(status_url, headers=auth)
            pr.raise_for_status()
            pd = pr.json()
            st = pd.get("status")
            if st == "completed":
                imgs = pd.get("images", [])
                if not imgs:
                    raise RuntimeError("Completed but no images")
                img = imgs[0]
                return {"url": img.get("url") if isinstance(img, dict) else img}
            if st in ("failed", "nsfw"):
                raise RuntimeError("Generation " + st + ": " + str(pd))

    raise RuntimeError("Polling timed out after 40 attempts")


async def generate_design(idea_title, niche, product_type):
    api_key, api_secret = _parse_hf_key()
    if not api_key:
        return _demo_fallback(idea_title, niche, product_type, "HF_KEY not set")

    model = _model_for_niche(niche)
    prompt = _build_prompt(idea_title, niche, product_type)

    try:
        if _SDK_AVAILABLE:
            coro = asyncio.to_thread(_call_sdk, model, prompt, api_key, api_secret)
        else:
            coro = _call_rest(model, prompt, api_key, api_secret)
        result = await asyncio.wait_for(coro, timeout=150.0)
        return {
            "url": result["url"],
            "prompt": prompt,
            "demo": False,
            "revised_prompt": None,
            "model": model,
        }
    except asyncio.TimeoutError:
        return _demo_fallback(idea_title, niche, product_type, "Timeout >150s")
    except Exception as e:
        return _demo_fallback(idea_title, niche, product_type,
                              type(e).__name__ + ": " + str(e)[:120])


async def generate_variants(idea_title, niche, product_type, count=2):
    results = []
    for i in range(count):
        if i > 0:
            await asyncio.sleep(2)
        results.append(await generate_design(idea_title, niche, product_type))
    return results
