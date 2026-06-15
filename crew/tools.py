from __future__ import annotations
import os
import psutil
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Any

try:
    from duckduckgo_search import DDGS
    _DDG_AVAILABLE = True
except ImportError:
    _DDG_AVAILABLE = False


LOG_DIR = Path("logs")


# ─── System Metrics ─────────────────────────────────────────────────────────

def get_system_metrics() -> dict:
    cpu = psutil.cpu_percent(interval=0.5)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    rx_kb = round(net.bytes_recv / 1024, 1)
    tx_kb = round(net.bytes_sent / 1024, 1)

    return {
        "cpu": round(cpu, 1),
        "ram": round(vm.percent, 1),
        "disk": round(disk.percent, 1),
        "network": {"rx": rx_kb, "tx": tx_kb},
        "ram_used_gb": round(vm.used / 1e9, 2),
        "ram_total_gb": round(vm.total / 1e9, 2),
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_total_gb": round(disk.total / 1e9, 2),
    }


# ─── Log Scanner ────────────────────────────────────────────────────────────

ERROR_PATTERNS = [
    ("CRITICAL", "critical"),
    ("Exception", "error"),
    ("Error:", "error"),
    ("ERROR", "error"),
    ("ConnectionRefusedError", "error"),
    ("TimeoutError", "error"),
    ("MemoryError", "error"),
    ("WARNING", "warning"),
    ("WARN", "warning"),
    ("Deprecation", "warning"),
]


def scan_logs(max_files: int = 10) -> dict:
    LOG_DIR.mkdir(exist_ok=True)
    errors = []
    warnings = []
    file_count = 0

    for log_file in list(LOG_DIR.glob("*.log"))[:max_files]:
        file_count += 1
        try:
            lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in lines[-200:]:
                for pattern, severity in ERROR_PATTERNS:
                    if pattern in line:
                        entry = {
                            "file": log_file.name,
                            "line": line.strip()[:200],
                            "severity": severity,
                            "timestamp": datetime.now().isoformat(),
                        }
                        if severity == "error":
                            errors.append(entry)
                        else:
                            warnings.append(entry)
                        break
        except Exception:
            pass

    return {
        "errors": errors[:20],
        "warnings": warnings[:20],
        "file_count": file_count,
        "scanned_at": datetime.now().isoformat(),
    }


# ─── Niche Research ─────────────────────────────────────────────────────────

NICHE_DATABASE: dict[str, Any] = {
    "dark academia": {
        "products": [
            "Vintage Library Aesthetic Tote Bag",
            "Moody Bookworm Sweatshirt",
            "Classical Literature Quote Mug",
            "Dark Academia Floral Skull T-Shirt",
            "Antique Map Print Poster",
        ],
        "keywords": ["dark academia", "bookish", "vintage aesthetic", "library lover", "literary", "gothic student", "moody vibes"],
        "demand_score_range": (86, 94),
        "competition": "Medium",
        "price_range": "$22–$32",
        "monthly_rev_range": ("$180", "$420"),
    },
    "cottagecore": {
        "products": [
            "Mushroom Foraging Tote Bag",
            "Wildflower Cottage Sweatshirt",
            "Bees and Honey Mug",
            "Pressed Flower Aesthetic T-Shirt",
            "Cottage Garden Watercolor Poster",
        ],
        "keywords": ["cottagecore", "cottage aesthetic", "mushroom lover", "wildflower", "nature aesthetic", "farmhouse style", "folk art"],
        "demand_score_range": (82, 91),
        "competition": "High",
        "price_range": "$20–$30",
        "monthly_rev_range": ("$200", "$500"),
    },
    "retro gaming": {
        "products": [
            "Pixel Art Console Nostalgia Tee",
            "8-Bit Adventure Mug",
            "Retro Game Controller Poster",
            "Classic RPG Party Hoodie",
            "Pixel Dungeon Map Tote Bag",
        ],
        "keywords": ["retro gaming", "pixel art", "8-bit", "gamer gift", "nostalgia gaming", "classic console", "arcade style"],
        "demand_score_range": (88, 95),
        "competition": "High",
        "price_range": "$22–$35",
        "monthly_rev_range": ("$250", "$600"),
    },
    "plant parent": {
        "products": [
            "Crazy Plant Lady Mug",
            "Propagation Station Tote",
            "Monstera Leaf Watercolor Tee",
            "Succulents & Self-Care Hoodie",
            "Plant Nerd Poster",
        ],
        "keywords": ["plant parent", "plant lover", "crazy plant lady", "houseplant", "monstera", "succulent lover", "green thumb"],
        "demand_score_range": (84, 92),
        "competition": "Medium",
        "price_range": "$18–$28",
        "monthly_rev_range": ("$160", "$380"),
    },
    "mental health": {
        "products": [
            "You Are Enough Minimalist Tee",
            "Therapy Is Cool Mug",
            "Mental Health Matters Hoodie",
            "Breathe & Reset Tote Bag",
            "Self-Care Sunday Poster",
        ],
        "keywords": ["mental health", "self care", "anxiety relief", "therapy", "mindfulness", "you are enough", "wellness"],
        "demand_score_range": (90, 96),
        "competition": "Medium",
        "price_range": "$20–$32",
        "monthly_rev_range": ("$220", "$550"),
    },
    "space exploration": {
        "products": [
            "Astronaut in Bloom Tee",
            "Solar System Map Poster",
            "Galaxy Vibe Hoodie",
            "Planets of the Solar System Mug",
            "Lost in Space Tote",
        ],
        "keywords": ["space lover", "astronaut", "galaxy aesthetic", "cosmos", "NASA fan", "star gazer", "universe"],
        "demand_score_range": (83, 91),
        "competition": "High",
        "price_range": "$22–$34",
        "monthly_rev_range": ("$190", "$460"),
    },
    "hiking": {
        "products": [
            "Mountains Are Calling Tee",
            "Trail Map Retro Poster",
            "Hike More Worry Less Mug",
            "Elevation Profile Hoodie",
            "Adventure Seeker Tote",
        ],
        "keywords": ["hiking", "trail life", "mountain lover", "outdoor adventure", "nature hiker", "camp vibes", "summit seeker"],
        "demand_score_range": (85, 93),
        "competition": "High",
        "price_range": "$22–$36",
        "monthly_rev_range": ("$200", "$480"),
    },
    "coffee culture": {
        "products": [
            "Coffee Is My Love Language Mug",
            "Espresso Yourself Tee",
            "Latte Art Minimalist Poster",
            "But First Coffee Tote",
            "Coffee Addict Hoodie",
        ],
        "keywords": ["coffee lover", "caffeine addict", "barista life", "espresso", "latte art", "morning coffee", "coffee shop"],
        "demand_score_range": (87, 94),
        "competition": "Very High",
        "price_range": "$15–$28",
        "monthly_rev_range": ("$150", "$400"),
    },
    "pet portraits": {
        "products": [
            "Custom Dog Mom Tote Bag",
            "Regal Cat Portrait Mug",
            "My Dog Is My Best Friend Tee",
            "Minimalist Pet Line Art Poster",
            "Fur Baby Appreciation Hoodie",
        ],
        "keywords": ["pet lover", "dog mom", "cat mom", "fur baby", "dog portrait", "cat lover gift", "pet gift"],
        "demand_score_range": (91, 97),
        "competition": "Medium",
        "price_range": "$22–$40",
        "monthly_rev_range": ("$280", "$700"),
    },
    "witchy aesthetic": {
        "products": [
            "Moon Phase Botanical Tee",
            "Witchy Vibes Mug",
            "Celestial Magic Poster",
            "Tarot Energy Hoodie",
            "Crystal Witch Tote",
        ],
        "keywords": ["witchy aesthetic", "moon phase", "celestial", "tarot", "crystal witch", "mystical", "gothic boho"],
        "demand_score_range": (88, 95),
        "competition": "Medium",
        "price_range": "$22–$34",
        "monthly_rev_range": ("$230", "$560"),
    },
    "minimalist design": {
        "products": [
            "Less Is More Quote Tee",
            "Clean Lines Architecture Poster",
            "One Line Drawing Mug",
            "Minimal Botanical Print",
            "Negative Space Art Tote",
        ],
        "keywords": ["minimalist", "clean aesthetic", "simple design", "modern art", "line art", "neutral tones", "minimal style"],
        "demand_score_range": (80, 88),
        "competition": "High",
        "price_range": "$18–$30",
        "monthly_rev_range": ("$140", "$340"),
    },
    "pride": {
        "products": [
            "Rainbow Pride Flag Tee",
            "Love Is Love Mug",
            "Pride Month Celebration Hoodie",
            "Be Yourself Pride Tote",
            "Inclusive Rainbow Poster",
        ],
        "keywords": ["pride", "lgbtq+", "gay pride", "rainbow flag", "love is love", "inclusive", "queer positive"],
        "demand_score_range": (85, 93),
        "competition": "High",
        "price_range": "$20–$32",
        "monthly_rev_range": ("$180", "$450"),
    },
}

_NICHES = list(NICHE_DATABASE.keys())
_niche_index = 0


def generate_niche_idea(niche: str | None = None) -> dict:
    """Generate a product idea for a given niche (or cycle through niches)."""
    import random
    import uuid

    global _niche_index
    if niche is None:
        niche = _NICHES[_niche_index % len(_NICHES)]
        _niche_index += 1

    data = NICHE_DATABASE.get(niche, NICHE_DATABASE["dark academia"])
    demand_min, demand_max = data["demand_score_range"]
    rev_min, rev_max = data["monthly_rev_range"]

    return {
        "id": str(uuid.uuid4()),
        "type": "idea",
        "status": "pending",
        "title": random.choice(data["products"]),
        "niche": niche.title(),
        "demandScore": random.randint(demand_min, demand_max),
        "productType": random.choice(["t-shirt", "hoodie", "mug", "tote bag", "poster"]),
        "competition": data["competition"],
        "estimatedMonthlyRevenue": f"{rev_min}–{rev_max}",
        "description": (
            f"High-potential {niche} product targeting buyers who love "
            f"{', '.join(data['keywords'][:3])}. "
            f"Price range {data['price_range']}. Strong visual appeal for POD."
        ),
        "keywords": data["keywords"][:7],
        "priceRange": data["price_range"],
        "createdAt": datetime.now().isoformat(),
    }


# ─── Web Search (DuckDuckGo, no API key needed) ─────────────────────────────

def search_etsy_trends(query: str, max_results: int = 5) -> list[dict]:
    if not _DDG_AVAILABLE:
        return []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(f"site:etsy.com {query}", max_results=max_results))
        return [{"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")} for r in results]
    except Exception:
        return []


def search_trends(query: str, max_results: int = 5) -> list[dict]:
    if not _DDG_AVAILABLE:
        return []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [{"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")} for r in results]
    except Exception:
        return []
