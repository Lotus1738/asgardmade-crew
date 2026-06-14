"""
Amazon Merch by Amazon integration for AsgardMade Pantheon.

STATUS: No public API available.

Amazon Merch by Amazon does NOT offer a public API. Uploading designs is
done entirely through the web portal at https://merch.amazon.com. There
is no official third-party API, no OAuth flow, and no documented endpoints.

Additionally, Merch by Amazon is an invite-only program. You must request
access at https://merch.amazon.com and wait for approval before you can
upload any designs.

MANUAL WORKAROUND (once approved):
1. Log in at https://merch.amazon.com
2. Click "Add Products" → select product type (e.g., T-Shirt)
3. Upload the design image (download from image_url first, must be PNG,
   at least 4500x5400 px, 300 dpi, transparent or white background)
4. Fill in title (max 60 chars for search), brand (your brand name),
   bullet points (2 required), and description
5. Set colors and pricing (Amazon controls the base price; you set the
   royalty tier via price selection)
6. Submit for review (Amazon reviews take 24–72 hours)

AMAZON MERCH SEO NOTES (different from Etsy):
- Title: Brand + main keyword + secondary keyword (60 char cap for search indexing)
  Example: "AsgardMade Cottagecore Frog Shirt Dark Academia Aesthetic Tee"
- Bullet points: Feature the emotion and use case, NOT just product specs
  "Soft ring-spun cotton tee perfect for cottagecore fans and aesthetic lovers"
- Description: Keyword-rich but natural; Amazon A9 algorithm weights title > bullets > desc
- Price: $19.99–$25.99 is the sweet spot for merch (higher royalties at higher price)
- No external links or brand names (other than your own) in content

Future: If Amazon opens a Merch API (rumored but unconfirmed as of 2026),
replace this stub. Potential env vars would be:
  AMAZON_MERCH_SELLER_ID = os.getenv("AMAZON_MERCH_SELLER_ID")
  AMAZON_MERCH_ACCESS_KEY = os.getenv("AMAZON_MERCH_ACCESS_KEY")
  AMAZON_MERCH_SECRET_KEY = os.getenv("AMAZON_MERCH_SECRET_KEY")
"""

import os

AMAZON_MERCH_AVAILABLE = False

# Amazon Merch title is capped at 60 chars for search indexing
AMAZON_TITLE_MAX = 60

# Amazon Merch bullet points (2 required, max 256 chars each)
AMAZON_BULLETS_MAX = 256


def _build_amazon_title(title: str, niche: str) -> str:
    """Build an Amazon Merch-optimized title (60 char search cap)."""
    candidate = f"{title} {niche.title()} Tee"
    return candidate[:AMAZON_TITLE_MAX]


def _build_amazon_bullets(title: str, niche: str, tags: list[str]) -> list[str]:
    """Build 2 bullet points for Amazon Merch listing."""
    tag_sample = ", ".join(tags[:4]) if tags else niche
    bullet1 = f"Perfect gift for {niche.lower()} fans and aesthetic lovers — unique print-on-demand design"
    bullet2 = f"Lightweight soft tee with vibrant print | Keywords: {tag_sample}"
    return [bullet1[:AMAZON_BULLETS_MAX], bullet2[:AMAZON_BULLETS_MAX]]


async def publish(
    title: str,
    tags: list[str],
    image_url: str,
    description: str,
) -> dict:
    """
    Stub: Amazon Merch by Amazon has no public API.
    Returns a dict with manual upload instructions.
    """
    niche = tags[0] if tags else "general"
    amazon_title = _build_amazon_title(title, niche)
    bullets = _build_amazon_bullets(title, niche, tags)
    portal_url = "https://merch.amazon.com"

    return {
        "platform": "amazon_merch",
        "available": False,
        "status": "manual_required",
        "instructions": (
            f"Amazon Merch requires manual upload (invite-only, no API). "
            f"1) Go to {portal_url} → Add Products "
            f"2) Upload PNG from: {image_url} (min 4500x5400px, 300dpi) "
            f"3) Title: {amazon_title} "
            f"4) Bullets: {bullets[0][:60]}... "
            f"5) Submit for Amazon review (24-72h)."
        ),
        "portal_url": portal_url,
        "image_url": image_url,
        "amazon_title": amazon_title,
        "bullets": bullets,
        "description": description,
        "tags": tags[:10],
    }
