"""
Multi-platform publisher for AsgardMade Pantheon.

Orchestrates publishing a design to all supported platforms after Etsy listing
is confirmed. Never raises — each platform result is logged independently.

Supported platforms:
  - Etsy (result passed in from existing pipeline)
  - Redbubble (stub — no public API; returns manual instructions)
  - Amazon Merch by Amazon (stub — no public API; returns manual instructions)
"""
from __future__ import annotations


import asyncio
from datetime import datetime
from typing import Callable, Awaitable

import integrations.redbubble as rb
import integrations.amazon_merch as amz


async def publish_everywhere(
    title: str,
    description: str,
    tags: list[str],
    image_url: str,
    etsy_url: str | None = None,
) -> dict:
    """
    Attempt to publish a design on all platforms.

    Args:
        title:       The design/product title
        description: Listing description
        tags:        SEO tags (up to 13 for Etsy, 15 for Redbubble, 10 for Amazon)
        image_url:   URL to the design image
        etsy_url:    Etsy listing URL (already published — passed through as-is)

    Returns:
        Dict mapping platform name → result dict or error string.
        Never raises.
    """
    results: dict = {
        "etsy": etsy_url or "already_published",
        "timestamp": datetime.now().isoformat(),
    }

    platforms: list[tuple[str, Callable[..., Awaitable[dict]]]] = [
        ("redbubble", rb.publish),
        ("amazon_merch", amz.publish),
    ]

    for platform_name, publish_fn in platforms:
        try:
            result = await publish_fn(
                title=title,
                tags=tags,
                image_url=image_url,
                description=description,
            )
            results[platform_name] = result
        except Exception as e:
            results[platform_name] = f"error: {type(e).__name__}: {e}"

    return results


def format_publish_log(results: dict) -> str:
    """Return a concise log line summarizing multi-platform publish results."""
    lines = []
    for platform, result in results.items():
        if platform == "timestamp":
            continue
        if isinstance(result, str):
            lines.append(f"{platform.upper()}: {result[:80]}")
        elif isinstance(result, dict):
            status = result.get("status", "unknown")
            available = result.get("available", False)
            if available:
                listing_url = result.get("url", result.get("listing_url", ""))
                lines.append(f"{platform.upper()}: LIVE — {listing_url}")
            else:
                lines.append(f"{platform.upper()}: {status} (manual upload required)")
        else:
            lines.append(f"{platform.upper()}: unexpected result type")

    return " | ".join(lines)
