"""
Leonardo.ai image generation integration for AsgardMade Pantheon.
Used by VULCAN to generate high-quality print-on-demand designs.

Required env var:
  LEONARDO_API_KEY — from leonardo.ai → Profile → API Key

Leonardo generates better POD designs than DALL-E:
  - More consistent style
  - Better for apparel/merchandise
  - Free tier: 150 tokens/day (~30 images)

Fallback: gpt-image-1 (OpenAI) — used when Leonardo tokens are depleted.
  Images are saved locally to public/generated/ and served via /generated/ route.
  (Pollinations.ai is blocked from Railway IPs — do not use as fallback.)

API docs: https://docs.leonardo.ai/reference/creategeneration
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import httpx

BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"

# Best model IDs for print-on-demand designs
# Phoenix = Leonardo's flagship model, great for merchandise
# FLUX Dev = photorealistic, good for mockups
POD_MODEL_ID = "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3"   # Leonardo Phoenix
FLUX_MODEL_ID = "aa77f04e-3eec-4034-9c07-d0f619684628"   # FLUX Dev (fallback)

# Style presets that work best for POD products
POD_STYLE = "ILLUSTRATION"


def _headers() -> dict:
    key = os.getenv("LEONARDO_API_KEY", "")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def leonardo_available() -> bool:
    return bool(os.getenv("LEONARDO_API_KEY"))


_PRODUCT_MOCKUP_TEMPLATES = {
    "t-shirt": (
        "A flat-lay product photography mockup of a white t-shirt on a clean light background, "
        "with a custom graphic print centered on the chest showing '{design}' ({niche} theme). "
        "Professional Etsy product photo, sharp details, soft shadows, photorealistic."
    ),
    "hoodie": (
        "A flat-lay product photography mockup of a black pullover hoodie on a clean background, "
        "front graphic print showing '{design}' ({niche} theme). "
        "Professional Etsy product photo, photorealistic, sharp focus."
    ),
    "mug": (
        "A product photography mockup of a white ceramic coffee mug on a wooden table, "
        "with '{design}' ({niche} theme) printed on the side. "
        "Professional Etsy product photo, warm lighting, photorealistic."
    ),
    "poster": (
        "A product photography mockup of a framed art print hanging on a white wall, "
        "artwork shows '{design}' ({niche} theme). "
        "Professional Etsy product photo, clean minimalist staging, photorealistic."
    ),
    "tote bag": (
        "A product photography mockup of a natural canvas tote bag on a clean white background, "
        "with '{design}' ({niche} theme) screen-printed on the front. "
        "Professional Etsy product photo, photorealistic."
    ),
    "phone case": (
        "A product photography mockup of a clear/white smartphone phone case, "
        "with '{design}' ({niche} theme) printed design. "
        "Professional Etsy product photo, clean background, photorealistic."
    ),
}

_DEFAULT_MOCKUP = (
    "A product photography mockup of a {product_type} with '{design}' ({niche} theme) print design. "
    "Professional Etsy product photo, clean background, photorealistic, sharp details."
)


def _build_pod_prompt(idea_title: str, niche: str, style_hint: str = "", product_type: str = "t-shirt") -> str:
    """Build a product mockup prompt so the generated image shows the actual Etsy product."""
    pt_lower = product_type.lower().strip()
    template = _PRODUCT_MOCKUP_TEMPLATES.get(pt_lower, _DEFAULT_MOCKUP)
    prompt = template.format(
        design=idea_title,
        niche=niche,
        product_type=product_type,
    )
    if style_hint:
        prompt += f" {style_hint}"
    return prompt


async def _generate_via_ai_fallback(
    idea_title: str,
    niche: str,
    product_type: str = "t-shirt",
) -> dict:
    """
    Fallback image generator using gpt-image-1 (OpenAI).
    Used when Leonardo.ai tokens are exhausted.
    Saves images locally to public/generated/ and returns a local /generated/ URL.
    NOTE: Pollinations.ai is blocked from Railway server IPs (returns 402) — do not use.
    """
    import hashlib
    import base64
    import openai

    prompt = _build_pod_prompt(idea_title, niche, product_type=product_type)
    design_id = hashlib.md5(f"{idea_title}_{niche}_{product_type}".encode()).hexdigest()[:12]
    cache_dir = Path("public/generated")
    cache_dir.mkdir(parents=True, exist_ok=True)
    local_file = cache_dir / f"{design_id}.jpg"

    # Return cached version if it exists and is a real image
    if local_file.exists() and local_file.stat().st_size > 5000:
        print(f"[GPT-IMAGE] Cache hit: /generated/{design_id}.jpg")
        return {
            "success": True,
            "images": [{"url": f"/generated/{design_id}.jpg", "id": design_id}],
            "generation_id": design_id,
            "demo": False,
            "source": "gpt_image_cached",
            "error": None,
        }

    try:
        print(f"[GPT-IMAGE] Generating: {idea_title} ({product_type})")
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = await client.images.generate(
            model="gpt-image-1",
            prompt=prompt[:1500],
            n=1,
            size="1024x1024",
            quality="low",
        )
        img_bytes = base64.b64decode(resp.data[0].b64_json)
        local_file.write_bytes(img_bytes)
        print(f"[GPT-IMAGE] Saved {len(img_bytes)} bytes to /generated/{design_id}.jpg")
        return {
            "success": True,
            "images": [{"url": f"/generated/{design_id}.jpg", "id": design_id}],
            "generation_id": design_id,
            "demo": False,
            "source": "gpt_image_1",
            "error": None,
        }
    except Exception as e:
        print(f"[GPT-IMAGE] Error: {e}")
        return {
            "success": False,
            "images": [],
            "generation_id": "",
            "demo": False,
            "source": "",
            "error": f"gpt-image-1: {e}",
        }


async def generate_design(
    idea_title: str,
    niche: str,
    style_hint: str = "",
    product_type: str = "t-shirt",
    width: int = 1024,
    height: int = 1024,
    num_images: int = 2,
) -> dict:
    """
    Generate POD design images.

    Tries Leonardo.ai first (higher quality). If Leonardo tokens are exhausted
    or the key is unavailable, automatically falls back to gpt-image-1 (OpenAI).
    Images are saved locally to public/generated/ and served via /generated/ URL.

    Returns:
        {
            "success": bool,
            "images": [{"url": str, "id": str}, ...],
            "generation_id": str,
            "demo": bool,
            "error": str | None,
        }
    """
    # If no Leonardo key, go straight to gpt-image-1
    if not leonardo_available():
        print("[GENERATE] No Leonardo key — using gpt-image-1 fallback")
        return await _generate_via_ai_fallback(idea_title, niche, product_type)

    prompt = _build_pod_prompt(idea_title, niche, style_hint, product_type)

    payload = {
        "prompt": prompt,
        "negative_prompt": (
            "blurry, low quality, watermark, text, signature, logo, "
            "distorted, ugly, poorly drawn, bad anatomy, duplicate"
        ),
        "modelId": POD_MODEL_ID,
        "width": width,
        "height": height,
        "num_images": num_images,
        "presetStyle": POD_STYLE,
        "alchemy": True,
        "highResolution": False,
        "public": False,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            # Step 1: Submit generation
            resp = await client.post(
                f"{BASE_URL}/generations",
                headers=_headers(),
                json=payload,
            )

            # Token exhaustion → fall back to Pollinations
            if resp.status_code == 400 and "not enough" in resp.text.lower():
                print("[LEONARDO] Tokens exhausted — falling back to Pollinations.ai")
                return await _generate_via_ai_fallback(idea_title, niche, product_type)

            resp.raise_for_status()
            data = resp.json()
            gen_id = data.get("sdGenerationJob", {}).get("generationId", "")

            if not gen_id:
                print("[LEONARDO] No generation ID — falling back to Pollinations.ai")
                return await _generate_via_ai_fallback(idea_title, niche, product_type)

            # Step 2: Poll for completion (up to 90 seconds)
            for attempt in range(18):
                await asyncio.sleep(5)
                poll = await client.get(
                    f"{BASE_URL}/generations/{gen_id}",
                    headers=_headers(),
                )
                poll.raise_for_status()
                poll_data = poll.json()
                gen = poll_data.get("generations_by_pk", {})
                status = gen.get("status", "")

                if status == "COMPLETE":
                    images = [
                        {"url": img.get("url", ""), "id": img.get("id", "")}
                        for img in gen.get("generated_images", [])
                        if img.get("url")
                    ]
                    return {
                        "success": True,
                        "images": images,
                        "generation_id": gen_id,
                        "demo": False,
                        "source": "leonardo",
                        "error": None,
                    }
                elif status == "FAILED":
                    print("[LEONARDO] Generation failed — falling back to Pollinations.ai")
                    return await _generate_via_ai_fallback(idea_title, niche, product_type)
                # PENDING or IN_PROGRESS — keep polling

            print("[LEONARDO] Timed out — falling back to Pollinations.ai")
            return await _generate_via_ai_fallback(idea_title, niche, product_type)

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            print(f"[LEONARDO] {error_msg} — falling back to Pollinations.ai")
            return await _generate_via_ai_fallback(idea_title, niche, product_type)
        except Exception as e:
            print(f"[LEONARDO] {type(e).__name__}: {e} — falling back to Pollinations.ai")
            return await _generate_via_ai_fallback(idea_title, niche, product_type)


async def get_remaining_tokens() -> int:
    """Returns remaining daily token balance. -1 if unavailable."""
    if not leonardo_available():
        return -1
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/users/me",
                headers=_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                user = data.get("users", [{}])[0]
                return user.get("user_details", [{}])[0].get("tokenRenewalDate", -1)
        except Exception:
            pass
    return -1
