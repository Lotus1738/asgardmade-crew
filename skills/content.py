"""
Content skill pack — blog posts, social captions, product descriptions, email drafts,
Pinterest pin copy, and ad copy using Claude.
"""

import os
from skills import SkillMeta, SkillResult, register

MODEL = "claude-haiku-4-5-20251001"   # fast model for content tasks


async def _claude(prompt: str, system: str = "") -> str:
    """Run a quick Claude call for content generation."""
    import anthropic
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    client = anthropic.AsyncAnthropic(api_key=key)
    msgs = [{"role": "user", "content": prompt}]
    kwargs = {"model": MODEL, "max_tokens": 1024, "messages": msgs}
    if system:
        kwargs["system"] = system
    resp = await client.messages.create(**kwargs)
    return resp.content[0].text.strip()


# ─── Skills ──────────────────────────────────────────────────────────────────

async def _etsy_listing_copy(args: dict) -> SkillResult:
    """Write a full Etsy listing: title, description, and 13 tags."""
    title = args.get("title", "")
    niche = args.get("niche", "")
    product_type = args.get("product_type", "t-shirt")
    if not title:
        return SkillResult(success=False, output=None, error="title is required")

    prompt = f"""Write an Etsy listing for a print-on-demand product.

Product: {title}
Niche: {niche}
Type: {product_type}

Return EXACTLY this format:

TITLE: [SEO-optimized title, max 140 chars, lead with main keyword]

DESCRIPTION:
[3 paragraphs. Para 1: emotional hook + niche. Para 2: product details. Para 3: gift angle + CTA]

TAGS: [13 comma-separated tags, niche + long-tail + buyer-intent mix]

PRICE: [suggested price USD based on market]"""

    try:
        text = await _claude(prompt, system="You are LOKI, expert Etsy SEO copywriter for print-on-demand.")
        sections = {"title": "", "description": "", "tags": [], "price": ""}
        lines = text.split("\n")
        current = None
        desc_lines = []
        for line in lines:
            if line.startswith("TITLE:"):
                sections["title"] = line.replace("TITLE:", "").strip()
            elif line.startswith("DESCRIPTION:"):
                current = "desc"
            elif line.startswith("TAGS:"):
                current = None
                raw = line.replace("TAGS:", "").strip()
                sections["tags"] = [t.strip() for t in raw.split(",")][:13]
            elif line.startswith("PRICE:"):
                current = None
                sections["price"] = line.replace("PRICE:", "").strip()
            elif current == "desc" and line.strip():
                desc_lines.append(line.strip())
        sections["description"] = "\n\n".join(desc_lines)
        return SkillResult(
            success=True,
            output=sections,
            summary=f"Generated Etsy listing copy for '{title}'",
        )
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))


async def _social_captions(args: dict) -> SkillResult:
    """Generate social media captions for a product (Instagram, TikTok, Pinterest)."""
    title = args.get("title", "")
    niche = args.get("niche", "")
    platforms = args.get("platforms", ["instagram", "tiktok", "pinterest"])
    if not title:
        return SkillResult(success=False, output=None, error="title is required")

    platform_list = ", ".join(platforms)
    prompt = f"""Write social media captions for a print-on-demand product.

Product: {title}
Niche: {niche}
Platforms: {platform_list}

For each platform write one caption optimized for that platform's style and algorithm.
Format:
INSTAGRAM: [caption with emojis + 10 hashtags]
TIKTOK: [hook-first caption, trending sounds vibe, 5 hashtags]
PINTEREST: [keyword-rich description, 150 chars, 5 hashtags]"""

    try:
        text = await _claude(prompt, system="You are a viral social media manager for a POD Etsy shop.")
        captions = {}
        for platform in ["instagram", "tiktok", "pinterest"]:
            key = platform.upper() + ":"
            if key in text:
                idx = text.index(key)
                end = len(text)
                for p2 in ["instagram", "tiktok", "pinterest"]:
                    k2 = p2.upper() + ":"
                    if k2 in text and text.index(k2) > idx:
                        end = min(end, text.index(k2))
                captions[platform] = text[idx + len(key):end].strip()
        return SkillResult(
            success=True,
            output=captions,
            summary=f"Generated captions for {len(captions)} platforms",
        )
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))


async def _blog_post(args: dict) -> SkillResult:
    """Write a short SEO blog post about a niche or product."""
    topic = args.get("topic", "")
    word_count = int(args.get("word_count", 400))
    if not topic:
        return SkillResult(success=False, output=None, error="topic is required")

    prompt = f"""Write a {word_count}-word SEO blog post about: {topic}

Structure:
- H1 title (keyword-rich)
- 1-sentence intro hook
- 3-4 body paragraphs
- Call to action at end

Write for someone interested in buying {topic}-themed gifts or apparel. Natural, conversational tone."""

    try:
        text = await _claude(prompt, system="You are a content strategist for an Etsy print-on-demand shop.")
        return SkillResult(
            success=True,
            output=text,
            summary=f"Wrote ~{len(text.split())} word blog post about '{topic}'",
        )
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))


async def _email_draft(args: dict) -> SkillResult:
    """Draft a professional email."""
    to = args.get("to", "")
    subject = args.get("subject", "")
    context = args.get("context", "")
    tone = args.get("tone", "professional")
    if not subject or not context:
        return SkillResult(success=False, output=None, error="subject and context are required")

    prompt = f"""Draft an email.
To: {to or 'recipient'}
Subject: {subject}
Tone: {tone}
Context/purpose: {context}

Write just the email body (no subject line). Start with appropriate greeting. End with signature "Mario / AsgardMade"."""

    try:
        text = await _claude(prompt)
        return SkillResult(
            success=True,
            output={"subject": subject, "body": text, "to": to},
            summary=f"Drafted email: '{subject}'",
        )
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))


async def _ad_copy(args: dict) -> SkillResult:
    """Write ad copy for Etsy Ads or social media ads."""
    product = args.get("product", "")
    niche = args.get("niche", "")
    ad_type = args.get("ad_type", "etsy")  # etsy, facebook, google
    if not product:
        return SkillResult(success=False, output=None, error="product is required")

    prompt = f"""Write {ad_type} ad copy for:
Product: {product}
Niche: {niche}

Output:
HEADLINE: [under 40 chars, value-first]
SUBHEAD: [under 60 chars]
BODY: [2-3 sentences, urgency + benefit]
CTA: [call to action button text, 2-4 words]"""

    try:
        text = await _claude(prompt, system="You are a direct-response copywriter for e-commerce ads.")
        return SkillResult(success=True, output=text, summary=f"Generated {ad_type} ad copy for '{product}'")
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))


async def _design_prompt(args: dict) -> SkillResult:
    """Generate an AI image generation prompt for a POD design."""
    concept = args.get("concept", "")
    style = args.get("style", "flat vector illustration")
    product = args.get("product_type", "t-shirt")
    if not concept:
        return SkillResult(success=False, output=None, error="concept is required")

    prompt = f"""Write 3 different AI image generation prompts for a print-on-demand design.

Concept: {concept}
Style: {style}
Product: {product}

Each prompt should be 1-2 sentences, highly specific, optimized for DALL-E or Stable Diffusion.
Include: art style, composition, colors, mood, technical specs (transparent background, vector).

FORMAT:
PROMPT 1: [prompt]
PROMPT 2: [prompt variation — different angle]
PROMPT 3: [prompt variation — different color mood]"""

    try:
        text = await _claude(prompt, system="You are VULCAN, expert AI art director for print-on-demand.")
        prompts = []
        for i in range(1, 4):
            key = f"PROMPT {i}:"
            if key in text:
                idx = text.index(key)
                end = len(text)
                if f"PROMPT {i+1}:" in text:
                    end = text.index(f"PROMPT {i+1}:")
                prompts.append(text[idx + len(key):end].strip())
        return SkillResult(
            success=True,
            output={"prompts": prompts, "concept": concept, "style": style},
            summary=f"Generated {len(prompts)} design prompts for '{concept}'",
        )
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))


async def _product_description(args: dict) -> SkillResult:
    """Write a product description optimized for conversion."""
    product = args.get("product", "")
    niche = args.get("niche", "")
    features = args.get("features", [])
    if not product:
        return SkillResult(success=False, output=None, error="product is required")

    feature_text = "\n".join(f"- {f}" for f in features) if features else "- High quality print\n- Ships 3-5 days"
    prompt = f"""Write a compelling product description for:
Product: {product}
Niche: {niche}
Features:
{feature_text}

200 words max. Lead with emotional benefit. Include keywords naturally. End with CTA."""

    try:
        text = await _claude(prompt)
        return SkillResult(success=True, output=text, summary=f"Written product description for '{product}'")
    except Exception as e:
        return SkillResult(success=False, output=None, error=str(e))


# ─── Register all ────────────────────────────────────────────────────────────

def register_all():
    register(SkillMeta(
        name="etsy_listing_copy",
        description="Generate a complete Etsy listing: title, description, and 13 SEO tags",
        pack="content",
        fn=_etsy_listing_copy,
        args_schema={"title": "Product title or concept", "niche": "Target niche", "product_type": "Product type"},
        tags=["etsy", "seo", "listing", "copy"],
        icon="🏪",
    ))
    register(SkillMeta(
        name="social_captions",
        description="Write optimized social media captions for Instagram, TikTok, and Pinterest",
        pack="content",
        fn=_social_captions,
        args_schema={"title": "Product name", "niche": "Niche", "platforms": "List of platforms"},
        tags=["social", "instagram", "tiktok", "pinterest"],
        icon="📱",
    ))
    register(SkillMeta(
        name="blog_post",
        description="Write a short SEO blog post about a niche or product",
        pack="content",
        fn=_blog_post,
        args_schema={"topic": "Blog topic", "word_count": "Target word count (default 400)"},
        tags=["blog", "seo", "content"],
        icon="✍️",
    ))
    register(SkillMeta(
        name="email_draft",
        description="Draft a professional email on any topic",
        pack="content",
        fn=_email_draft,
        args_schema={"to": "Recipient", "subject": "Email subject", "context": "What to say", "tone": "professional/casual"},
        tags=["email", "communication"],
        icon="📧",
    ))
    register(SkillMeta(
        name="ad_copy",
        description="Write ad copy for Etsy Ads, Facebook, or Google Ads",
        pack="content",
        fn=_ad_copy,
        args_schema={"product": "Product name", "niche": "Niche", "ad_type": "etsy/facebook/google"},
        tags=["ads", "marketing", "copy"],
        icon="📣",
    ))
    register(SkillMeta(
        name="design_prompt",
        description="Generate 3 AI image prompts for a print-on-demand design concept",
        pack="content",
        fn=_design_prompt,
        args_schema={"concept": "Design concept", "style": "Art style (default: flat vector)", "product_type": "Product type"},
        tags=["design", "ai", "dalle", "vulcan"],
        icon="🎨",
    ))
    register(SkillMeta(
        name="product_description",
        description="Write a conversion-optimized product description",
        pack="content",
        fn=_product_description,
        args_schema={"product": "Product name", "niche": "Niche", "features": "List of features"},
        tags=["copy", "product", "conversion"],
        icon="📝",
    ))
