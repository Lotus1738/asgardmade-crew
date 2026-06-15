"""
core/pipeline_runner.py
=======================
Dispatches the idea → asset → publish pipeline for ANY registered BusinessModule.

This replaces direct calls to crew/pipeline.py functions. The server routes to
this runner, which resolves the correct module from the registry and executes
each step — logging to the HUD WebSocket manager throughout.

Usage:
    from core.pipeline_runner import PipelineRunner

    runner = PipelineRunner(manager, state)

    # Step 1: idea approved
    await runner.run_idea_pipeline(idea_dict, module_id="etsy_printify")

    # Step 2: design/asset approved
    await runner.run_asset_pipeline(asset_dict, module_id="etsy_printify")

    # Fully autonomous (no approvals)
    await runner.run_autonomous(module_id="etsy_printify", count=3)
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from core.registry import registry
from core.business_module import IdeaResult, AssetResult, PublishResult

if TYPE_CHECKING:
    from server import ConnectionManager, AppState


class PipelineRunner:
    """
    Orchestrates the full pipeline for any BusinessModule.
    Shares the WebSocket manager and AppState from server.py.
    """

    def __init__(self, manager: "ConnectionManager", state: "AppState") -> None:
        self.manager = manager
        self.state = state

    # ------------------------------------------------------------------
    # Step 1: Idea → Design/Asset Queue
    # ------------------------------------------------------------------

    async def run_idea_pipeline(
        self,
        idea_dict: dict,
        module_id: str | None = None,
    ) -> None:
        """
        Triggered when commander approves an idea card.
        Resolves the module, calls generate_asset(), and queues results for
        the second approval step (or auto-publishes if the module skips approval).
        """
        module = registry.get_or_default(module_id or idea_dict.get("module_id"))

        await self._log(module.ICON, "VULCAN",
                        f"[{module.NAME}] Idea approved: '{idea_dict.get('title')}'. "
                        f"Generating {module.NAME} asset now...")

        idea = IdeaResult.from_dict(idea_dict)
        idea.module_id = module.MODULE_ID

        ctx = self._build_context()

        try:
            await module.on_idea_approved(idea, ctx)
            asset = await module.generate_asset(idea, ctx)
        except Exception as e:
            await self._log(module.ICON, "VULCAN",
                            f"[{module.NAME}] Asset generation failed: {e}", "error")
            return

        if not asset.success:
            await self._log(module.ICON, "VULCAN",
                            f"[{module.NAME}] Asset generation returned error: {asset.error}", "error")
            return

        # Queue assets for approval (or auto-publish for autonomous modules)
        design_items = []
        for i, img_url in enumerate(asset.image_urls or [""]):
            design_item = {
                "id": str(uuid.uuid4()),
                "type": "design",
                "status": "pending",
                "module_id": module.MODULE_ID,
                "module_name": module.NAME,
                "ideaId": idea_dict.get("id", ""),
                "ideaTitle": idea.title,
                "niche": idea.niche,
                "productType": idea.product_type,
                "imageUrl": img_url,
                "content": asset.content[:500] if asset.content else "",
                "content_path": asset.content_path,
                "variantIndex": i + 1,
                "demo": False,
                "keywords": idea.keywords,
                "asset_metadata": asset.metadata,
                "createdAt": datetime.now().isoformat(),
            }
            design_items.append(design_item)
            self.state.queue["designs"].append(design_item)

        self.state.save_queue()

        await self._log(module.ICON, "VULCAN",
                        f"[{module.NAME}] {len(design_items)} asset(s) queued for your approval.")

        await self.manager.broadcast({
            "type": "approval_queue",
            "agent": "VULCAN",
            "data": {"category": "designs", "items": design_items},
        })

        # Fully autonomous modules skip the approval step
        if not module.SUPPORTS_DESIGN_APPROVAL:
            for item in design_items:
                item["status"] = "approved"
                await self.run_asset_pipeline(item, module_id=module.MODULE_ID)

    # ------------------------------------------------------------------
    # Step 2: Asset Approved → Publish
    # ------------------------------------------------------------------

    async def run_asset_pipeline(
        self,
        asset_dict: dict,
        module_id: str | None = None,
    ) -> None:
        """
        Triggered when commander approves an asset/design card.
        Calls module.publish() and then module.track_revenue().
        """
        module = registry.get_or_default(module_id or asset_dict.get("module_id"))

        idea = IdeaResult(
            title=asset_dict.get("ideaTitle", ""),
            niche=asset_dict.get("niche", "general"),
            product_type=asset_dict.get("productType", "t-shirt"),
            keywords=asset_dict.get("keywords", []),
            module_id=module.MODULE_ID,
        )

        asset = AssetResult(
            image_urls=[asset_dict["imageUrl"]] if asset_dict.get("imageUrl") else [],
            content=asset_dict.get("content", ""),
            content_path=asset_dict.get("content_path", ""),
            metadata=asset_dict.get("asset_metadata", {}),
            idea=idea,
        )

        ctx = self._build_context()
        ctx["asset_dict"] = asset_dict  # carry raw dict for modules that need it

        await self._log(module.ICON, "LOKI",
                        f"[{module.NAME}] Asset approved. Publishing '{idea.title}'...")

        try:
            await module.on_asset_approved(asset, ctx)
            publish_result = await module.publish(asset, ctx)
        except Exception as e:
            await self._log(module.ICON, "LOKI",
                            f"[{module.NAME}] Publish failed: {e}", "error")
            return

        await self._log(
            module.ICON, "LOKI",
            f"[{module.NAME}] Published: '{idea.title}' → "
            f"{'LIVE' if publish_result.is_live else 'DEMO'} "
            f"{'@ $' + str(publish_result.price_usd) if publish_result.price_usd else ''}. "
            f"{'URL: ' + publish_result.url if publish_result.url else ''}"
        )

        # Revenue tracking
        try:
            rev = await module.track_revenue(publish_result, ctx)
            await self._log(module.ICON, "VAULT",
                            f"[{module.NAME}] Expense logged: ${rev.get('expense', 0):.2f}. "
                            f"Expected revenue: ${rev.get('expected_revenue', 0):.2f}.")
        except Exception as e:
            await self._log(module.ICON, "VAULT",
                            f"[{module.NAME}] Revenue tracking failed: {e}", "warning")

        # Broadcast publish event so HUD updates
        await self.manager.broadcast({
            "type": "loki_published",
            "agent": "LOKI",
            "module_id": module.MODULE_ID,
            "data": {
                "listingId": publish_result.listing_id,
                "productId": publish_result.product_id,
                "url": publish_result.url,
                "price": publish_result.price_usd,
                "title": idea.title,
                "module": module.NAME,
                "demo": publish_result.demo,
            },
        })

    # ------------------------------------------------------------------
    # Autonomous mode — no approvals, fires all steps in sequence
    # ------------------------------------------------------------------

    async def run_autonomous(
        self,
        module_id: str | None = None,
        count: int = 3,
    ) -> dict:
        """
        Fully autonomous run for any module. Loops count times through:
        generate_idea → generate_asset → publish → track_revenue.
        Used by the daily scheduled task.
        """
        module = registry.get_or_default(module_id)
        ctx = self._build_context()

        published = []
        errors = []

        await self._log(module.ICON, "ODIN",
                        f"[{module.NAME}] Autonomous run starting: {count} target(s).")

        for i in range(count):
            try:
                await self._log(module.ICON, "HEIMDALL",
                                f"[{module.NAME}] Run {i+1}/{count}: generating idea...")
                idea = await module.generate_idea(ctx)
                idea.module_id = module.MODULE_ID

                await self._log(module.ICON, "VULCAN",
                                f"[{module.NAME}] Run {i+1}: creating asset for '{idea.title}'...")
                asset = await module.generate_asset(idea, ctx)
                if not asset.success:
                    raise RuntimeError(f"Asset generation failed: {asset.error}")

                await self._log(module.ICON, "LOKI",
                                f"[{module.NAME}] Run {i+1}: publishing '{idea.title}'...")
                pub = await module.publish(asset, ctx)

                rev = await module.track_revenue(pub, ctx)

                published.append({
                    "title": idea.title,
                    "niche": idea.niche,
                    "module": module.MODULE_ID,
                    "listing_id": pub.listing_id,
                    "price_usd": pub.price_usd,
                    "demo": pub.demo,
                })

                await self._log(module.ICON, "ODIN",
                                f"[{module.NAME}] Run {i+1} done: '{idea.title}' published. "
                                f"Expense: ${rev.get('expense', 0):.2f}.")

            except Exception as e:
                msg = f"[{module.NAME}] Run {i+1} error: {type(e).__name__}: {e}"
                errors.append(msg)
                await self._log(module.ICON, "ODIN", msg, "error")

            if i < count - 1:
                await asyncio.sleep(2)

        summary = {
            "module": module.MODULE_ID,
            "published": len(published),
            "errors": len(errors),
            "listings": published,
            "error_details": errors,
        }

        await self._log(module.ICON, "ODIN",
                        f"[{module.NAME}] Autonomous run complete: "
                        f"{len(published)}/{count} published.")
        await self.manager.broadcast({
            "type": "autonomous_pipeline_complete",
            "data": summary,
        })
        return summary

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_context(self) -> dict:
        """Runtime context passed to every module method."""
        return {
            "manager": self.manager,
            "state": self.state,
        }

    async def _log(
        self,
        icon: str,
        agent: str,
        message: str,
        level: str = "info",
    ) -> None:
        await self.manager.broadcast({
            "type": "agent_log",
            "agent": agent,
            "message": message,
            "level": level,
            "timestamp": datetime.now().isoformat(),
        })
