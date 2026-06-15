"""
Variant Generator — color palette variants for bestselling designs.
When a niche hits bestseller status (3+ sales), VULCAN generates
3 color palette variants of the same design concept.
"""

COLOR_PALETTES = [
    {"name": "Pastel Dream", "desc": "soft pastel palette — blush pink, mint green, lavender, cream white background"},
    {"name": "Dark Academia", "desc": "moody dark palette — deep burgundy, forest green, warm brown, cream text on dark background"},
    {"name": "Neon Pop", "desc": "bold vibrant palette — electric blue, hot pink, lime green, white background with high contrast"},
    {"name": "Earthy Boho", "desc": "warm earthy tones — terracotta, rust orange, sage green, sandy beige background"},
    {"name": "Monochrome", "desc": "black and white only — stark black linework, pure white background, no color"},
    {"name": "Golden Luxury", "desc": "premium gold accents — deep navy or black background, gold and cream elements"},
    {"name": "Cottagecore Bloom", "desc": "floral soft palette — dusty rose, sage, butter yellow, warm white background"},
]


async def generate_color_variants(original_title: str, niche: str, product_type: str, count: int = 3) -> list[dict]:
    """Pick count random palettes and return variant idea dicts ready to add to the queue."""
    import random
    palettes = random.sample(COLOR_PALETTES, min(count, len(COLOR_PALETTES)))
    variants = []
    for palette in palettes:
        variant_title = f"{original_title} — {palette['name']}"
        variant_desc = (
            f"Color variant of bestselling design. {palette['desc']}. "
            f"Same concept as '{original_title}' but recolored for a different aesthetic buyer."
        )
        variants.append({
            "title": variant_title,
            "niche": niche,
            "product_type": product_type,
            "description": variant_desc,
            "source": f"AUTO-VARIANT: {palette['name']}",
            "palette": palette["name"],
        })
    return variants
