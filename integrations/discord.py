"""
Discord webhook integration — sends rich embed notifications for key Pantheon events.

Required env var:
  DISCORD_WEBHOOK_URL — Discord incoming webhook URL

Events supported:
  - Sale received      → notify_sale()
  - Item auto-approved → notify_approval()
  - Morning briefing   → notify_briefing()
  - Generic           → notify()
"""
from __future__ import annotations


import logging
import os

import httpx

logger = logging.getLogger(__name__)

# Embed colors
COLOR_GOLD = 0xC9A84C    # AsgardMade brand gold
COLOR_GREEN = 0x57F287   # success / sale
COLOR_BLUE = 0x5865F2    # informational / briefing
COLOR_RED = 0xED4245     # error / alert


def _webhook_url() -> str:
    return os.getenv("DISCORD_WEBHOOK_URL", "")


async def notify(
    message: str,
    title: str | None = None,
    color: int = COLOR_GOLD,
) -> None:
    """
    Post a Discord embed via webhook.

    Args:
        message: Embed description text (max 2000 chars).
        title:   Optional embed title.
        color:   Embed sidebar color as integer (default: AsgardMade gold).
    """
    url = _webhook_url()
    if not url:
        return  # silently no-op if not configured

    embed: dict = {
        "description": message[:2000],
        "color": color,
    }
    if title:
        embed["title"] = title

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"embeds": [embed]})
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[DISCORD] Notification failed: {type(e).__name__}: {e}")


async def notify_sale(niche: str, product: str, revenue: float) -> None:
    """Notify Discord when a sale is received."""
    await notify(
        message=(
            f"**Niche:** {niche}\n"
            f"**Product:** {product}\n"
            f"**Revenue:** ${revenue:.2f}"
        ),
        title="💰 Sale Received!",
        color=COLOR_GREEN,
    )


async def notify_approval(item_title: str, score: int) -> None:
    """Notify Discord when an item is auto-approved."""
    await notify(
        message=(
            f"**Item:** {item_title}\n"
            f"**Score:** {score}/100"
        ),
        title="✅ Item Auto-Approved",
        color=COLOR_GOLD,
    )


async def notify_briefing(briefing_text: str) -> None:
    """Notify Discord with the daily morning briefing."""
    await notify(
        message=briefing_text[:2000],
        title="🌅 Morning Briefing — AsgardMade Pantheon",
        color=COLOR_BLUE,
    )


async def notify_review_alert(
    listing_title: str,
    rating: int,
    review_text: str,
    listing_id: str | None = None,
) -> None:
    """Fires for 1-2 star reviews."""
    stars = "⭐" * rating + "☆" * (5 - rating)
    msg = f"**{stars} — {listing_title}**\n\"{review_text[:200]}\""
    if listing_id:
        msg += f"\nhttps://www.etsy.com/listing/{listing_id}"
    await notify(msg, title="⚠️ Negative Review Alert", color=0xe74c3c)


async def notify_general(message: str, color: int = COLOR_BLUE) -> None:
    """General-purpose notification used by A/B resolver and review monitor loops."""
    await notify(message=message, color=color)
