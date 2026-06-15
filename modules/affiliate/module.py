"""
modules/affiliate/module.py
============================
BusinessModule for affiliate marketing content sites.

Business model:
  - HEIMDALL finds high-CPC, low-competition keywords (Amazon, ClickBank, CJ)
  - VULCAN writes SEO review articles via Claude/OpenAI
  - LOKI publishes the article to a CMS / static site and posts to social
  - VAULT tracks content creation cost vs affiliate commission estimates

Current status: STUB — runs end-to-end in demo mode, generates real article drafts.
To activate: set WORDPRESS_URL + WORDPRESS_APP_PASSWORD env vars for auto-publishing.

Affiliate programs integrated (demo):
  Amazon Associates, ClickBank, ShareASale, CJ Affiliate
"""
from __future__ import annotations

import uuid
from datetime import datetime

from core.business_module import BusinessModule, IdeaResult, AssetResult, PublishResult


_AFFILIATE_NICHES = [
    ("Best Standing Desks Under $300 — 2026 Buyer's Guide", "home office", "review article", "amazon"),
    ("10 Best Air Purifiers for Allergies (Tested & Ranked)", "health", "review article", "amazon"),
    ("Top 7 Protein Powders for Women — 2026 Review", "fitness", "review article", "amazon"),
    ("Best Dividend ETFs for Passive Income in 2026", "personal finance", "informational", "clickbank"),
    ("Complete Guide to Passive Income with Print on Demand", "make money online", "informational", "clickbank"),
    ("Best Budget Mirrorless Cameras for Beginners", "photography", "review article", "amazon"),
    ("Top Sleep Supplements That Actually Work", "wellness", "review article", "shareasale"),
]


class AffiliateModule(BusinessModule):

    MODULE_ID   = "affiliate"
    NAME        = "Affiliate Content"
    ICON        = "💰"
    DESCRIPTION = "SEO review articles and informational content that earn affiliate commissions."
    SUPPORTS_DESIGN_APPROVAL = True  # Commander approves article draft before publishing

    def required_env_vars(self) -> list[str]:
        return ["ANTHROPIC_API_KEY"]  # WORDPRESS_URL, WORDPRESS_APP_PASSWORD for auto-publish

    async def validate_credentials(self) -> dict[str, bool]:
        return {v: self._has_env(v) for v in self.required_env_vars()}

    # ------------------------------------------------------------------
    # generate_idea — find high-value affiliate keyword
    # ------------------------------------------------------------------

    async def generate_idea(self, context: dict) -> IdeaResult:
        """
        In production: call Ahrefs/SEMrush API to find keywords with
        high CPC ($2-10+) and DR<30 ranking difficulty.
        Demo: rotate through curated high-converting affiliate niches.
        """
        import random
        title, niche, article_type, network = random.choice(_AFFILIATE_NICHES)
        return IdeaResult(
            title=title,
            niche=niche,
            product_type=article_type,
            keywords=self._extract_keywords(title, niche),
            description=f"{article_type.title()} targeting {niche} audience. Affiliate network: {network}.",
            metadata={
                "article_type": article_type,
                "affiliate_network": network,
                "target_word_count": 2500,
                "estimated_cpc": 2.50,
            },
        )

    # ------------------------------------------------------------------
    # generate_asset — write the article via Claude
    # ------------------------------------------------------------------

    async def generate_asset(self, idea: IdeaResult, context: dict) -> AssetResult:
        """
        Write a full SEO article using Claude. In production this also:
        - Generates featured image via Leonardo
        - Adds structured data / FAQ schema
        - Inserts affiliate link placeholders
        """
        article_content = await self._write_article(idea)

        # Generate a feature image too
        image_urls = []
        try:
            from integrations.leonardo import generate_design, leonardo_available
            if leonardo_available():
                result = await generate_design(
                    idea.title,
                    niche=idea.niche,
                    product_type="poster",
                    num_images=1,
                )
                if result.get("success") and result.get("images"):
                    image_urls = [img["url"] for img in result["images"]]
        except Exception:
            pass

        if not image_urls:
            image_urls = [
                f"https://via.placeholder.com/1200x630/1a1a2e/gold?text=Article+Feature+Image"
            ]

        return AssetResult(
            image_urls=image_urls,
            content=article_content,
            metadata={
                "word_count": len(article_content.split()),
                "affiliate_network": idea.metadata.get("affiliate_network", "amazon"),
                "article_type": idea.metadata.get("article_type", "review article"),
            },
            idea=idea,
        )

    # ------------------------------------------------------------------
    # publish — post to WordPress / CMS
    # ------------------------------------------------------------------

    async def publish(self, asset: AssetResult, context: dict) -> PublishResult:
        """
        Publish article to WordPress via REST API.
        Demo mode when WORDPRESS_URL is not configured.
        """
        import httpx

        idea = asset.idea
        wp_url = self._env("WORDPRESS_URL")
        wp_user = self._env("WORDPRESS_USERNAME")
        wp_pass = self._env("WORDPRESS_APP_PASSWORD")
        is_demo = not (wp_url and wp_user and wp_pass)

        if is_demo:
            slug = idea.title.lower().replace(" ", "-").replace("'", "")[:60]
            post_id = uuid.uuid4().hex[:8]
            return PublishResult(
                listing_id=post_id,
                product_id=post_id,
                url=f"https://{wp_url or 'your-blog.com'}/best-{slug[:30]}",
                price_usd=0.0,
                demo=True,
                metadata={
                    "word_count": asset.metadata.get("word_count", 0),
                    "affiliate_network": asset.metadata.get("affiliate_network", "amazon"),
                },
            )

        try:
            import base64
            credentials = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{wp_url}/wp-json/wp/v2/posts",
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "title": idea.title,
                        "content": asset.content,
                        "status": "publish",
                        "categories": [],
                        "tags": idea.keywords[:5],
                        "excerpt": idea.description[:200],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return PublishResult(
                    listing_id=str(data["id"]),
                    product_id=str(data["id"]),
                    url=data.get("link", ""),
                    price_usd=0.0,
                    demo=False,
                    metadata=asset.metadata,
                )
        except Exception as e:
            return PublishResult(error=str(e), demo=True)

    # ------------------------------------------------------------------
    # track_revenue — affiliate commission estimates
    # ------------------------------------------------------------------

    async def track_revenue(self, publish_result: PublishResult, context: dict) -> dict:
        """
        Affiliate content has near-zero hard cost (just AI writing time).
        Revenue is commission-based: estimate based on niche CPC and expected traffic.
        """
        state = context.get("state")
        # Writing cost estimate (API tokens + time)
        expense = 0.05
        # Conservative estimate: 100 monthly visitors, 3% CTR, $30 avg order, 4% commission
        estimated_monthly = round(100 * 0.03 * 30 * 0.04, 2)

        if not publish_result.demo and state:
            txn = {
                "id": str(uuid.uuid4()),
                "type": "expense",
                "amount": expense,
                "description": f"Affiliate article: {publish_result.listing_id}",
                "source": "affiliate",
                "timestamp": datetime.now().isoformat(),
            }
            state.vault["transactions"].append(txn)
            state.recalculate_vault()
            state.save_vault()

        return {
            "expense": expense,
            "expected_revenue": estimated_monthly,
            "note": "Commission-based — actual revenue depends on traffic and conversions",
            "breakdown": {"api_cost": expense, "estimated_monthly_commission": estimated_monthly},
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_article(self, idea: IdeaResult) -> str:
        """Write article content via Claude or fall back to a structured template."""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._env("ANTHROPIC_API_KEY"))
            word_count = idea.metadata.get("target_word_count", 2000)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Write a detailed, SEO-optimized {idea.product_type} for the topic: "
                        f"'{idea.title}'\n\n"
                        f"Target audience: {idea.niche} enthusiasts.\n"
                        f"Target length: {word_count} words.\n"
                        f"Include: intro, 5-7 top picks with pros/cons, buying guide, FAQ, conclusion.\n"
                        f"Insert [AFFILIATE_LINK] placeholders where product links would go.\n"
                        f"Write in a helpful, expert tone. No filler. Real value."
                    ),
                }],
            )
            return response.content[0].text
        except Exception as e:
            print(f"[AFFILIATE] Article generation failed: {e}")
            return self._template_article(idea)

    def _template_article(self, idea: IdeaResult) -> str:
        """Minimal fallback template when Claude is unavailable."""
        return (
            f"# {idea.title}\n\n"
            f"## Introduction\n"
            f"Looking for the best options in {idea.niche}? "
            f"We tested the top products and ranked them for you.\n\n"
            f"## Our Top Picks\n\n"
            f"### 1. Best Overall — [AFFILIATE_LINK]\n"
            f"**Pros:** Quality, durability, value\n**Cons:** Price\n\n"
            f"### 2. Best Budget — [AFFILIATE_LINK]\n"
            f"**Pros:** Affordable, reliable\n**Cons:** Fewer features\n\n"
            f"## Buying Guide\n"
            f"What to look for when choosing {idea.niche} products...\n\n"
            f"## FAQ\n"
            f"**Q: What's the best option?** A: It depends on your budget.\n\n"
            f"## Conclusion\n"
            f"We recommend starting with our top pick for best results.\n"
        )

    def _extract_keywords(self, title: str, niche: str) -> list[str]:
        """Extract likely search keywords from the title."""
        words = [w.lower() for w in title.split() if len(w) > 3]
        return list(dict.fromkeys([niche] + words))[:10]
