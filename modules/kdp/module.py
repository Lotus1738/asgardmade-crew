"""
modules/kdp/module.py
=====================
BusinessModule for Amazon KDP (Kindle Direct Publishing).

Business model:
  - HEIMDALL finds low-competition book niches (puzzle books, journals, coloring books)
  - VULCAN generates cover artwork (Leonardo) + interior content (AI text)
  - LOKI uploads manuscript + cover to KDP, sets price and keywords
  - VAULT tracks printing cost (~$2-4) vs royalty (35-70%)

Current status: STUB — runs end-to-end in demo mode.
To activate: set KDP_EMAIL + KDP_PASSWORD env vars and implement
the Selenium/Playwright uploader in _upload_to_kdp().
"""
from __future__ import annotations

import uuid
from datetime import datetime

from core.business_module import BusinessModule, IdeaResult, AssetResult, PublishResult


# KDP low-competition book niches that sell well
_KDP_NICHES = [
    ("Gratitude Journal for Women", "self-help", "journal"),
    ("Large Print Word Search for Seniors", "puzzle", "activity book"),
    ("Mandala Coloring Book for Adults", "art", "coloring book"),
    ("Lined Notebook — Minimalist Aesthetic", "stationery", "notebook"),
    ("Sudoku Puzzle Book Hard Level", "puzzle", "activity book"),
    ("Food & Mood Tracker Journal", "wellness", "journal"),
    ("Budget Planner Weekly 2026", "finance", "planner"),
    ("Baby Memory Book First Year", "family", "memory book"),
]

_KDP_PRICE_MAP = {
    "journal": 8.99,
    "notebook": 6.99,
    "activity book": 9.99,
    "coloring book": 7.99,
    "planner": 11.99,
    "memory book": 12.99,
}


class KDPModule(BusinessModule):

    MODULE_ID   = "kdp"
    NAME        = "Amazon KDP"
    ICON        = "📚"
    DESCRIPTION = "Low-content and activity books published on Amazon Kindle Direct Publishing."
    SUPPORTS_DESIGN_APPROVAL = True  # Commander approves cover before uploading to KDP

    def required_env_vars(self) -> list[str]:
        return ["LEONARDO_API_KEY"]  # KDP_EMAIL, KDP_PASSWORD when Selenium uploader is live

    # ------------------------------------------------------------------
    # generate_idea — find a low-competition KDP niche
    # ------------------------------------------------------------------

    async def generate_idea(self, context: dict) -> IdeaResult:
        """
        In production: call BSR scraper / KDP Rocket API to find
        low-competition niches with high demand.
        Demo: rotate through curated list.
        """
        import random
        title, niche, product_type = random.choice(_KDP_NICHES)
        keywords = [niche, product_type, "amazon kdp", "self-publish", title.split()[0].lower()]
        return IdeaResult(
            title=title,
            niche=niche,
            product_type=product_type,
            keywords=keywords,
            description=(
                f"Low-content KDP book: {title}. "
                f"Niche: {niche}. 6x9 inch paperback, 120 pages."
            ),
            metadata={"pages": 120, "trim_size": "6x9", "kdp_format": "paperback"},
        )

    # ------------------------------------------------------------------
    # generate_asset — cover image + interior placeholder
    # ------------------------------------------------------------------

    async def generate_asset(self, idea: IdeaResult, context: dict) -> AssetResult:
        """
        Generate a KDP book cover via Leonardo.
        In production: also generate interior pages (lined, dotted, puzzle grids).
        """
        from integrations.leonardo import generate_design, leonardo_available

        cover_urls = []

        if leonardo_available():
            # KDP covers are portrait 6x9 — override composition
            cover_prompt_idea = f"book cover: {idea.title}"
            cover_niche = f"{idea.niche} book publishing"
            try:
                result = await generate_design(
                    cover_prompt_idea,
                    niche=cover_niche,
                    product_type="poster",   # portrait format, similar to book cover
                    num_images=1,
                )
                if result.get("success") and result.get("images"):
                    cover_urls = [img["url"] for img in result["images"]]
            except Exception as e:
                print(f"[KDP] Cover generation failed: {e}")

        if not cover_urls:
            cover_urls = [
                f"https://via.placeholder.com/1600x2560/2c1810/gold?text={idea.title.replace(' ', '+')}"
            ]

        return AssetResult(
            image_urls=cover_urls,
            content=f"Interior placeholder for: {idea.title}\n120 pages, 6x9, {idea.niche} theme.",
            metadata={
                "pages": idea.metadata.get("pages", 120),
                "trim_size": idea.metadata.get("trim_size", "6x9"),
                "format": idea.metadata.get("kdp_format", "paperback"),
            },
            idea=idea,
        )

    # ------------------------------------------------------------------
    # publish — upload to KDP (demo until Selenium uploader is implemented)
    # ------------------------------------------------------------------

    async def publish(self, asset: AssetResult, context: dict) -> PublishResult:
        """
        In production: Playwright bot logs into KDP, fills book details,
        uploads cover + interior PDF, sets price and keywords, publishes.
        Demo: simulate the publish and return a fake ASIN.
        """
        idea = asset.idea
        price_usd = _KDP_PRICE_MAP.get(idea.product_type, 9.99)
        fake_asin = f"B0{uuid.uuid4().hex[:8].upper()}"

        # TODO: replace this block with real KDP Playwright uploader
        # from integrations.kdp_uploader import upload_book
        # result = await upload_book(cover_url=asset.primary_image,
        #                            interior_path=asset.content_path,
        #                            title=idea.title, ...)
        is_demo = not self._has_env("KDP_EMAIL", "KDP_PASSWORD")

        return PublishResult(
            listing_id=fake_asin,
            product_id=fake_asin,
            url=f"https://www.amazon.com/dp/{fake_asin}",
            price_usd=price_usd,
            demo=is_demo,
            metadata={
                "asin": fake_asin,
                "format": asset.metadata.get("format", "paperback"),
                "pages": asset.metadata.get("pages", 120),
                "royalty_pct": 0.60,
            },
        )

    # ------------------------------------------------------------------
    # track_revenue — KDP royalty structure
    # ------------------------------------------------------------------

    async def track_revenue(self, publish_result: PublishResult, context: dict) -> dict:
        """
        KDP royalties: 35% for books priced <$2.99 or >$9.99,
        70% for $2.99–$9.99 (digital), ~60% for paperback after printing costs.
        """
        state = context.get("state")
        price = publish_result.price_usd
        # Paperback: ~60% royalty after printing
        royalty_pct = 0.60 if price >= 2.99 else 0.35
        printing_cost = round(price * 0.40, 2)
        expected_revenue = round(price * royalty_pct, 2)
        expense = printing_cost

        if not publish_result.demo and state:
            txn = {
                "id": str(uuid.uuid4()),
                "type": "expense",
                "amount": expense,
                "description": f"KDP printing cost: {publish_result.listing_id}",
                "source": "kdp",
                "timestamp": datetime.now().isoformat(),
            }
            state.vault["transactions"].append(txn)
            state.recalculate_vault()
            state.save_vault()

        return {
            "expense": expense,
            "expected_revenue": expected_revenue,
            "royalty_pct": royalty_pct,
            "breakdown": {"printing_cost": printing_cost, "list_price": price},
        }
