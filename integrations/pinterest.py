"""
Pinterest integration — auto-pin Etsy listings when LOKI publishes them.

Required env vars:
  PINTEREST_TOKEN    — Pinterest API OAuth bearer token
  PINTEREST_BOARD_ID — Target board ID to pin to
"""
from __future__ import annotations


import logging
import os

import httpx

logger = logging.getLogger(__name__)

PINTEREST_API_URL = "https://api.pinterest.com/v5/pins"


def _token() -> str:
    return os.getenv("PINTEREST_TOKEN", "")


def _board_id() -> str:
    return os.getenv("PINTEREST_BOARD_ID", "")


async def create_pin(
    title: str,
    description: str,
    image_url: str,
    link: str,
    board_id: str | None = None,
) -> str | None:
    """
    Create a Pinterest pin via the v5 API.

    Args:
        title:       Pin title (truncated to 100 chars).
        description: Pin description (truncated to 500 chars).
        image_url:   Public URL of the image to use as pin media.
        link:        Destination URL (e.g. the Etsy listing URL).
        board_id:    Override board — defaults to PINTEREST_BOARD_ID env var.

    Returns:
        The created pin's ID string on success, or None on failure/misconfiguration.
    """
    token = _token()
    board = board_id or _board_id()

    if not token:
        logger.warning("[PINTEREST] PINTEREST_TOKEN not set — skipping pin creation")
        return None
    if not board:
        logger.warning("[PINTEREST] PINTEREST_BOARD_ID not set — skipping pin creation")
        return None

    payload = {
        "board_id": board,
        "title": title[:100],
        "description": description[:500],
        "link": link,
        "media_source": {
            "source_type": "image_url",
            "url": image_url,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                PINTEREST_API_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            pin_id = data.get("id")
            logger.info(f"[PINTEREST] Pin created: {pin_id} for '{title}'")
            return pin_id
    except Exception as e:
        logger.warning(f"[PINTEREST] Pin creation failed: {type(e).__name__}: {e}")
        return None
