"""
Review tracker — persists Etsy review data and surfaces quality patterns.

Data lives in data/reviews.json.

Functions:
  record_review()         — save a review (dedup by review_id)
  get_flagged_listings()  — listings with avg rating < 3.5 or 2+ negatives
  get_review_pattern()    — detects if a product type keeps getting negatives
"""
from __future__ import annotations


import json
from datetime import datetime
from pathlib import Path

_DATA_FILE = Path("data/reviews.json")


def _load() -> dict:
    """Load review store. Returns {listing_id: {title, reviews: [...]}}"""
    if _DATA_FILE.exists():
        try:
            return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def record_review(
    listing_id: str,
    listing_title: str,
    rating: int,
    review_text: str,
    reviewer: str,
    review_id: str | None = None,
    product_type: str | None = None,
) -> bool:
    """
    Save a review entry.

    Returns True if this is a new review, False if already seen (dedup).
    Uses review_id for dedup if provided, otherwise falls back to
    (reviewer + review_text[:40]) composite key.
    """
    data = _load()

    entry = data.setdefault(str(listing_id), {
        "listing_title": listing_title,
        "product_type": product_type or "unknown",
        "reviews": [],
    })
    # Update title/product_type in case they changed
    entry["listing_title"] = listing_title
    if product_type:
        entry["product_type"] = product_type

    # Dedup check
    dedup_key = review_id or f"{reviewer}::{review_text[:40]}"
    for existing in entry["reviews"]:
        if existing.get("dedup_key") == dedup_key:
            return False  # already recorded

    entry["reviews"].append({
        "dedup_key": dedup_key,
        "rating": rating,
        "review_text": review_text,
        "reviewer": reviewer,
        "timestamp": datetime.now().isoformat(),
    })
    _save(data)
    return True


def get_flagged_listings() -> list:
    """
    Return listings that need attention:
      - Average rating < 3.5, OR
      - 2 or more reviews with rating ≤ 2
    """
    data = _load()
    flagged = []
    for listing_id, entry in data.items():
        reviews = entry.get("reviews", [])
        if not reviews:
            continue
        ratings = [r["rating"] for r in reviews]
        avg = sum(ratings) / len(ratings)
        neg_count = sum(1 for r in ratings if r <= 2)
        if avg < 3.5 or neg_count >= 2:
            flagged.append({
                "listing_id": listing_id,
                "listing_title": entry.get("listing_title", "Unknown"),
                "product_type": entry.get("product_type", "unknown"),
                "avg_rating": round(avg, 2),
                "negative_count": neg_count,
                "total_reviews": len(reviews),
            })
    return flagged


def get_review_pattern(product_type: str) -> str | None:
    """
    If 3+ negative (≤2 star) reviews exist for the same product_type,
    return a human-readable warning string; otherwise None.

    Scans all listings matching the product_type and looks for recurring
    complaint themes in the review text.
    """
    data = _load()
    neg_reviews = []
    for entry in data.values():
        if entry.get("product_type", "").lower() != product_type.lower():
            continue
        for r in entry.get("reviews", []):
            if r.get("rating", 5) <= 2:
                neg_reviews.append(r.get("review_text", ""))

    if len(neg_reviews) < 3:
        return None

    # Simple keyword frequency to surface common complaint theme
    complaint_keywords = {
        "print": ["print", "printing", "faded", "blurry", "color", "ink"],
        "shipping": ["shipping", "late", "delivery", "arrived", "slow", "days"],
        "quality": ["quality", "material", "fabric", "thin", "cheap", "fell apart"],
        "size": ["size", "sizing", "small", "large", "fit", "measurements"],
    }

    keyword_hits: dict[str, int] = {k: 0 for k in complaint_keywords}
    for text in neg_reviews:
        lower = text.lower()
        for category, words in complaint_keywords.items():
            if any(w in lower for w in words):
                keyword_hits[category] += 1

    top_complaint = max(keyword_hits, key=lambda k: keyword_hits[k])
    if keyword_hits[top_complaint] == 0:
        top_complaint = "general quality"

    return (
        f"{product_type.title()}s getting consistent complaints about "
        f"{top_complaint} ({len(neg_reviews)} negative reviews)"
    )
