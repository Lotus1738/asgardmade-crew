"""
Redbubble integration for AsgardMade Pantheon.

STATUS: No public API available.

Redbubble does NOT offer a public API for creating listings. They have an
"Artist API" / partner program (https://www.redbubble.com/artist-services/api)
but it is invite-only and intended for print fulfillment partners, not
third-party shops uploading designs.

MANUAL WORKAROUND:
1. Go to https://www.redbubble.com/portfolio/manage_works/add_new
2. Upload the design image (download from the image_url first)
3. Set title, tags (up to 15), and description
4. Enable product types (t-shirts, stickers, mugs, etc.)
5. Publish

Future: If Redbubble opens their API, replace this stub with a real
implementation using the credentials below:
  REDBUBBLE_API_KEY = os.getenv("REDBUBBLE_API_KEY")
  REDBUBBLE_SHOP_URL = os.getenv("REDBUBBLE_SHOP_URL")
"""

import os

REDBUBBLE_AVAILABLE = False


async def publish(
    title: str,
    tags: list[str],
    image_url: str,
    description: str,
) -> dict:
    """
    Stub: Redbubble has no public API.
    Returns a dict with manual upload instructions and the listing URL to visit.
    """
    shop_url = os.getenv("REDBUBBLE_SHOP_URL", "https://www.redbubble.com/portfolio/manage_works/add_new")
    tag_str = ", ".join(tags[:15])

    return {
        "platform": "redbubble",
        "available": False,
        "status": "manual_required",
        "instructions": (
            f"Redbubble requires manual upload. "
            f"1) Go to {shop_url} "
            f"2) Upload image from: {image_url} "
            f"3) Title: {title[:50]} "
            f"4) Tags: {tag_str} "
            f"5) Publish all product types."
        ),
        "upload_url": shop_url,
        "image_url": image_url,
        "title": title,
        "tags": tags[:15],
        "description": description,
    }
