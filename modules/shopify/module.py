"""
modules/shopify/module.py
=========================
BusinessModule for a Shopify dropshipping / branded store.

Business model:
  - HEIMDALL finds trending products via Google Trends / TikTok virality
  - VULCAN generates product lifestyle images and ad creatives (Leonardo)
  - LOKI creates the Shopify product listing via Shopify Admin API
  - VAULT tracks COGS vs revenue per order

Current status: STUB — runs end-to-end in demo mode.
To activate: set SHOPIFY_STORE_DOMAIN + SHOPIFY_ADMIN_TOKEN env vars.

Shopify Admin API docs: https://shopify.dev/docs/api/admin-rest
"""
from __future__ import annotations

import uuid
from datetime import datetime

from core.business_module import BusinessModule, IdeaResult, AssetResult, PublishResult


_SHOPIFY_NICHES = [
    ("Minimalist Ceramic Candle Holder", "home decor", "home product"),
    ("Weighted Anxiety Relief Blanket", "wellness", "home product"),
    ("Personalized Pet Portrait Canvas", "pet lovers", "wall art"),
    ("Eco-Friendly Bamboo Tumbler Set", "sustainable living", "drinkware"),
    ("LED Moon Lamp Night Light", "aesthetic decor", "home product"),
    ("Customizable Leather Notebook", "stationery", "accessory"),
    ("Posture Corrector Support Band", "fitness", "health product"),
]


class ShopifyModule(BusinessModule):

    MODULE_ID   = "shopify"
    NAME        = "Shopify Store"
    ICON        = "🛒"
    DESCRIPTION = "Branded Shopify dropshipping store with AI-generated product listings and ad creatives."
    SUPPORTS_DESIGN_APPROVAL = True

    def required_env_vars(self) -> list[str]:
        return ["SHOPIFY_STORE_DOMAIN", "SHOPIFY_ADMIN_TOKEN", "LEONARDO_API_KEY"]

    async def validate_credentials(self) -> dict[str, bool]:
        return {v: self._has_env(v) for v in self.required_env_vars()}

    # ------------------------------------------------------------------
    # generate_idea
    # ------------------------------------------------------------------

    async def generate_idea(self, context: dict) -> IdeaResult:
        """
        In production: scrape Google Trends, TikTok Discover, and Amazon
        Best Sellers to identify trending products with high margins.
        Demo: rotate through curated list.
        """
        import random
        title, niche, product_type = random.choice(_SHOPIFY_NICHES)
        return IdeaResult(
            title=title,
            niche=niche,
            product_type=product_type,
            keywords=[niche, product_type, "trending", "gift idea", title.split()[0].lower()],
            description=f"Trending Shopify product: {title}. High-margin, low-competition.",
            metadata={"cogs_estimate": 8.00, "suggested_price": 34.99},
        )

    # ------------------------------------------------------------------
    # generate_asset — product photo + ad creative
    # ------------------------------------------------------------------

    async def generate_asset(self, idea: IdeaResult, context: dict) -> AssetResult:
        """Generate product lifestyle photo and ad creative via Leonardo."""
        from integrations.leonardo import generate_design, leonardo_available

        image_urls = []

        if leonardo_available():
            try:
                result = await generate_design(
                    idea.title,
                    niche=idea.niche,
                    product_type="poster",  # clean product-style composition
                    num_images=1,
                )
                if result.get("success") and result.get("images"):
                    image_urls = [img["url"] for img in result["images"]]
            except Exception as e:
                print(f"[SHOPIFY] Image generation failed: {e}")

        if not image_urls:
            image_urls = [
                f"https://via.placeholder.com/1200x1200/f0f0f0/333?text={idea.title.replace(' ', '+')}"
            ]

        # Product description copy
        product_copy = (
            f"{idea.title} — {idea.description}\n\n"
            f"Perfect gift for {idea.niche} lovers. Fast shipping. "
            f"30-day satisfaction guarantee."
        )

        return AssetResult(
            image_urls=image_urls,
            content=product_copy,
            metadata={"niche": idea.niche, "cogs": idea.metadata.get("cogs_estimate", 8.00)},
            idea=idea,
        )

    # ------------------------------------------------------------------
    # publish — create Shopify product via Admin API
    # ------------------------------------------------------------------

    async def publish(self, asset: AssetResult, context: dict) -> PublishResult:
        """
        Create a Shopify product with image, description, and variants.
        Demo mode when SHOPIFY_ADMIN_TOKEN is not set.
        """
        import httpx

        idea = asset.idea
        store = self._env("SHOPIFY_STORE_DOMAIN")
        token = self._env("SHOPIFY_ADMIN_TOKEN")
        price_usd = round(idea.metadata.get("suggested_price", 34.99), 2)
        is_demo = not (store and token)

        if is_demo:
            fake_id = uuid.uuid4().hex[:10]
            return PublishResult(
                listing_id=fake_id,
                product_id=fake_id,
                url=f"https://{store or 'your-store.myshopify.com'}/products/{fake_id}",
                price_usd=price_usd,
                demo=True,
                metadata={"cogs": asset.metadata.get("cogs", 8.00)},
            )

        payload = {
            "product": {
                "title": idea.title,
                "body_html": asset.content.replace("\n", "<br>"),
                "vendor": "AsgardMade",
                "product_type": idea.product_type,
                "tags": ", ".join(idea.keywords),
                "variants": [
                    {"price": str(price_usd), "inventory_management": "shopify"}
                ],
                "images": [{"src": url} for url in asset.image_urls],
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"https://{store}/admin/api/2024-01/products.json",
                    headers={
                        "X-Shopify-Access-Token": token,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()["product"]
                product_id = str(data["id"])
                handle = data.get("handle", product_id)
                return PublishResult(
                    listing_id=product_id,
                    product_id=product_id,
                    url=f"https://{store}/products/{handle}",
                    price_usd=price_usd,
                    demo=False,
                    metadata={"shopify_id": product_id, "cogs": asset.metadata.get("cogs", 8.00)},
                )
        except Exception as e:
            return PublishResult(error=str(e), demo=True, price_usd=price_usd)

    # ------------------------------------------------------------------
    # track_revenue
    # ------------------------------------------------------------------

    async def track_revenue(self, publish_result: PublishResult, context: dict) -> dict:
        state = context.get("state")
        cogs = publish_result.metadata.get("cogs", 8.00)
        price = publish_result.price_usd
        shopify_fee = round(price * 0.029 + 0.30, 2)  # Shopify payment processing
        expected_revenue = round(price - cogs - shopify_fee, 2)
        expense = round(cogs + shopify_fee, 2)

        if not publish_result.demo and state:
            txn = {
                "id": str(uuid.uuid4()),
                "type": "expense",
                "amount": expense,
                "description": f"Shopify COGS: {publish_result.product_id}",
                "source": "shopify",
                "timestamp": datetime.now().isoformat(),
            }
            state.vault["transactions"].append(txn)
            state.recalculate_vault()
            state.save_vault()

        return {
            "expense": expense,
            "expected_revenue": expected_revenue,
            "breakdown": {"cogs": cogs, "shopify_processing": shopify_fee, "price": price},
        }
