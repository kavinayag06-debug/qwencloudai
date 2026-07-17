"""
HTML Generator Service - generates landing page redesigns.

For each shortlisted client:
- Generates one primary landing page in HTML
- Optionally generates 1-2 alternate variants
- Saves HTML into the output folder
"""

import hashlib
import logging
from pathlib import Path

import httpx

from app.config import get_settings
from app.core.llm_provider import get_llm_provider, get_vision_provider, build_image_content_parts, llm_unconfigured_reason
from app.core.models import Lead, LeadStatus, StyleTraits
from app.core.prompts import HTML_GENERATION_PROMPT, DESIGN_PLAN_PROMPT, HTML_CRITIQUE_PROMPT, HTML_REVISION_PROMPT
from app.core.scoring import compute_confidence
from app.storage.database import get_database

logger = logging.getLogger(__name__)

# How many actual reference screenshots to attach to the build/critique calls.
# Keep small: enough for the model to genuinely study composition/spacing/type
# without blowing the context window or cost per lead.
MAX_REFERENCE_IMAGES = 3
# How many real photos to try to pull from the client's own site.
MAX_SOURCE_IMAGES = 4

# Quality bar a generated design must clear to skip further revision rounds.
QUALITY_THRESHOLD = 75
# Build once, revise at most this many times.
MAX_REVISIONS = 2

# Industry-specific design presets
INDUSTRY_PRESETS = {
    "florist": {
        "colors": ["#4A7C59", "#F5E6D3", "#D4A574", "#2D5016"],
        "font": "Playfair Display",
        "mood": "elegant, earthy, organic",
        "hero_text": "Beautiful Blooms for Every Occasion",
        "services": ["Wedding Arrangements", "Daily Fresh Bouquets", "Event Floristry"],
        "testimonial": "The most beautiful arrangement I've ever received. Absolutely stunning craftsmanship!",
        "layout": "split",  # side-by-side hero
    },
    "restaurant": {
        "colors": ["#8B1A1A", "#FFF8E7", "#D4A017", "#1A1A1A"],
        "font": "Merriweather",
        "mood": "warm, inviting, appetizing",
        "hero_text": "Authentic Flavours, Unforgettable Moments",
        "services": ["Dine-In Experience", "Catering Services", "Private Events"],
        "testimonial": "Best food in the neighbourhood! We come back every week. The flavours are incredible.",
        "layout": "fullwidth",  # large full-width hero
    },
    "cafe": {
        "colors": ["#6B4423", "#FDF6EC", "#C9956B", "#2C1810"],
        "font": "Nunito",
        "mood": "cozy, artisanal, relaxed",
        "hero_text": "Your Neighbourhood Coffee Spot",
        "services": ["Specialty Coffee", "Fresh Pastries", "Cozy Workspace"],
        "testimonial": "The perfect place to grab a coffee and get some work done. Love the atmosphere!",
        "layout": "minimal",  # minimal white-space heavy
    },
    "spa": {
        "colors": ["#5B7B7A", "#F7F3EF", "#C9B99A", "#2C3E3D"],
        "font": "Cormorant Garamond",
        "mood": "serene, luxurious, calming",
        "hero_text": "Relax. Rejuvenate. Restore.",
        "services": ["Massage Therapy", "Facial Treatments", "Body Wellness"],
        "testimonial": "An oasis of calm. I left feeling completely renewed. Can't recommend enough!",
        "layout": "centered",  # centered with lots of breathing room
    },
    "salon": {
        "colors": ["#C4547A", "#FFF5F7", "#2C2C2C", "#E8B4B8"],
        "font": "Montserrat",
        "mood": "stylish, confident, trendy",
        "hero_text": "Your Best Look Starts Here",
        "services": ["Haircuts & Styling", "Colour Treatments", "Bridal Packages"],
        "testimonial": "Finally found a salon that really listens. My hair has never looked this good!",
        "layout": "bold",  # bold typography, dark theme option
    },
    "gym": {
        "colors": ["#E63946", "#1D3557", "#F1FAEE", "#457B9D"],
        "font": "Oswald",
        "mood": "energetic, powerful, motivating",
        "hero_text": "Push Your Limits. Transform Your Life.",
        "services": ["Personal Training", "Group Classes", "24/7 Access"],
        "testimonial": "This gym changed my life. The trainers are incredible and the community is so supportive.",
        "layout": "angular",  # diagonal cuts, bold angles
    },
    "sports": {
        "colors": ["#E63946", "#1D3557", "#F1FAEE", "#457B9D"],
        "font": "Oswald",
        "mood": "energetic, powerful, motivating",
        "hero_text": "Achieve More. Play Harder.",
        "services": ["Sports Facilities", "Group Activities", "Membership Plans"],
        "testimonial": "Amazing facilities and a great community vibe. Something for everyone.",
        "layout": "angular",
    },
    "clinic": {
        "colors": ["#1B6CA8", "#F0F8FF", "#4CAF50", "#2C3E50"],
        "font": "Source Sans Pro",
        "mood": "trustworthy, professional, caring",
        "hero_text": "Compassionate Care for Your Family",
        "services": ["General Consultation", "Health Screening", "Vaccination"],
        "testimonial": "Dr. and the team are always so thorough and kind. We trust them with our whole family's health.",
        "layout": "clean",  # very clean, medical-style
    },
    "bakery": {
        "colors": ["#D4763B", "#FFF9F0", "#8B4513", "#F5DEB3"],
        "font": "Satisfy",
        "mood": "warm, homely, artisanal",
        "hero_text": "Freshly Baked with Love, Daily",
        "services": ["Artisan Breads", "Custom Cakes", "Pastries & Treats"],
        "testimonial": "The croissants here are better than what I had in Paris. Not exaggerating!",
        "layout": "warm",  # warm tones, rounded elements
    },
    "retail": {
        "colors": ["#2C3E50", "#ECF0F1", "#E74C3C", "#3498DB"],
        "font": "Poppins",
        "mood": "modern, clean, trustworthy",
        "hero_text": "Quality Products, Personal Service",
        "services": ["Curated Selection", "Expert Advice", "Local Delivery"],
        "testimonial": "My go-to shop for quality items. The staff really know their products.",
        "layout": "grid",  # product-grid focused
    },
    "fashion": {
        "colors": ["#1A1A1A", "#FAFAFA", "#C9A96E", "#333333"],
        "font": "Playfair Display",
        "mood": "elegant, luxurious, editorial",
        "hero_text": "Define Your Style",
        "services": ["New Arrivals", "Personal Styling", "Exclusive Collections"],
        "testimonial": "Such a curated selection. I always find something unique here.",
        "layout": "editorial",  # magazine-style
    },
}

DEFAULT_PRESET = {
    "colors": ["#2C3E50", "#ECF0F1", "#3498DB", "#E74C3C"],
    "font": "Inter",
    "mood": "professional, modern",
    "hero_text": "Quality Service You Can Trust",
    "services": ["Expert Service", "Local Presence", "Customer First"],
    "testimonial": "Wonderful experience from start to finish. Highly recommended!",
    "layout": "fullwidth",
}


class HTMLGenerator:
    """Generates HTML landing pages based on analysis and style traits."""

    async def generate(self, lead: Lead, style_traits: StyleTraits) -> Lead:
        """Generate an HTML landing page for the lead via a plan -> build -> critique -> revise loop."""
        logger.info(f"Generating HTML for {lead.company_name}")
        lead.add_log("Starting HTML generation")

        llm = get_llm_provider()
        vision = get_vision_provider()
        quality_score = 0

        # Reference screenshots: attach the *actual* images to the model call,
        # not just the text paraphrase in style_traits. Without this the model
        # never sees what "good" looks like, which is the main reason past
        # output didn't resemble the samples at all.
        reference_images = self._select_reference_images(style_traits, lead)

        # Real photos of this specific business, downloaded from their current
        # site. Every generated <img> must point at one of these local files
        # (or none at all) — never a hotlinked stock photo or a path that was
        # never created.
        settings = get_settings()
        lead_dir = settings.output_dir / lead.id
        local_images = await self._prepare_images(lead, lead_dir)

        # Check if AI is actually configured — if not, warn loudly and use fallback
        unconfigured = llm_unconfigured_reason()
        fallback_reason = None

        try:
            if unconfigured:
                fallback_reason = f"AI NOT CONFIGURED: {unconfigured}"
                raise RuntimeError(fallback_reason)

            brief = await self._plan(llm, lead, style_traits)

            html_content = await self._build(vision, lead, style_traits, brief, reference_images, local_images)
            best_html = html_content if self._looks_like_html(html_content) else None
            best_score = -1

            for round_num in range(MAX_REVISIONS + 1):
                if not self._looks_like_html(html_content):
                    break

                critique = await self._critique(vision, lead, html_content, reference_images)
                score = int(critique.get("score", 0))
                issues = critique.get("issues", [])
                lead.add_log(f"Design critique round {round_num + 1}: score={score}, issues={len(issues)}")

                if score > best_score:
                    best_score, best_html = score, html_content

                if score >= QUALITY_THRESHOLD or not issues or round_num == MAX_REVISIONS:
                    break

                html_content = await self._revise(llm, lead, html_content, issues)

            if best_html is None:
                fallback_reason = "LLM did not return valid HTML"
                html_content = self._generate_fallback_html(lead, style_traits)
                quality_score = 50
            else:
                html_content = best_html
                quality_score = max(best_score, 0)

        except Exception as e:
            if not fallback_reason:
                fallback_reason = f"LLM call failed: {e}"
            logger.error(f"HTML generation failed: {e}")
            lead.add_log(f"HTML generation failed: {str(e)}")
            html_content = self._generate_fallback_html(lead, style_traits)
            quality_score = 50

        # Loud logging when fallback is used
        if fallback_reason:
            warn_msg = f"NOT an AI-generated design — {fallback_reason}"
            logger.warning(warn_msg)
            lead.add_log(f"AI not configured or failed: using fallback template. This is NOT an AI-generated design.")

        # Save HTML file
        lead_dir.mkdir(parents=True, exist_ok=True)

        html_path = lead_dir / "index.html"
        html_path.write_text(html_content, encoding="utf-8")

        lead.html_path = str(html_path)
        lead.html_quality_score = quality_score
        lead.status = LeadStatus.REDESIGN_GENERATED
        lead.add_log(f"HTML saved to {html_path} (quality_score={quality_score})")

        # Feed the critic's real score back into confidence/routing instead of a flat guess
        if lead.website_analysis:
            lead.confidence = compute_confidence(
                analysis=lead.website_analysis,
                style_traits=style_traits,
                industry=lead.industry,
                html_generated=True,
                email_drafted=bool(lead.email_body),
                html_quality_score=quality_score,
            )

        # Save
        db = get_database()
        db.save_lead(lead)
        return lead

    @staticmethod
    def _select_reference_images(style_traits: StyleTraits, lead: Lead) -> list[Path]:
        """Pick a small, varied subset of the actual reference screenshots.

        Uses a stable hash of the lead so different leads see different
        reference images across runs, instead of always the same first N.
        """
        paths = [Path(p) for p in (style_traits.reference_image_paths or []) if Path(p).exists()]
        if len(paths) <= MAX_REFERENCE_IMAGES:
            return paths
        seed = int(hashlib.sha256((lead.id or lead.company_name).encode()).hexdigest(), 16)
        offset = seed % len(paths)
        return [paths[(offset + i) % len(paths)] for i in range(MAX_REFERENCE_IMAGES)]

    async def _prepare_images(self, lead: Lead, lead_dir: Path) -> list[str]:
        """Download real photos from the client's current site into images/.

        Returns the filenames (relative to lead_dir) that were actually saved
        successfully. Only these filenames are ever handed to the model — if
        the list is empty, the prompt instructs a photo-free, CSS-only design
        instead of a broken <img> or an unrelated stock photo.
        """
        if not lead.source_image_urls:
            return []

        images_dir = lead_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []

        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        ) as client:
            for i, url in enumerate(lead.source_image_urls[:MAX_SOURCE_IMAGES]):
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    content_type = resp.headers.get("content-type", "")
                    if not content_type.startswith("image/"):
                        continue
                    if len(resp.content) < 2048:  # almost certainly an icon/pixel, not a photo
                        continue
                    ext = content_type.split("/")[-1].split(";")[0].strip() or "jpg"
                    if ext == "jpeg":
                        ext = "jpg"
                    if ext not in ("jpg", "png", "webp", "gif"):
                        ext = "jpg"
                    filename = f"photo_{i + 1}.{ext}"
                    (images_dir / filename).write_bytes(resp.content)
                    saved.append(filename)
                except Exception as e:
                    logger.warning(f"Could not download image {url}: {e}")
                    continue

        lead.local_image_paths = saved
        if saved:
            lead.add_log(f"Downloaded {len(saved)} real photos from the client's site")
        else:
            lead.add_log("No usable photos found on the client's site; using a photo-free design")
        return saved

    async def _plan(self, llm, lead: Lead, style_traits: StyleTraits) -> dict:
        """Planner step: produce a business-specific content brief before any HTML is written."""
        design_problems = ", ".join(
            lead.website_analysis.design_problems if lead.website_analysis else ["outdated design"]
        )
        prompt = DESIGN_PLAN_PROMPT.format(
            company_name=lead.company_name,
            industry=lead.industry,
            location=lead.location,
            address=lead.address or lead.location,
            phone=lead.phone or "not provided",
            design_problems=design_problems,
            color_palette=", ".join(style_traits.color_palette) if style_traits.color_palette else "use industry-appropriate colors",
            typography=style_traits.typography or "modern sans-serif",
            layout_style=style_traits.layout_style or "clean minimalist",
            mood=style_traits.mood or "professional",
        )
        response = await llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            json_mode=True,
        )
        try:
            return response.as_json()
        except Exception:
            return {}

    async def _build(self, vision, lead: Lead, style_traits: StyleTraits, brief: dict,
                      reference_images: list[Path], local_images: list[str]) -> str:
        """Builder step: generate the HTML, informed by the planner's brief and
        grounded in the actual reference screenshots (attached as images, not
        just described in text)."""
        design_problems = ", ".join(
            lead.website_analysis.design_problems if lead.website_analysis else ["outdated design"]
        )
        design_patterns = list(style_traits.design_patterns or [])
        if brief.get("sections"):
            design_patterns = brief["sections"]

        if local_images:
            image_instructions = (
                f"Real photos of this business are available at these EXACT local paths — "
                f"use only these, each at most once, and no others: "
                + ", ".join(f'"images/{name}"' for name in local_images)
            )
        else:
            image_instructions = (
                "No real photos of this business are available. Do NOT use <img> tags, "
                "picsum.photos, unsplash, or any other placeholder/stock image service. "
                "Build the visual interest entirely from CSS: gradients, color blocks, "
                "geometric shapes, subtle patterns, and typography, the way the attached "
                "reference designs do in their non-photo sections."
            )

        prompt = HTML_GENERATION_PROMPT.format(
            company_name=lead.company_name,
            industry=lead.industry,
            location=lead.location,
            design_problems=design_problems,
            color_palette=", ".join(style_traits.color_palette) if style_traits.color_palette else "use industry-appropriate colors",
            typography=style_traits.typography or "modern sans-serif",
            layout_style=style_traits.layout_style or "clean minimalist",
            mood=style_traits.mood or "professional",
            design_patterns=", ".join(design_patterns) if design_patterns else "hero section, card grid, testimonials, CTA",
            image_instructions=image_instructions,
        )
        if brief:
            brief_text = []
            if brief.get("headline"):
                brief_text.append(f"Headline: {brief['headline']}")
            if brief.get("subheadline"):
                brief_text.append(f"Subheadline: {brief['subheadline']}")
            if brief.get("highlights"):
                brief_text.append("Service highlights:")
                for h in brief["highlights"]:
                    title = h.get("title", "") if isinstance(h, dict) else str(h)
                    desc = h.get("description", "") if isinstance(h, dict) else ""
                    brief_text.append(f"  - {title}: {desc}")
            if brief.get("cta_text"):
                brief_text.append(f"CTA button text: {brief['cta_text']}")
            if brief.get("testimonial_placeholder"):
                brief_text.append(f"Sample testimonial (mark as placeholder): {brief['testimonial_placeholder']}")
            if brief.get("meta_description"):
                brief_text.append(f"Meta description: {brief['meta_description']}")
            prompt += "\n\nContent brief (use this specific content, not generic filler):\n" + "\n".join(brief_text)

        content_parts = [{"type": "text", "text": prompt}]
        if reference_images:
            content_parts.append({
                "type": "text",
                "text": (
                    f"\nThe {len(reference_images)} image(s) below are real past designs from our "
                    "studio. Study their composition, spacing, type scale, hero layout, and use of "
                    "whitespace closely and reproduce that *level of design quality and structure* "
                    "for this business — do not copy their specific content or colors verbatim, "
                    "adapt the palette above onto the same caliber of layout."
                ),
            })
            content_parts.extend(build_image_content_parts(reference_images))

        response = await vision.complete(
            messages=[{"role": "user", "content": content_parts}],
            temperature=0.7,
            max_tokens=8192,
        )
        return self._strip_code_fence(response.content)

    async def _critique(self, vision, lead: Lead, html_content: str, reference_images: list[Path]) -> dict:
        """Critic step: score the generated HTML against commercial-quality
        standards AND fidelity to the attached reference designs."""
        prompt = HTML_CRITIQUE_PROMPT.format(
            company_name=lead.company_name,
            industry=lead.industry,
            html_content=html_content,
        )
        content_parts = [{"type": "text", "text": prompt}]
        if reference_images:
            content_parts.append({
                "type": "text",
                "text": "\nThe image(s) below are the reference designs this page is supposed to match in quality and composition. Judge criterion 11 against them directly.",
            })
            content_parts.extend(build_image_content_parts(reference_images))

        response = await vision.complete(
            messages=[{"role": "user", "content": content_parts}],
            temperature=0.2,
            json_mode=True,
        )
        try:
            return response.as_json()
        except Exception:
            return {"score": 0, "issues": [], "passed": False}

    async def _revise(self, llm, lead: Lead, html_content: str, issues: list) -> str:
        """Revision step: fix the specific issues the critic raised."""
        prompt = HTML_REVISION_PROMPT.format(
            company_name=lead.company_name,
            html_content=html_content,
            issues="\n".join(f"- {issue}" for issue in issues),
        )
        response = await llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=8192,
        )
        return self._strip_code_fence(response.content)

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        return content.strip()

    @staticmethod
    def _looks_like_html(content: str) -> bool:
        lowered = content.strip().lower()
        return lowered.startswith("<!doctype") or lowered.startswith("<html")

    def _generate_fallback_html(self, lead: Lead, style_traits: StyleTraits) -> str:
        """Generate industry-specific fallback HTML with varied layouts."""
        from app.services.fallback_layouts import generate_fallback
        return generate_fallback(lead, style_traits, INDUSTRY_PRESETS, DEFAULT_PRESET)
