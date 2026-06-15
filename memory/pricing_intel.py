"""
Pricing intelligence module — tracks competitor price data per niche/product combo
and provides suggested prices for LOKI's listing creation.

Data is stored in data/pricing_intel.json as:
  {
    "cottagecore|mug": {
      "niche": "cottagecore",
      "product_type": "mug",
      "prices": [21.00, 22.50, 19.99, ...]
    },
    ...
  }
"""

import json
from pathlib import Path

_DATA_FILE = Path("data/pricing_intel.json")


def _load() -> dict:
    if _DATA_FILE.exists():
        try:
            return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_competitor_price(niche: str, product_type: str, price: float) -> None:
    """Save a competitor price data point for the given niche/product combination."""
    if not niche or price <= 0:
        return
    data = _load()
    key = f"{niche.lower().strip()}|{product_type.lower().strip()}"
    if key not in data:
        data[key] = {"niche": niche, "product_type": product_type, "prices": []}
    data[key]["prices"].append(round(float(price), 2))
    # Keep last 50 data points per key to avoid unbounded growth
    data[key]["prices"] = data[key]["prices"][-50:]
    _save(data)


def get_suggested_price(niche: str, product_type: str, floor: float = 12.99) -> float:
    """
    Return the average competitor price + 5% margin for this niche/product combo.
    Falls back to floor if no data exists yet.
    """
    data = _load()
    key = f"{niche.lower().strip()}|{product_type.lower().strip()}"
    entry = data.get(key, {})
    prices = entry.get("prices", [])
    if not prices:
        return floor
    avg = sum(prices) / len(prices)
    suggested = round(avg * 1.05, 2)
    return max(suggested, floor)


def format_pricing_for_prompt(niche: str) -> str:
    """
    Return a compact pricing summary block for all product types in this niche.
    Example output:
      cottagecore mug avg $21.40 (8 data points). Suggested: $22.47
      cottagecore t-shirt avg $32.10 (5 data points). Suggested: $33.71
    Returns empty string if no data for this niche.
    """
    data = _load()
    niche_lower = niche.lower().strip()
    lines = []
    for key, entry in sorted(data.items()):
        if entry.get("niche", "").lower().strip() == niche_lower:
            prices = entry.get("prices", [])
            if not prices:
                continue
            avg = sum(prices) / len(prices)
            suggested = round(avg * 1.05, 2)
            product_type = entry.get("product_type", "unknown")
            count = len(prices)
            lines.append(
                f"{niche} {product_type} avg ${avg:.2f} ({count} data points). Suggested: ${suggested:.2f}"
            )
    return "\n".join(lines)
