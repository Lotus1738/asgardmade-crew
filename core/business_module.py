"""
core/business_module.py
=======================
Abstract base class for every business type in AsgardMade Pantheon.

Any new business (Etsy, KDP, Shopify, Affiliate, etc.) must subclass
BusinessModule and implement the four core methods. The registry and
pipeline runner work entirely through this interface — they never import
business-specific code directly.

Quickstart for a new module:
    from core.business_module import BusinessModule, IdeaResult, AssetResult, PublishResult

    class MyModule(BusinessModule):
        MODULE_ID   = "my_module"
        NAME        = "My Business"
        ICON        = "🚀"
        DESCRIPTION = "What this business does in one sentence."

        async def generate_idea(self, context: dict) -> IdeaResult: ...
        async def generate_asset(self, idea: IdeaResult, context: dict) -> AssetResult: ...
        async def publish(self, asset: AssetResult, context: dict) -> PublishResult: ...
        async def track_revenue(self, publish_result: PublishResult, context: dict) -> dict: ...
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Shared result types — passed between pipeline steps
# ---------------------------------------------------------------------------

@dataclass
class IdeaResult:
    """Output of generate_idea(). Describes what product/content to create."""
    title: str
    niche: str
    product_type: str
    keywords: list[str] = field(default_factory=list)
    description: str = ""
    metadata: dict = field(default_factory=dict)
    # Module that produced this idea — set automatically by pipeline runner
    module_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "niche": self.niche,
            "product_type": self.product_type,
            "keywords": self.keywords,
            "description": self.description,
            "metadata": self.metadata,
            "module_id": self.module_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IdeaResult":
        return cls(
            title=d.get("title", ""),
            niche=d.get("niche", "general"),
            product_type=d.get("product_type", d.get("productType", "t-shirt")),
            keywords=d.get("keywords", []),
            description=d.get("description", ""),
            metadata=d.get("metadata", {}),
            module_id=d.get("module_id", ""),
            created_at=d.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class AssetResult:
    """Output of generate_asset(). The deliverable that gets published."""
    # For image-based products: list of image URLs or local paths
    image_urls: list[str] = field(default_factory=list)
    # For text-based products (KDP, affiliate): body text or file path
    content: str = ""
    content_path: str = ""
    # Structured data any module wants to carry forward
    metadata: dict = field(default_factory=dict)
    # Did generation succeed?
    success: bool = True
    error: str = ""
    # Source idea
    idea: IdeaResult = field(default_factory=IdeaResult)

    @property
    def primary_image(self) -> str:
        return self.image_urls[0] if self.image_urls else ""

    def to_dict(self) -> dict:
        return {
            "image_urls": self.image_urls,
            "content": self.content[:500] if self.content else "",
            "content_path": self.content_path,
            "metadata": self.metadata,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class PublishResult:
    """Output of publish(). Where the product ended up."""
    # Marketplace-specific listing/product identifier
    listing_id: str = ""
    product_id: str = ""
    # Public URL (Etsy listing, Amazon page, affiliate link, etc.)
    url: str = ""
    # Price actually set
    price_usd: float = 0.0
    # Was this a live publish or demo mode?
    demo: bool = True
    # Any error message
    error: str = ""
    # Free-form extras (Printify product ID, ASIN, etc.)
    metadata: dict = field(default_factory=dict)
    published_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_live(self) -> bool:
        return not self.demo and not self.error

    def to_dict(self) -> dict:
        return {
            "listing_id": self.listing_id,
            "product_id": self.product_id,
            "url": self.url,
            "price_usd": self.price_usd,
            "demo": self.demo,
            "error": self.error,
            "metadata": self.metadata,
            "published_at": self.published_at,
        }


# ---------------------------------------------------------------------------
# BusinessModule — the interface every module implements
# ---------------------------------------------------------------------------

class BusinessModule(ABC):
    """
    Abstract base for a self-contained business pipeline.

    Class attributes (set on each subclass):
        MODULE_ID   — unique snake_case identifier, e.g. "etsy_printify"
        NAME        — human-readable name shown in the HUD
        ICON        — emoji used in the UI
        DESCRIPTION — one-line description of what this business does
        SUPPORTS_DESIGN_APPROVAL — True if the module uses a 2-step
                      idea→approve→design→approve flow (like Etsy).
                      False for fully autonomous modules (like KDP).
    """

    MODULE_ID: str = "base"
    NAME: str = "Base Module"
    ICON: str = "📦"
    DESCRIPTION: str = ""
    SUPPORTS_DESIGN_APPROVAL: bool = True

    # ------------------------------------------------------------------
    # Core pipeline methods — must be implemented by every module
    # ------------------------------------------------------------------

    @abstractmethod
    async def generate_idea(self, context: dict) -> IdeaResult:
        """
        Research and return a profitable product/content idea.

        Args:
            context: runtime data — env vars, state, HUD manager reference, etc.

        Returns:
            IdeaResult describing what to create next.
        """
        ...

    @abstractmethod
    async def generate_asset(self, idea: IdeaResult, context: dict) -> AssetResult:
        """
        Create the actual deliverable for the idea.

        For Etsy/Printify: generate design image(s) via Leonardo.
        For KDP: write manuscript + cover image.
        For Shopify: generate product photos + copy.
        For Affiliate: write review article + SEO content.

        Args:
            idea:    the approved IdeaResult from generate_idea().
            context: runtime data.

        Returns:
            AssetResult containing image URLs, content, or file paths.
        """
        ...

    @abstractmethod
    async def publish(self, asset: AssetResult, context: dict) -> PublishResult:
        """
        Upload and publish the asset to the target marketplace/platform.

        For Etsy/Printify: upload to Printify CDN, create product, list on Etsy.
        For KDP: upload manuscript to KDP, set price, publish.
        For Shopify: create product, upload images, set variants.
        For Affiliate: publish article to blog/CMS, post to social.

        Args:
            asset:   the AssetResult from generate_asset().
            context: runtime data including pricing intel, tags, etc.

        Returns:
            PublishResult with listing ID, URL, price, and demo flag.
        """
        ...

    @abstractmethod
    async def track_revenue(self, publish_result: PublishResult, context: dict) -> dict:
        """
        Log expenses and expected revenue for this publish event to the Vault.

        Returns a dict with at minimum:
            {"expense": float, "expected_revenue": float, "breakdown": dict}
        """
        ...

    # ------------------------------------------------------------------
    # Optional hooks — override if the module needs them
    # ------------------------------------------------------------------

    async def on_idea_approved(self, idea: IdeaResult, context: dict) -> None:
        """Called after the commander approves an idea. Hook for pre-asset work."""
        pass

    async def on_asset_approved(self, asset: AssetResult, context: dict) -> None:
        """Called after the commander approves a generated asset."""
        pass

    async def validate_credentials(self) -> dict[str, bool]:
        """
        Check that all required env vars are present and non-empty.

        Returns:
            {"PRINTIFY_API_KEY": True, "ETSY_API_KEY": False, ...}
        """
        return {}

    def required_env_vars(self) -> list[str]:
        """
        List env vars this module needs. Used by the HUD to show setup status.
        Override in each subclass.
        """
        return []

    # ------------------------------------------------------------------
    # Shared helpers available to all modules
    # ------------------------------------------------------------------

    def _env(self, key: str, default: str = "") -> str:
        """Read a Railway env var safely — always strips trailing whitespace."""
        return os.getenv(key, default).strip()

    def _has_env(self, *keys: str) -> bool:
        """True only if all listed env vars are non-empty."""
        return all(bool(self._env(k)) for k in keys)

    def meta(self) -> dict:
        """Return module metadata dict for the registry and HUD."""
        return {
            "module_id": self.MODULE_ID,
            "name": self.NAME,
            "icon": self.ICON,
            "description": self.DESCRIPTION,
            "supports_design_approval": self.SUPPORTS_DESIGN_APPROVAL,
            "required_env_vars": self.required_env_vars(),
        }

    def __repr__(self) -> str:
        return f"<BusinessModule {self.MODULE_ID}: {self.NAME}>"
