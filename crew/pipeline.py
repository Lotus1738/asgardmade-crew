"""
Orchestration pipeline: idea approval → design generation → Printify → Etsy listing.
Each step broadcasts live updates to the HUD via the WebSocket manager.
"""

import asyncio
import uuid
import os
from datetime import datetime
from typing import TYPE_CHECKING

try:
    from integrations.higgsfield import generate_variants as _gen_variants
    _GENERATOR = "Higgsfield"
except ImportError:
    from integrations.dalle import generate_variants as _gen_variants
    _GENERATOR = "DALL-E"

generate_variants = _gen_variants
from integrations.printify import upload_image, create_product, publish_product, generate_mockups
from integrations.etsy import create_listing, build_tags, build_title, build_description, LISTING_FEE
from integrations import pinterest, discord
from integrations.publisher import publish_everywhere, format_publish_log
import memory.obsidian as mem
import memory.ab_tests as ab_tests
import memory.pricing_intel as pricing_intel

if TYPE_CHECKING:
    from server import ConnectionManager, AppState


async def run_idea_pipeline(
    idea: dict,
    manager: "ConnectionManager",
    state: "AppState",
) -> None:
    """
    Full pipeline triggered when commander approves an idea:
    1. Heimdall briefs Vulcan
    2. Vulcan generates DALL-E designs (2 variants)
    3. Designs go to approval queue
    """
    idea_id = idea["id"]
    title = idea["title"]
    niche = idea.get("niche", "general")
    product_type = idea.get("productType", "t-shirt")

    await _log(manager, "HEIMDALL",
               f"Idea '{title}' approved. Briefing Vulcan now — niche: {niche}, product: {product_type}.")
    await _update_status(manager, state, "HEIMDALL", "working",
                         f"Briefing Vulcan on '{title}'")

    await asyncio.sleep(0.5)

    await _log(manager, "VULCAN",
               f"Received brief from Heimdall. Generating 2 {_GENERATOR} variants for '{title}'.")
    await _update_status(manager, state, "VULCAN", "working",
                         f"Generating designs for '{title}'")

    try:
        variants = await generate_variants(title, niche, product_type, count=2)
    except Exception as e:
        await _log(manager, "VULCAN", f"Design generation failed: {e}. Using demo placeholders.", "warning")
        try:
            from integrations.higgsfield import DEMO_IMAGES as _DEMO
        except ImportError:
            from integrations.dalle import DEMO_IMAGES as _DEMO
        variants = [
            {"url": _DEMO[0], "prompt": f"Demo design for {title}", "demo": True},
            {"url": _DEMO[1], "prompt": f"Demo design variant 2 for {title}", "demo": True},
        ]

    design_items = []
    for i, variant in enumerate(variants):
        design = {
            "id": str(uuid.uuid4()),
            "type": "design",
            "status": "pending",
            "ideaId": idea_id,
            "ideaTitle": title,
            "niche": niche,
            "productType": product_type,
            "imageUrl": variant["url"],
            "prompt": variant.get("prompt", ""),
            "variantIndex": i + 1,
            "demo": variant.get("demo", False),
            "keywords": idea.get("keywords", []),
            "createdAt": datetime.now().isoformat(),
        }
        design_items.append(design)
        state.queue["designs"].append(design)
        try:
            mem.vulcan_write_generated(design)
        except Exception:
            pass

    state.save_queue()

    await _log(manager, "VULCAN",
               f"Generated {len(design_items)} design variants for '{title}'. "
               f"{f'{_GENERATOR} live.' if not variants[0].get('demo') else f'Demo mode — configure API key for {_GENERATOR}.'} "
               f"Queued for commander review.")
    await _update_status(manager, state, "VULCAN", "active",
                         f"{len(design_items)} designs queued for '{title}'")
    await _award_xp(manager, state, "VULCAN", 40, "design_generation")
    await _award_xp(manager, state, "HEIMDALL", 25, "idea_pipeline")

    # Record VULCAN's design generation outcome so the brain can learn what styles
    # the commander approves vs. rejects. VULCAN was the only pipeline agent that
    # generated output without any brain outcome at the generation stage.
    try:
        import memory.brain as _brain_v
        _is_demo_variants = bool(variants) and variants[0].get("demo", False)
        _brain_v.record_outcome(
            "VULCAN",
            f"Generated {len(design_items)} design variant(s) for '{title}' ({niche}, {product_type})",
            f"{'Demo placeholders — configure API key for ' + _GENERATOR if _is_demo_variants else _GENERATOR + ' designs generated successfully — awaiting commander review'}",
            5 if _is_demo_variants else 8,
        )
    except Exception:
        pass

    await manager.broadcast({
        "type": "approval_queue",
        "agent": "VULCAN",
        "data": {"category": "designs", "items": design_items},
    })

    await _log(manager, "ODIN",
               f"Pipeline step 1 complete. '{title}' has {len(design_items)} designs awaiting your approval. "
               f"Review the DESIGN QUEUE tab.")


async def run_design_pipeline(
    design: dict,
    manager: "ConnectionManager",
    state: "AppState",
) -> None:
    """
    Pipeline triggered when commander approves a design:
    1. Vulcan uploads to Printify
    2. Loki creates Etsy listing
    3. Vault logs the transaction
    4. Odin confirms completion
    """
    design_id = design["id"]
    title = design["ideaTitle"]
    niche = design.get("niche", "general")
    product_type = design.get("productType", "t-shirt")
    image_url = design["imageUrl"]
    keywords = design.get("keywords", [])
    # Use pricing intel to set a competitive price; fall back to $34.99 if no data
    _pricing_intel_text = pricing_intel.format_pricing_for_prompt(niche)
    _suggested = pricing_intel.get_suggested_price(niche, product_type, floor=12.99)
    if _suggested > 12.99:
        # Price 10% below niche average to maximize conversion speed
        price_usd = round(_suggested * 0.90, 2)
        price_usd = max(price_usd, 12.99)  # hard floor
        price_usd = min(price_usd, 59.99)  # ceiling cap — prevents corrupted pricing intel from listing at absurd prices
    else:
        price_usd = 34.99  # default when no intel available

    await _log(manager, "LOKI",
               f"Pricing intel for '{niche}': {_pricing_intel_text or 'no data yet'} → listing at ${price_usd:.2f}.")

    await _log(manager, "VULCAN",
               f"Design approved. Uploading '{title}' image to Printify CDN.")
    await _update_status(manager, state, "VULCAN", "working",
                         f"Uploading design to Printify")

    try:
        image_result = await upload_image(image_url, filename=f"{design_id}.png")
        image_id = image_result["id"]
        demo_mode = image_result.get("demo", False)
    except Exception as e:
        await _log(manager, "VULCAN", f"Printify image upload failed: {e}", "error")
        image_id = "demo_img"
        demo_mode = True

    await _log(manager, "VULCAN",
               f"Image uploaded {'(demo)' if demo_mode else ''}. Creating Printify product.")

    try:
        description = build_description(title, niche, keywords)
        product_result = await create_product(
            title=title,
            description=description,
            image_id=image_id,
            product_type=product_type,
            price_cents=int(price_usd * 100),
        )
        product_id = product_result["id"]
    except Exception as e:
        await _log(manager, "VULCAN", f"Printify product creation failed: {e}", "warning")
        product_id = f"demo_{uuid.uuid4().hex[:8]}"

    # ── Mockup generation ─────────────────────────────────────────────────────
    # Fetch Printify-generated mockup images after product creation.
    # Falls back to the raw design image URL if credentials are missing / demo run.
    mockup_urls: list[str] = []
    try:
        mockup_urls = await generate_mockups(product_id, image_url=image_url)
        if mockup_urls:
            await _log(manager, "VULCAN",
                       f"Mockup pipeline: {len(mockup_urls)} mockup image(s) generated for '{title}'.")
    except Exception as e:
        await _log(manager, "VULCAN", f"Mockup generation skipped: {e}", "warning")
        mockup_urls = [image_url]

    await manager.broadcast({
        "type": "vulcan_published",
        "agent": "VULCAN",
        "data": {"product": {"id": product_id}, "design_id": design_id},
    })

    if not product_id.startswith("demo_"):
        try:
            await publish_product(product_id)
        except Exception as e:
            await _log(manager, "VULCAN", f"Printify publish step: {e}", "warning")

    await _award_xp(manager, state, "VULCAN", 60, "product_created")

    # Record VULCAN brain outcome for the Printify upload stage so the brain
    # synthesis loop can learn which product types/designs upload successfully vs. fail.
    try:
        import memory.brain as _brain_vu
        _demo_prod = product_id.startswith("demo_")
        _brain_vu.record_outcome(
            "VULCAN",
            f"Uploaded design for '{title}' ({niche}, {product_type}) to Printify",
            f"{'Printify API unavailable — demo product ID' if _demo_prod else 'Printify product ' + product_id[:12] + ' created successfully'}",
            4 if _demo_prod else 9,
        )
    except Exception:
        pass

    await _update_status(manager, state, "VULCAN", "active",
                         f"Product {product_id[:12]} created for '{title}'")

    await _log(manager, "LOKI",
               f"Product ready from Vulcan. Creating Etsy listing for '{title}'.")
    await _update_status(manager, state, "LOKI", "working",
                         f"Creating Etsy listing for '{title}'")

    try:
        etsy_title = build_title(title, niche)
        etsy_tags = build_tags(niche, keywords)
        etsy_desc = build_description(title, niche, keywords)
        listing_result = await create_listing(
            title=etsy_title,
            description=etsy_desc,
            tags=etsy_tags,
            price_usd=price_usd,
        )
        listing_id = listing_result.get("listing_id", "N/A")
        listing_demo = listing_result.get("demo", False)
    except Exception as e:
        await _log(manager, "LOKI", f"Etsy listing creation failed: {e}", "warning")
        listing_id = f"demo_{uuid.uuid4().hex[:6]}"
        listing_demo = True
        etsy_tags = build_tags(niche, keywords)

    await _log(manager, "LOKI",
               f"Listing created {'(demo)' if listing_demo else ''}. "
               f"ID: {listing_id}. Tags: {len(etsy_tags)} applied. "
               f"Price: ${price_usd}. Listing fee logged to Vault.")

    # ── A/B title test creation ────────────────────────────────────────────────
    # Parse title_b from listing_result (LOKI may have returned it via AI response).
    # Falls back to a simple year-variant so every listing always has a test running.
    try:
        title_b = listing_result.get("title_b") or _make_title_b_fallback(etsy_title)
        ab_test = ab_tests.create_test(
            listing_id=str(listing_id),
            title_a=etsy_title,
            title_b=title_b,
            niche=niche,
        )
        await _log(manager, "LOKI",
                   f"[A/B] Test created for listing {listing_id}: "
                   f"\"{etsy_title}\" vs \"{title_b}\"")
    except Exception as _ab_err:
        print(f"[A/B] Test creation failed for listing {listing_id}: {_ab_err}")

    # ── Pinterest auto-pin ─────────────────────────────────────────────────────
    # Pin the listing to Pinterest using the first mockup image (or raw design).
    if not listing_demo:
        try:
            listing_url = listing_result.get("url", f"https://www.etsy.com/listing/{listing_id}")
            pin_image = (mockup_urls[0] if mockup_urls else image_url)
            pin_id = await pinterest.create_pin(
                title=etsy_title,
                description=etsy_desc,
                image_url=pin_image,
                link=listing_url,
            )
            if pin_id:
                await _log(manager, "LOKI",
                           f"Pinterest pin created (ID: {pin_id}) for '{title}'.")
        except Exception as e:
            await _log(manager, "LOKI", f"Pinterest pin skipped: {e}", "warning")

    # Feed listing success back to HEIMDALL's niche memory so future scoring improves
    try:
        import memory.brain as brain
        brain.record_outcome(
            "HEIMDALL",
            f"Niche: {niche} | Product: {product_type}",
            f"Listing published — '{title}' live on Etsy (ID {listing_id}). Niche confirmed converting.",
            9,
        )
    except Exception:
        pass

    try:
        mem.loki_write_listing(design, {
            "listing_id": listing_id,
            "title": etsy_title,
            "price": price_usd,
            "tags": etsy_tags,
            "demo": listing_demo,
        })
    except Exception:
        pass

    await manager.broadcast({
        "type": "loki_published",
        "agent": "LOKI",
        "data": {"listingId": listing_id, "price": price_usd, "title": etsy_title},
    })
    await _award_xp(manager, state, "LOKI", 50, "listing_created")
    await _update_status(manager, state, "LOKI", "active",
                         f"Listing {listing_id} live for '{title}'")

    # ── Multi-platform publish (Redbubble + Amazon Merch) ─────────────────────
    # Fire-and-forget after Etsy confirm. Never raises — each platform is independent.
    try:
        etsy_url = listing_result.get("url", f"https://www.etsy.com/listing/{listing_id}") if not listing_demo else None
        multi_results = await publish_everywhere(
            title=etsy_title,
            description=etsy_desc,
            tags=etsy_tags,
            image_url=image_url,
            etsy_url=etsy_url,
        )
        publish_summary = format_publish_log(multi_results)
        await _log(manager, "LOKI",
                   f"Multi-platform publish: {publish_summary}")
    except Exception as e:
        await _log(manager, "LOKI", f"Multi-platform publish error: {e}", "warning")

    # Record LOKI outcome so the brain can learn what listing approaches work
    try:
        import memory.brain as _brain
        _brain.record_outcome(
            "LOKI",
            f"Listed '{etsy_title}' | niche: {niche} | tags: {len(etsy_tags)} | price: ${price_usd}",
            f"{'LIVE' if not listing_demo else 'DEMO'} listing created — ID {listing_id}",
            7 if not listing_demo else 5,
        )
    except Exception:
        pass

    # Only log real production expenses — not demo/fallback runs where no money was spent.
    # Previously, Printify failures caused a real expense entry even though no product was
    # created, overstating costs and making P&L look worse than reality.
    is_demo_run = product_id.startswith("demo_") or listing_demo
    printify_cost = 8.50
    etsy_txn_fee = round(price_usd * 0.065, 2)
    total_expense = round(printify_cost + LISTING_FEE + etsy_txn_fee, 2)

    if not is_demo_run:
        txn = {
            "id": str(uuid.uuid4()),
            "type": "expense",
            "amount": total_expense,
            "description": f"Production cost: {title}",
            "source": "printify+etsy",
            "breakdown": {
                "printify_base": printify_cost,
                "etsy_listing_fee": LISTING_FEE,
                "etsy_txn_fee": etsy_txn_fee,
            },
            "timestamp": datetime.now().isoformat(),
        }
        state.vault["transactions"].append(txn)
        state.recalculate_vault()
        state.save_vault()
        try:
            mem.vault_write_transaction(txn)
        except Exception:
            pass
    else:
        await _log(manager, "VAULT",
                   f"Demo run — no real expense logged for '{title}'. "
                   f"Production cost (${total_expense}) only applies to live Printify+Etsy listings.")

    # Only log the real expense breakdown for production runs — demo runs already logged above.
    if not is_demo_run:
        await _log(manager, "VAULT",
                   f"Logged ${total_expense} expense for '{title}'. "
                   f"Breakdown: Printify ${printify_cost}, "
                   f"listing fee ${LISTING_FEE}, "
                   f"transaction fee ${etsy_txn_fee}. "
                   f"Net profit: ${state.vault['netProfit']:.2f}.")
    await _award_xp(manager, state, "VAULT", 20, "expense_logged")

    vault_report = _build_vault_report(state)
    await manager.broadcast({"type": "vault_report", "data": vault_report})

    await _log(manager, "ODIN",
               f"Pipeline complete for '{title}'. "
               f"Product {product_id[:12]} → Listing {listing_id}. "
               f"Running P&L: ${state.vault['netProfit']:.2f} net. "
               f"All agents confirmed.")


    strategy_text = (
        f"New product live: '{title}'. Total products in pipeline: "
        f"{len([d for d in state.queue['designs'] if d['status'] == 'approved'])}. "
        f"Current margin: {state.vault.get('profitMarginPct', 0):.1f}%."
    )
    state.strategy_count += 1
    await manager.broadcast({
        "type": "odin_strategy",
        "data": {"strategy": strategy_text, "strategyCount": state.strategy_count},
    })
    await _award_xp(manager, state, "ODIN", 15, "pipeline_confirmed")


def _make_title_b_fallback(title_a: str) -> str:
    """
    Generate a simple title_b variant when LOKI doesn't produce one.
    Tests the 'with year' variable — appends '2026' if not already present,
    or strips year if it's already there (testing without).
    """
    from datetime import datetime as _dt
    year = str(_dt.now().year)
    if year in title_a:
        # Strip the year — test without it
        return title_a.replace(f" {year}", "").replace(f", {year}", "").strip()
    else:
        # Add the year — test with it
        candidate = f"{title_a} {year}"
        return candidate[:140]


def _build_vault_report(state: "AppState") -> dict:
    v = state.vault
    revenue = v.get("totalRevenue", 0)
    expenses = v.get("totalExpenses", 0)
    net = v.get("netProfit", 0)
    margin = (net / revenue * 100) if revenue > 0 else 0
    start_date = v.get("startDate", datetime.now().isoformat())
    days = max(1, (datetime.now() - datetime.fromisoformat(start_date[:10])).days + 1)
    txns = v.get("transactions", [])

    return {
        "totalRevenue": f"{revenue:.2f}",
        "totalExpenses": f"{expenses:.2f}",
        "netProfit": f"{net:.2f}",
        "profitMargin": f"{margin:.1f}%",
        "totalTransactions": len(txns),
        "salesCount": len([t for t in txns if t.get("type") == "revenue"]),
        "daysRunning": days,
        "dailyBreakdown": _build_daily_breakdown(txns),
        "recentTransactions": [
            {
                "id": t["id"],
                "type": t["type"],
                "amount": t["amount"],
                "description": t.get("description", ""),
                "source": t.get("source", ""),
                "timestamp": t.get("timestamp", ""),
            }
            for t in sorted(txns, key=lambda x: x.get("timestamp", ""), reverse=True)[:15]
        ],
    }


def _build_daily_breakdown(transactions: list) -> list:
    from collections import defaultdict
    daily: dict = defaultdict(float)
    for t in transactions:
        if t.get("type") == "revenue":
            day = t.get("timestamp", "")[:10]
            daily[day] += t["amount"]
    sorted_days = sorted(daily.items())[-30:]
    return [{"date": d, "revenue": round(v, 2)} for d, v in sorted_days]


async def _log(manager: "ConnectionManager", agent: str, message: str, level: str = "info") -> None:
    await manager.broadcast({
        "type": "agent_log",
        "agent": agent,
        "message": message,
        "level": level,
        "timestamp": datetime.now().isoformat(),
    })


async def _update_status(
    manager: "ConnectionManager",
    state: "AppState",
    agent: str,
    status: str,
    last_action: str,
) -> None:
    ag = state.agents.setdefault(agent, {})
    ag["status"] = status
    ag["lastAction"] = last_action
    await manager.broadcast({
        "type": "agent_status",
        "agent": agent,
        "data": {
            "status": status,
            "lastAction": last_action,
            "xp": ag.get("xp", 0),
            "level": ag.get("level", 1),
        },
    })


async def _award_xp(
    manager: "ConnectionManager",
    state: "AppState",
    agent: str,
    amount: int,
    action: str,
) -> None:
    ag = state.agents.setdefault(agent, {"xp": 0, "level": 1})
    ag["xp"] = ag.get("xp", 0) + amount
    ag["level"] = ag["xp"] // 500 + 1
    state.save_agents()
    await manager.broadcast({
        "type": "xp_gain",
        "agent": agent,
        "amount": amount,
        "total": ag["xp"],
        "level": ag["level"],
        "action": action,
    })
