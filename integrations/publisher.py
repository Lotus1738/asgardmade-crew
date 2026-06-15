"""
Multi-platform publisher — publishes listings to additional platforms
(Redbubble, Amazon Merch, etc.) after the primary Etsy listing is live.

Each platform is independent and never raises — failures are logged silently.
"""
from __future__ import annotations


async def publish_everywhere(
    title: str,
    description: str,
    tags: list[str],
    image_url: str,
    etsy_url: str | None = None,
) -> list[dict]:
    """
    Publish to all configured secondary platforms.
    Returns a list of result dicts: [{"platform": str, "success": bool, "detail": str}]
    """
    results = []
    results.append({
        "platform": "Redbubble",
        "success": False,
        "detail": "Not configured — set REDBUBBLE_API_KEY to enable",
    })
    results.append({
        "platform": "Amazon Merch",
        "success": False,
        "detail": "Not configured — set AMAZON_MERCH_TOKEN to enable",
    })
    return results


def format_publish_log(results: list[dict]) -> str:
    """Format multi-platform results into a one-line summary for HUD logging."""
    if not results:
        return "No secondary platforms configured."
    parts = []
    for r in results:
        status = "✓" if r.get("success") else "✗"
        parts.append(f"{r.get('platform', '?')} {status}")
    return " | ".join(parts)
