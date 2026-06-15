"""
Pinterest integration — create pins for published Etsy listings.

Requires:
    PINTEREST_ACCESS_TOKEN — Pinterest API v5 access token
    PINTEREST_BOARD_ID    — Board ID to pin to

If credentials are missing, create_pin() returns None silently.
"""
from __future__ import annotations

import os
import httpx

PINTEREST_API = "https://api.pinterest.com/v5"


def _has_credentials() -> bool:
    return bool(os.getenv("PINTEREST_ACCESS_TOKEN") and os.getenv("PINTEREST_BOARD_ID"))


async def create_pin(
    title: str,
    description: str,
    image_url: str,
    link: str,
) -> str | None:
    """Create a pin on Pinterest. Returns pin ID on success, None otherwise."""
    if not _has_credentials():
        return None
    token = os.getenv("PINTEREST_ACCESS_TOKEN", "")
    board_id = os.getenv("PINTEREST_BOARD_ID", "")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{PINTEREST_API}/pins",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "board_id": board_id,
                    "title": title[:100],
                    "description": description[:500],
                    "link": link,
                    "media_source": {
                        "source_type": "image_url",
                        "url": image_url,
                    },
                },
            )
            if resp.status_code in (200, 201):
                return resp.json().get("id")
            print(f"[PINTEREST] Pin creation failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"[PINTEREST] Error: {e}")
    return None
