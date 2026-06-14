"""
Task definitions for the AsgardMade pipeline.
These describe what each agent should do at each pipeline stage.
Used as structured prompts for the Anthropic API calls.
"""


def make_research_task(niche: str) -> dict:
    return {
        "agent": "HEIMDALL",
        "description": (
            f"Research the '{niche}' niche on Etsy and identify 3 specific product opportunities. "
            "For each product, provide: exact title, product type (t-shirt/mug/poster/tote/hoodie), "
            "demand score 1-100, competition level (Low/Medium/High/Very High), "
            "estimated monthly revenue range, and 7 SEO keywords. "
            "Focus on gaps in the market — products with high demand but medium-or-lower competition."
        ),
        "expected_output": (
            "A JSON array of 3 product ideas, each with fields: "
            "title, productType, demandScore, competition, estimatedMonthlyRevenue, keywords (list), description"
        ),
    }


def make_design_brief_task(idea: dict) -> dict:
    return {
        "agent": "VULCAN",
        "description": (
            f"Create a DALL-E 3 prompt for: '{idea['title']}' "
            f"in the {idea.get('niche', 'general')} niche for a {idea.get('productType', 't-shirt')}. "
            "The prompt must produce a flat vector illustration with: "
            "clean bold design, white background, centered composition, "
            "high contrast, no text in the image, DTG printing ready. "
            "Generate 2 variant concepts — same theme, different visual approach."
        ),
        "expected_output": (
            "prompt1 (string), prompt2 (string), "
            "design_rationale (why these will sell), "
            "recommended_variant (1 or 2 with reason)"
        ),
    }


def make_listing_task(idea: dict, product_id: str) -> dict:
    return {
        "agent": "LOKI",
        "description": (
            f"Create an optimized Etsy listing for '{idea['title']}'. "
            f"Product type: {idea.get('productType', 't-shirt')}. "
            f"Niche: {idea.get('niche', 'general')}. "
            f"Printify product ID: {product_id}. "
            f"Keywords to target: {', '.join(idea.get('keywords', [])[:7])}. "
            "Generate: SEO title (max 140 chars, keyword-first), "
            "13 Etsy tags (mix of high-volume and long-tail), "
            "compelling product description (3-4 paragraphs, buyer-focused). "
            "Price: $24.99."
        ),
        "expected_output": (
            "title (string), tags (list of 13), description (string), "
            "price (float), seo_notes (why these choices maximize visibility)"
        ),
    }


def make_finance_log_task(event: dict) -> dict:
    return {
        "agent": "VAULT",
        "description": (
            f"Log this financial event: {event}. "
            "Calculate: Printify base cost ($8.50), Etsy listing fee ($0.20), "
            "Etsy transaction fee (6.5% of sale price if applicable). "
            "Return updated P&L summary."
        ),
        "expected_output": (
            "transaction_id (string), totalRevenue (float), "
            "totalExpenses (float), netProfit (float), "
            "profitMargin (string), healthAssessment (string)"
        ),
    }


def make_security_scan_task(recent_requests: list) -> dict:
    return {
        "agent": "TYR",
        "description": (
            f"Analyze these HTTP requests for threats: {recent_requests[:20]}. "
            "Check for SQL injection, path traversal, malicious IP ranges (185.220.x, 194.165.x), "
            "rate limit violations, API key exposure. "
            "Classify each threat: INFO, WARNING, CRITICAL."
        ),
        "expected_output": (
            "threats (list), ips_to_block (list), scan_summary (string), "
            "recommended_actions (list)"
        ),
    }
