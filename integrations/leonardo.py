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

# Style presets that work best for POD products.
# CREATIVE gives Leonardo Phoenix more freedom to render intricate detail
# versus ILLUSTRATION which can over-simplify. NONE is used when the
# prompt itself fully specifies the style.
POD_STYLE = "CREATIVE"


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
    "cottagecore":   "intricate vintage botanical watercolor illustration, hand-painted honeybees and wildflowers with detailed wing venation, delicate petal rendering, warm honey-golden and sage-green palette, fine folk art ink linework with crosshatching, pressed-flower herbarium aesthetic",
    "dark academia": "moody gothic copperplate engraving style, intricately detailed library books and candlelight motifs, rich sepia and deep charcoal tones, fine hatching and cross-hatching technique, ornate Victorian decorative borders, scholarly antique aesthetic",
    "gaming":        "bold detailed retro vector pixel art, vibrant neon RGB palette with precise pixel-level shading, 8-bit to 16-bit arcade era fidelity, sharp clean outlines, intricate sprite-level detail, scanline texture overlay",
    "gamer":         "bold detailed retro vector pixel art, vibrant neon RGB palette with precise pixel-level shading, 8-bit to 16-bit arcade era fidelity, sharp clean outlines, intricate sprite-level detail, scanline texture overlay",
    "patriotic":     "bold high-detail americana vintage graphic, fine distressed texture with aged ink grain, deep red white and blue, intricately rendered eagle with feather detail, stars-and-stripes motifs, vintage WPA travel poster illustration style",
    "4th of july":   "bold high-detail americana graphic, intricate fireworks burst rendering, detailed star clusters and banner motifs, deep red white and blue palette, festive retro poster style with fine halftone dots and vintage ink texture",
    "pet":           "charming highly detailed watercolor animal illustration, individual fur strand rendering, warm cozy tones, expressive breed-accurate pet portrait with soft ink outline, delicate watercolor wash layers with fine detail",
    "dog":           "highly detailed dog breed illustration, individual fur strand shading, warm earthy tones, expressive friendly portrait, fine detailed ink outlines, breed-specific anatomical accuracy, soft vignette background",
    "cat":           "charming detailed cat illustration, delicate fine-line fur texture, soft expressive eyes with iris detail, clean playful lines, soft pastel palette with subtle gradient shading",
    "sustainable":   "clean eco-conscious detailed line art, intricately veined botanical leaf motifs, muted earth tones with precise stroke weight variation, hand-drawn feel with professional fine-pen detail",
    "mental health": "uplifting detailed typographic design, intricate decorative letterforms, soft gradient layers, positive affirmation aesthetic, precisely spaced clean sans-serif with ornamental flourishes",
    "family":        "elegant vintage typography with intricate floral ornamental border, hand-lettered calligraphy with fine swash details, warm ivory and gold color palette, delicate decorative flourishes",
    "grandpa":       "classic americana detailed badge design, bold vintage serif lettering with inline strokes, navy and aged gold tones, intricately rendered emblem with banner ribbon and star details, etched illustration style",
    "grandma":       "elegant detailed floral typography, lush soft floral wreath with individual petal and leaf detail, warm rose and cream palette, fine calligraphic letterforms, grandmother keepsake aesthetic",
    "graduation":    "elegant high-detail achievement design, intricately rendered mortarboard cap and diploma scroll with ribbon, gold leaf and navy, fine serif typography with ornate academic decorative elements",
    "birthday":      "festive highly detailed celebration illustration, intricately rendered confetti shapes and ribbon curls, bright cheerful colors with depth shading, detailed birthday cake with candle flames and frosting texture",
    "christmas":     "classic detailed holiday illustration, intricately rendered pine tree with individual needle detail, fine snowflake crystalline structures, rich cozy red and green palette, vintage Christmas card engraving style",
    "halloween":     "spooky-detailed illustration, intricately carved pumpkin face with wax drip candle, detailed bat wing membrane texture, bold orange and black with purple accent, haunted gothic decorative elements",
    "floral":        "highly detailed botanical fine art illustration, individual petal and stamen rendering, lush vibrant blooms with layered watercolor wash, museum-quality print with professional illustrator detail level",
    "botanical":     "precise scientific botanical illustration style, intricate ink linework with every vein and sepal detailed, natural muted tones, pressed-flower specimen aesthetic, Royal Horticultural Society illustration standard",
    "vintage":       "highly detailed retro vintage distressed poster, fine aged letterpress texture with authentic ink press imperfections, muted warm palette, ornate decorative borders, classic Americana etching aesthetic",
    "minimalist":    "ultra-clean precision minimalist vector, single accent color on pure white, razor-precise geometric forms with perfect weight, Swiss International Design aesthetic, professional commercial brand design",
    "funny":         "bold highly detailed comedic cartoon graphic, bright saturated colors with cel-shading depth, clean comic book linework with varied line weight, exaggerated expression with fine character detail",
    "motivation":    "powerful typographic poster, bold high-contrast black and gold with intricate geometric decorative elements, strong composition with fine ornamental detail, inspirational premium aesthetic",
    "adventure":     "highly detailed rugged vintage travel poster, intricately rendered mountain peaks with rock face texture, wilderness motifs with fine tree silhouettes, earthy tones, WPA national park illustration style",
    "hiking":        "detailed vintage national park poster style, intricately rendered mountain and trail scenery, earthy muted tones with fine topographic detail, bold vintage serif type with park emblem",
    "ocean":         "detailed coastal watercolor illustration, individual wave foam rendering, intricate marine life with scale and fin detail, turquoise to deep navy gradient palette, breezy nautical fine art aesthetic",
    "space":         "highly detailed cosmic illustration, intricate nebula gas cloud rendering with star field depth, deep navy and gold palette, detailed planet surface texture, celestial mystical premium artwork",
    "celestial":     "intricate mystical celestial illustration, detailed moon phase crescent with crater texture, elaborate constellation linework, deep navy and gold leaf art nouveau floral border, spiritual fine art aesthetic",
    "music":         "bold highly detailed music-themed graphic, intricately rendered instrument silhouettes with hardware detail, dynamic musical notation, vibrant colors with concert poster depth and halftone texture",
    "coffee":        "warm detailed cafe illustration, intricately rendered coffee beans with surface gloss, delicate rising steam curl, rich espresso-brown and cream palette with fine crosshatch shading, cozy morning aesthetic",
    "latte":         "warm detailed cafe illustration, intricate latte art rosette pattern, delicate coffee steam wisps, rich espresso-brown and cream palette with precise shading, cozy artisan coffee shop aesthetic",
    "yoga":          "serene detailed zen illustration, intricately rendered lotus flower with individual petal gradients, geometric mandala with fine radial linework, soft pastel sunrise tones, spiritual premium minimalist",
    "fitness":       "bold athletic detailed graphic, intricately rendered muscular silhouette with anatomical accuracy, dynamic motion lines, high-contrast black and white with single powerful accent color, energy aesthetic",
    "cooking":       "charming detailed kitchen illustration, intricately rendered herbs and spice elements with fine botanical detail, utensil motifs with material texture, warm inviting earthy tones with precise linework",
    "witch":         "detailed mystical witchy illustration, intricately rendered moon phases and crystal facets with light refraction, fine potion bottle label detail, deep purple and midnight black with gold accent, celestial feminine aesthetic",
    "crystal":       "highly detailed mystical gemstone illustration, intricate crystal facet planes with light refraction rendering, deep jewel-tone palette with specular highlights, spiritual fine art aesthetic",
    "mahjong":       "elegant intricately detailed Asian-inspired tile illustration, fine calligraphic brushwork, precisely rendered tile characters with stroke accuracy, rich traditional red and gold palette, cultural premium fine art",
    "pride":         "bold detailed rainbow celebration graphic, intricately rendered spectrum color gradients, vibrant spectrum colors with depth, inclusive love-wins premium aesthetic with decorative flourishes",
    "teacher":       "warm detailed educational illustration, intricately rendered apple with reflection highlight, fine pencil detail with eraser and shaving, cheerful primary colors with depth, heartfelt appreciation premium aesthetic",
    "nurse":         "clean detailed medical appreciation graphic, intricately rendered stethoscope with metal and tubing texture, heart motif with fine detail, navy and white palette, professional fine-line healthcare aesthetic",
    "bees":          "whimsical highly detailed botanical honey illustration, intricate bumblebee rendering with wing venation and body fuzz, detailed hexagonal honeycomb structure, warm amber and golden yellow palette, fine folk art linework",
    "honey":         "warm detailed rustic honey illustration, intricately rendered hexagonal honeycomb grid, golden amber drip with translucent light through honey, rich golden tones, artisan farmhouse premium aesthetic",
    "tote":          "bold high-contrast screen-print style graphic, intricately detailed silhouette art, strong readable composition, flat color illustration with precise edge definition, screen-print production quality",
    "mug":           "cozy highly detailed illustrated wrap-around graphic, bold shapes with fine decorative detail readable at ceramic scale, warm inviting palette with depth shading, wrap-around composition consideration",
}

# -- Print Composition Rules by Product Type ---------------------------------
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

_DEFAULT_STYLE = "highly detailed professional graphic illustration, vibrant colors with rich tonal depth, crisp precise linework, intricate fine detail, award-winning commercial print artwork"
_DEFAULT_COMPOSITION = "centered print graphic, bold readable design with intricate detail, white or transparent background, professional POD artwork at maximum resolution"


def _build_pod_prompt(idea_title: str, niche: str, style_hint: str = "", product_type: str = "t-shirt") -> str:
    product_words = ["t-shirt", "tshirt", "shirt", "hoodie", "sweatshirt",
                     "mug", "tote", "bag", "poster", "canvas", "sticker",
                     "phone case", "wall art", "print"]
    concept = idea_title
    for pw in product_words:
        concept = concept.replace(pw.title(), "").replace(pw, "").strip(" -|")
    if not concept:
        concept = idea_title

    niche_lower = niche.lower()
    art_style = style_hint or _DEFAULT_STYLE
    best_match_len = 0
    for keyword, style in _NICHE_STYLE_MAP.items():
        if keyword in niche_lower and len(keyword) > best_match_len:
            art_style = style
            best_match_len = len(keyword)

    pt_lower = product_type.lower().strip()
    composition = _PRODUCT_COMPOSITION_MAP.get(pt_lower, _DEFAULT_COMPOSITION)

    prompt = (
        f"Masterful ultra-high-quality print-on-demand graphic design: {concept}. "
        f"Art style: {art_style}. "
        f"Technical rendering: razor-sharp crisp edges, extremely intricate fine detail, "
        f"professional commercial illustrator quality, rich saturated colors with perfect tonal balance, "
        f"no pixelation, no blur, no noise — print-ready at 4800 DPI DTG quality. "
        f"Composition: {composition}. "
        f"CRITICAL RULES: pure isolated design artwork ONLY — absolutely NO product photos, "
        f"NO t-shirt shape, NO mug silhouette, NO model wearing clothing, NO product photography, "
        f"NO background scene, NO lifestyle context, NO product mockup of any kind. "
        f"Output must be clean isolated graphic design artwork on pure white or transparent background, "
        f"professional print-on-demand upload ready."
    )
    return prompt


_NEGATIVE_PROMPT = (
    "product mockup, product photography, t-shirt photo, mug on table, model wearing, "
    "person wearing, mannequin, lifestyle photo, stock photo, photorealistic product, "
    "blurry, low quality, watermark, text overlay, cluttered background, dark background, "
    "busy background, gradient background, shadowed product, 3D render of product, "
    "low resolution, pixelated, jpeg artifacts, compression artifacts, noise, grain, "
    "out of focus, soft focus, oversaturated, washed out, flat colors with no detail, "
    "simplistic, generic clipart, amateur, amateurish, childish scribble, "
    "clothing on person, garment shape, fabric texture, product context, scene background"
)


async def generate_design(
    idea_title: str,
    niche: str = "",
    style_hint: str = "",
    product_type: str = "t-shirt",
    num_images: int = 2,
) -> dict:
    api_key = os.getenv("LEONARDO_API_KEY", "").strip()
    if not api_key:
        return {"success": False, "error": "LEONARDO_API_KEY not set", "images": []}

    effective_niche = niche or idea_title
    prompt = _build_pod_prompt(idea_title, effective_niche, style_hint=style_hint, product_type=product_type)
    print(f"[VULCAN] Generating {num_images} image(s) for: {idea_title!r} | niche: {effective_niche!r} | product: {product_type}")
    print(f"[VULCAN] Prompt: {prompt[:200]}...")

    payload = {
        "prompt": prompt,
        "negative_prompt": _NEGATIVE_PROMPT,
        "modelId": POD_MODEL_ID,
        "num_images": num_images,
        "width": 1472,    # Max for Phoenix — higher res = more detail
        "height": 1472,
        "presetStyle": POD_STYLE,
        "public": False,
        "contrast": 3.5,  # Phoenix contrast boost: 1-4.5, higher = more vivid
        "enhancePrompt": True,  # Let Leonardo auto-enhance for quality
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE_URL}/generations",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            generation_id = data.get("sdGenerationJob", {}).get("generationId")
            if not generation_id:
                return {"success": False, "error": f"No generation ID in response: {data}", "images": []}

            print(f"[VULCAN] Generation started: {generation_id}")

            for attempt in range(18):
                await asyncio.sleep(5)
                poll = await client.get(
                    f"{BASE_URL}/generations/{generation_id}",
                    headers=_headers(),
                )
                poll.raise_for_status()
                poll_data = poll.json()
                gen = poll_data.get("generations_by_pk", {})
                status = gen.get("status", "PENDING")

                if status == "COMPLETE":
                    images_raw = gen.get("generated_images", [])
                    images = [
                        {"url": img["url"], "id": img.get("id", "")}
                        for img in images_raw
                        if img.get("url")
                    ]
                    print(f"[VULCAN] Generation complete: {len(images)} image(s) ready.")
                    return {"success": True, "images": images}

                if status == "FAILED":
                    return {"success": False, "error": "Generation failed on Leonardo side", "images": []}

                print(f"[VULCAN] Status: {status} (attempt {attempt+1}/18)")

            return {"success": False, "error": "Generation timed out after 90s", "images": []}

    except httpx.HTTPStatusError as e:
        error_body = e.response.text[:300]
        print(f"[VULCAN] Leonardo API error {e.response.status_code}: {error_body}")
        return {"success": False, "error": f"HTTP {e.response.status_code}: {error_body}", "images": []}
    except Exception as e:
        print(f"[VULCAN] Leonardo generation exception: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e), "images": []}
