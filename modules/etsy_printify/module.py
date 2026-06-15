"""
modules/etsy_printify/module.py
================================
BusinessModule implementation for the Etsy + Printify print-on-demand pipeline.

This wraps the existing crew/pipeline.py logic into the BusinessModule interface
so it works with the registry and pipeline runner. All Etsy and Printify API
calls stay inside this file — nothing outside this module imports those directly.

Agents involved: HEIMDALL (idea), VULCAN (design), LOKI (listing), VAULT (revenue)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from core.business_module import BusinessModule, IdeaResult, AssetResult, PublishResult


class EtsyPrintifyModule(BusinessModule):

    MODULE_ID   = "etsy_printify"
    NAME        = "Etsy + Printify"
    ICON        = "🛍️"
    DESCRIPTION = "Print-on-demand merchandise listed on Etsy via Printify fulfillment."
    SUPPORTS_DESIGN_APPROVAL = True   # Commander approves each design before publishing

    def required_env_vars(self) -> list[str]:
        return ["LEONARDO_API_KEY", "PRINTIFY_API_KEY", "PRINTIFY_SHOP_ID"]

    async def validate_credentials(self) -> dict[str, bool]:
        return {v: self._has_env(v) for v in self.required_env_vars()}

    # ------------------------------------------------------------------
    # generate_idea — uses HEIMDALL's tools
    # ------------------------------------------------------------------

    async def generate_idea(self, context: dict) -> IdeaResult:
        """Research trending niches and return a product idea."""
        from crew.tools import generate_niche_idea

        raw = generate_niche_idea()  # sync function - no await
        if not raw:
            # Fallback idea so the pipeline never stalls
            return IdeaResult(
                title="Cottagecore Wildflower Tote Bag",
                niche="cottagecore",
                product_type="tote bag",
                keywords=["cottagecore", "wildflower", "botanical", "tote bag", "aesthetic"],
            )

        return IdeaResult(
            title=raw.get("title", ""),
            niche=raw.get("niche", "general"),
            product_type=raw.get("productType", "t-shirt"),
            keywords=raw.get("keywords", []),
            description=raw.get("description", ""),
        )

    # ------------------------------------------------------------------
    # generate_asset — VULCAN generates design artwork via Leonardo
    # ------------------------------------------------------------------

    async def generate_asset(self, idea: IdeaResult, context: dict) -> AssetResult:
        """Generate 2 Leonardo design variants for the idea."""
        from crew.pipeline import generate_variants, _cache_image_locally
        import uuid as _uuid

        try:
            raw_urls = await generate_variants(
                idea.title,
                niche=idea.niche,
                n=2,
                product_type=idea.product_type,
            )
        except Exception as e:
            return AssetResult(success=False, error=str(e), idea=idea)

        if not raw_urls:
            return AssetResult(
                image_urls=[
                    "https://via.placeholder.com/1024x1024/1a1a2e/gold?text=Demo+Design",
                ],
                metadata={"demo": True},
                idea=idea,
            )

        return AssetResult(
            image_urls=raw_urls,
            metadata={"generator": "leonardo", "niche": idea.niche},
            idea=idea,
        )

    # ------------------------------------------------------------------
    # publish — VULCAN uploads to Printify, LOKI creates Etsy listing
    # ------------------------------------------------------------------

    async def publish(self, asset: AssetResult, context: dict) -> PublishResult:
        """Upload design to Printify, create product, list on Etsy."""
        from integrations.printify import upload_image, create_product, publish_product
        from integrations.etsy import (
            create_listing, build_tags, build_title,
            build_description, LISTING_FEE,
        )
        import memory.pricing_intel as pricing_intel

        idea = asset.idea
        image_url = asset.primary_image
        design_id = uuid.uuid4().hex[:12]

        # -- Pricing --
        price_usd = pricing_intel.get_suggested_price(
            idea.niche, idea.product_type, floor=12.99
        )
        if price_usd <= 12.99:
            price_usd = 34.99
        price_usd = round(min(max(price_usd * 0.90, 12.99), 59.99), 2)

        # -- Printify upload + product --
        try:
            img_result = await upload_image(image_url, filename=f"{design_id}.png")
            image_id = img_result["id"]
            demo_img = img_result.get("demo", False)
        except Exception as e:
            return PublishResult(error=f"Printify image upload failed: {e}", demo=True)

        description = build_description(
            idea.title, idea.niche, idea.keywords,
            product_type=idea.product_type,
        )
        try:
            product_result = await create_product(
                title=idea.title,
                description=description,
                image_id=image_id,
                product_type=idea.product_type,
                price_cents=int(price_usd * 100),
            )
            product_id = product_result["id"]
            demo_product = product_result.get("demo", True)
        except Exception as e:
            return PublishResult(error=f"Printify product creation failed: {e}", demo=True)

        if not demo_product:
            try:
                await publish_product(product_id)
            except Exception:
                pass

        # -- Etsy listing --
        try:
            etsy_title = build_title(
                idea.title, idea.niche,
                product_type=idea.product_type,
                keywords=idea.keywords,
            )
            etsy_tags = build_tags(idea.niche, idea.keywords, product_type=idea.product_type)
            etsy_desc = build_description(
                idea.title, idea.niche, idea.keywords,
                product_type=idea.product_type,
                price_usd=price_usd,
            )
            listing_result = await create_listing(
                title=etsy_title,
                description=etsy_desc,
                tags=etsy_tags,
                price_usd=price_usd,
            )
            listing_id = str(listing_result.get("listing_id", "N/A"))
            listing_demo = listing_result.get("demo", False)
            listing_url = listing_result.get(
                "url", f"https://www.etsy.com/listing/{listing_id}"
            )
        except Exception as e:
            listing_id = f"demo_{uuid.uuid4().hex[:6]}"
            listing_demo = True
            listing_url = ""

        return PublishResult(
            listing_id=listing_id,
            product_id=product_id,
            url=listing_url,
            price_usd=price_usd,
            demo=demo_product or listing_demo,
            metadata={
                "image_id": image_id,
                "etsy_tags": etsy_tags if "etsy_tags" in dir() else [],
            },
        )

    # ------------------------------------------------------------------
    # track_revenue — VAULT logs costs
    # ------------------------------------------------------------------

    async def track_revenue(self, publish_result: PublishResult, context: dict) -> dict:
        from integrations.etsy import LISTING_FEE
        import memory.obsidian as mem

        state = context.get("state")
        price_usd = publish_result.price_usd
        printify_base = 8.50
        etsy_txn_fee = round(price_usd * 0.065, 2)
        total_expense = round(printify_base + LISTING_FEE + etsy_txn_fee, 2)
        expected_revenue = price_usd

        if not publish_result.demo and state:
            txn = {
                "id": str(uuid.uuid4()),
                "type": "expense",
                "amount": total_expense,
                "description": f"Etsy+Printify: {publish_result.listing_id}",
                "source": "etsy_printify",
                "breakdown": {
                    "printify_base": printify_base,
                    "etsy_listing_fee": LISTING_FEE,
                    "etsy_txn_fee": etsy_txn_fee,
                },
                "timestamp": datetime.now().isoformat(),
            }
            state.vault["transactions"].append(txn)
            state.recalculate_vault()
            state.save_vault()

        return {
            "expense": total_expense,
            "expected_revenue": expected_revenue,
            "breakdown": {
                "printify_base": printify_base,
                "etsy_listing_fee": LISTING_FEE,
                "etsy_txn_fee": etsy_txn_fee,
            },
        }
