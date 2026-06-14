"""
AsgardMade Sales Intelligence — per-niche performance tracker.
Feeds real sales data back to HEIMDALL so it prioritizes proven niches.

Storage: data/sales_intel.json
"""

import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("data")
SALES_INTEL_FILE = DATA_DIR / "sales_intel.json"


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _load() -> dict:
    """Load sales intel JSON, returning empty dict on missing or corrupt file."""
    if not SALES_INTEL_FILE.exists():
        return {}
    try:
        return json.loads(SALES_INTEL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    """Persist sales intel to disk."""
    DATA_DIR.mkdir(exist_ok=True)
    SALES_INTEL_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def record_sale(niche: str, product_type: str, revenue: float, units: int = 1) -> None:
    """
    Accumulate per-niche performance data from an Etsy sale.
    Called whenever a revenue transaction is recorded in VAULT.

    Args:
        niche:        Niche name (e.g. "cottagecore", "dog mom").
        product_type: Product type (e.g. "t-shirt", "mug", "wall art").
        revenue:      Sale revenue in dollars (gross).
        units:        Number of units sold (default 1).
    """
    try:
        niche_key = (niche or "general").strip().lower()
        pt_key = (product_type or "unknown").strip().lower()
        data = _load()

        entry = data.get(niche_key, {
            "niche": niche_key,
            "product_types": {},
            "total_revenue": 0.0,
            "total_units": 0,
            "sale_count": 0,
            "first_sale": datetime.now().isoformat(),
            "last_sale": datetime.now().isoformat(),
        })

        entry["total_revenue"] = round(entry.get("total_revenue", 0.0) + revenue, 2)
        entry["total_units"] = entry.get("total_units", 0) + units
        entry["sale_count"] = entry.get("sale_count", 0) + 1
        entry["last_sale"] = datetime.now().isoformat()

        # Per-product-type breakdown
        pt = entry.get("product_types", {})
        pt_entry = pt.get(pt_key, {"units": 0, "revenue": 0.0})
        pt_entry["units"] += units
        pt_entry["revenue"] = round(pt_entry["revenue"] + revenue, 2)
        pt[pt_key] = pt_entry
        entry["product_types"] = pt

        data[niche_key] = entry
        _save(data)
        print(f"[SALES INTEL] Recorded: {niche_key} | {pt_key} | ${revenue:.2f} | {units} unit(s)")
    except Exception as e:
        print(f"[SALES INTEL] record_sale error: {type(e).__name__}: {e}")


def get_top_niches(n: int = 10) -> list:
    """
    Return the top n niches ranked by total revenue.
    Each entry includes niche name, revenue, units, and best-selling product type.

    Returns:
        List of dicts sorted by total_revenue descending.
    """
    try:
        data = _load()
        if not data:
            return []
        ranked = sorted(data.values(), key=lambda x: x.get("total_revenue", 0.0), reverse=True)
        results = []
        for entry in ranked[:n]:
            pt_data = entry.get("product_types", {})
            best_pt = (
                max(pt_data, key=lambda k: pt_data[k].get("units", 0))
                if pt_data else "unknown"
            )
            results.append({
                "niche": entry.get("niche", "unknown"),
                "total_revenue": entry.get("total_revenue", 0.0),
                "total_units": entry.get("total_units", 0),
                "sale_count": entry.get("sale_count", 0),
                "best_product_type": best_pt,
                "last_sale": entry.get("last_sale", ""),
            })
        return results
    except Exception as e:
        print(f"[SALES INTEL] get_top_niches error: {type(e).__name__}: {e}")
        return []


def get_bestsellers(min_units: int = 3) -> list:
    """
    Return niches that have sold at least min_units units total.
    Used by the bestseller requeue loop to identify proven performers.

    Args:
        min_units: Minimum cumulative units sold to qualify (default 3).

    Returns:
        List of niche entry dicts meeting the threshold.
    """
    try:
        data = _load()
        return [
            entry for entry in data.values()
            if entry.get("total_units", 0) >= min_units
        ]
    except Exception as e:
        print(f"[SALES INTEL] get_bestsellers error: {type(e).__name__}: {e}")
        return []


def format_top_niches_for_prompt(n: int = 10) -> str:
    """
    Format top niches as a compact text block for injection into HEIMDALL's prompt.
    Returns empty string if no sales data exists yet.
    """
    try:
        top = get_top_niches(n)
        if not top:
            return ""
        lines = ["Top-performing niches by revenue (prioritize these and adjacent ideas):"]
        for i, entry in enumerate(top, 1):
            lines.append(
                f"  {i}. {entry['niche']} — ${entry['total_revenue']:.2f} revenue, "
                f"{entry['total_units']} units sold, best product: {entry['best_product_type']}"
            )
        return "\n".join(lines)
    except Exception:
        return ""
