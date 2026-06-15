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


# ── Niche → Art Style Mapping ─────────────────────────────────────────────────
# Maps niche keywords to visual art style descriptions.
# The more specific the style, the better Leonardo produces recognizable, saleable artwork.
_NICHE_STYLE_MAP = {
    "cottagecore":   "whimsical vintage botanical watercolor, honeybees and wildflowers, warm honey-golden and sage-green palette, folk art ink linework",
    "dark academia": "moody gothic ink illustration, library books and candlelight motifs, sepia and charcoal tones, antique copper-plate engraving style",
    "gaming":        "bold retro vector pixel art, vibrant neon RGB palette, 8-bit arcade era, sharp clean outlines",
    "gamer":         "bold retro vector pixel art, vibrant neon RGB palette, 8-bit arcade era, sharp clean outlines",
    "patriotic":     "bold americana vintage graphic, distressed texture, red white and blue, eagle and stars-and-stripes motifs, vintage travel poster style",
    "4th of july":   "bold americana graphic, fireworks and stars motifs, red white and blue palette, festive retro poster style",
    "pet":           "charming loose watercolor animal illustration, warm cozy tones, expressive breed-accurate pet portrait",
    "dog":           "detailed dog breed illustration, warm earthy tones, expressive friendly portrait, fine ink outlines",
    "cat":           "cute minimalist cat illustration, clean playful lines, soft pastel palette",
    "sustainable":   "clean eco-conscious minimalist line art, botanical leaf motifs, muted earth tones, hand-drawn feel",
    "mental health": "uplifting typography-focused design, soft gradient background, positive affirmation aesthetic, clean sans-serif style",
    "family":        "elegant vintage typography, floral ornamental border, warm ivory and gold color palette, hand-lettered feel",
    "grandpa":       "classic americana badge design, bold serif lettering, navy and gold tones, vintage emblem with banner ribbon",
    "grandma":       "elegant floral typography, soft floral wreath border, warm rose and cream palette, grandmother aesthetic",
    "graduation":    "elegant achievement design, mortarboard cap and diploma scroll, gold and navy, clean serif typography",
    "birthday":      "festive celebration illustration, confetti and ribbon, bright cheerful colors, birthday cake motif",
    "christmas":     "classic holiday illustration, pine trees and snowflakes, cozy red and green palette, vintage Christmas card style",
    "halloween":     "spooky-cute illustration, pumpkin and bat motifs, bold orange and black, playful haunted aesthetic",
    "floral":        "detailed botanical fine art illustration, lush vibrant blooms, watercolor wash style, museum-quality print",
    "botanical":     "scientific botanical illustration, precise ink linework, natural muted tones, pressed-flower aesthetic",
    "vintage":       "retro vintage distressed poster, muted warm palette, aged letterpress texture, classic Americana",
    "minimalist":    "ultra-clean minimalist vector, single accent color on white, precise geometric forms, Swiss design style",
    "funny":         "bold comedic cartoon graphic, bright saturated colors, clean comic book linework, exaggerated expression",
    "motivation":    "strong typographic poster, bold high-contrast black and gold, geometric shapes, inspirational aesthetic",
    "adventure":     "rugged vintage travel poster, mountain and wilderness motifs, earthy tones, retro outdoor illustration",
    "hiking":        "vintage national park poster style, mountain and trail motifs, earthy muted tones, bold serif type",
    "ocean":         "coastal watercolor illustration, waves and marine life, turquoise and deep navy palette, breezy nautical feel",
    "space":         "cosmic detailed illustration, stars and nebula, deep navy and gold palette, celestial mystical style",
    "celestial":     "mystical celestial illustration, moon phases and constellations, deep navy and gold leaf, art nouveau inspired",
    "music":         "bold music-themed graphic, dynamic musical notes and instrument silhouettes, vibrant colors, concert poster style",
    "coffee":        "warm cafe illustration, coffee beans and steam curl, rich espresso-brown and cream palette, cozy morning aesthetic",
    "latte":         "warm cafe illustration, latte art and coffee steam, rich brown and cream palette, cozy coffee shop aesthetic",
    "yoga":          "serene zen illustration, lotus flower and mandala motifs, soft pastel sunrise tones, spiritual minimalist",
    "fitness":       "bold athletic graphic, dynamic motion blur lines, high-contrast black and white with one accent color",
    "cooking":       "charming kitchen illustration, herbs, spices, and utensil motifs, warm inviting earthy tones",
    "witch":         "mystical witchy illustration, moon and crystal motifs, deep purple and black, celestial feminine aesthetic",
    "crystal":       "mystical gemstone illustration, sparkling crystal clusters, deep jewel-tone palette, spiritual aesthetic",
    "mahjong":       "elegant Asian-inspired tile illustration, clean lines, traditional red and gold palette, cultural detail",
    "pride":         "bold rainbow celebration graphic, vibrant spectrum colors, inclusive love-wins aesthetic",
    "teacher":       "warm educational illustration, apple and pencil motifs, cheerful primary colors, appreciation aesthetic",
    "nurse":         "clean medical appreciation graphic, heart and stethoscope motifs, navy and white palette, professional aesthetic",
}

# ── Print Composition Rules by Product Type ───────────────────────────────────
# Tells Leonardo HOW to compose the design for each print surface.
_PRODUCT_COMPOSITION_MAP = {
    "t-shirt":    "centered chest print graphic, bold and readable at arm's length, strong silhouette, white or transparent background, designed for direct-to-garment printing",
    "hoodie":     "large centered front graphic, high contrast for printing on dark fabric, impactful bold design with clear focal point, transparent background",
    "mug":        "wide horizontal panoramic illustration (landscape format), bold shapes that read clearly at ceramic scale, centered focal element flanked by decorative side motifs, high contrast",
    "tote bag":   "bold centered graphic, high contrast screen-print aesthetic, strong readable silhouette at medium size, white background",
    "poster":     "full rich illustrated composition, decorative frame or border treatment, gallery art print aesthetic, sophisticated color palette, fine detail rewarded",
    "wall art":   "full detailed art print, gallery-quality composition, frameable fine-art aesthetic, rich color depth and layered detail",
    "phone case": "portrait-format centered graphic (2:3 ratio), clean focal design with white background, detail that photographs well",
    "sticker":    "clean vector illustration with defined crisp outline, vibrant flat colors, die-cut friendly silhouette, white or transparent background",
    "sweatshirt": "large centered chest graphic, high contrast for printing, bold and impactful, similar to hoodie format",
    "canvas":     "full rich painting composition, gallery-wrapped edge consideration, fine-art aesthetic, vibrant painterly style",
}

_DEFAULT_COMPOSITION = "centered graphic design artwork, white background, bold and print-ready"


def _build_pod_prompt(idea_title: str, niche: str, style_hint: str = "", product_type: str = "t-shirt") -> str:
    """
    Build a print-on-demand DESIGN ARTWORK prompt for Leonardo.

    Generates the graphic artwork that gets PRINTED ON the product.
    NOT a product mockup photo — Printify auto-generates mockup photos separately.

    Key principle: the output should be clean artwork/illustration on white/transparent
    background — exactly like a professional designer would provide to a print shop.
    """
    # Find art style from niche keywords
    niche_lower = (niche or "").lower()
    art_style = ""
    for keyword, style in _NICHE_STYLE_MAP.items():
        if keyword in niche_lower:
            art_style = style
            break

    # Also scan the idea title if niche didn't match
    if not art_style:
        title_lower = idea_title.lower()
        for keyword, style in _NICHE_STYLE_MAP.items():
            if keyword in title_lower:
                art_style = style
                break

    if not art_style:
        art_style = "professional graphic design illustration, bold colors, clean composition, Etsy bestseller aesthetic"

    # Get composition rules for this product type
    composition = _PRODUCT_COMPOSITION_MAP.get(
        product_type.lower().strip(),
        _DEFAULT_COMPOSITION,
    )

    # Strip product-type words from title to get the core design concept
    concept = idea_title
    for strip_word in [
        " T-Shirt", " Hoodie", " Mug", " Poster", " Tote Bag", " Tote",
        " Sticker", " Phone Case", " Wall Art", " Canvas Print", " Canvas",
        " Sweatshirt", " Collection", " Series", " Set",
    ]:
        concept = concept.replace(strip_word, "").replace(strip_word.lower(), "")
    concept = concept.strip(" ,.-")

    prompt = (
        f"Print-on-demand graphic design artwork: {concept}. "
        f"Art style: {art_style}. "
        f"Composition: {composition}. "
        f"Rules: pure artwork only — absolutely NO product photos, NO t-shirt photo, "
        f"NO mug photo, NO model wearing clothing, NO product mockup, NO photography. "
        f"Deliver clean design artwork on white background, ready for print-on-demand upload."
    )

    if style_hint:
        prompt += f" Extra direction: {style_hint}"

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
    # Use data/generated/ — Railway volume, persists across redeploys
    # public/generated/ is ephemeral and wiped on every redeploy
    cache_dir = Path("data/generated")
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
            "blurry, low quality, watermark, signature, "
            "photo of t-shirt, t-shirt mockup, photo of mug, mug mockup, "
            "photo of hoodie, product photography, flat lay photo, "
            "model wearing clothing, person in shirt, garment photograph, "
            "commercial retail photography, stock photo of product, "
            "text garbled, distorted letters, illegible text, "
            "distorted, ugly, poorly drawn, bad anatomy, duplicate, extra limbs"
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
