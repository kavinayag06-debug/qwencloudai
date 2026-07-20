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
from typing import Optional

import httpx

from app.config import get_settings
from app.core.llm_provider import get_llm_provider, get_vision_provider, build_image_content_parts, llm_unconfigured_reason, vision_unconfigured_reason
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

# What Awwwards/FWA-caliber sites actually look like per industry — a restaurant
# and a gym shouldn't look like the same template with different colors. Fed
# into the build/critique prompts so the quality bar is industry-specific, not
# a generic "avoid AI template tells" note.
AWARD_REFERENCE_STYLES = {
    "florist": "Award-winning florist sites use macro close-up photography of texture and "
    "petals, asymmetric organic layouts that avoid rigid grids, a single elegant script or "
    "serif display font paired with a minimal sans body, and generous negative space — never "
    "a stock-photo hero with a bootstrap-style CTA button.",
    "restaurant": "Award-winning restaurant sites (Michelin-guide caliber) use cinematic "
    "full-bleed food and interior photography, oversized editorial display type, dark or "
    "richly-colored sections rather than flat white, and a reservation CTA that feels like an "
    "invitation, not a form dump.",
    "cafe": "Top-tier cafe sites lean into warm documentary-style photography of the space and "
    "drinks, hand-lettered or script accent type against a clean geometric sans, and an "
    "ingredient/sourcing story section — not a generic 'our menu' grid.",
    "spa": "Award-winning spa/wellness sites use slow, immersive full-bleed imagery, a muted "
    "sophisticated palette (stone, sage, warm neutrals), thin elegant serif or high-end sans "
    "type, and deliberate whitespace that itself communicates calm — busy layouts undercut the "
    "entire premise.",
    "salon": "Top salon/beauty sites use bold editorial fashion-magazine composition, large "
    "confident portrait photography, a striking type pairing (often a heavy display face + "
    "light body), and a strong signature accent color used decisively, not timidly.",
    "gym": "Award-winning fitness sites use high-contrast action photography, oversized bold "
    "uppercase display type, kinetic diagonal or angular section breaks, and a color palette "
    "that reads as energy, not a pastel gym.",
    "sports": "Award-winning sports/fitness sites use high-contrast action photography, "
    "oversized bold uppercase display type, kinetic diagonal or angular section breaks, and a "
    "color palette that reads as energy and momentum.",
    "clinic": "Top healthcare/clinic sites use calm generous whitespace, soft rounded geometry, "
    "real trust-building elements (credentials, outcomes, care philosophy) presented with "
    "restraint, and warm approachable photography — sterile stock-photo clinical imagery reads "
    "as generic, not trustworthy.",
    "bakery": "Award-winning bakery sites use warm natural-light photography of the product "
    "close-up, a friendly script or hand-drawn accent type against a clean serif/sans body, and "
    "a 'baked daily' rhythm/story section — never a plain grid of product thumbnails.",
    "retail": "Top-tier retail/boutique sites use disciplined e-commerce-grade grids, large "
    "lifestyle photography over plain product shots, minimal chrome/navigation, and confident "
    "use of negative space between products.",
    "fashion": "Award-winning fashion/boutique sites use full-bleed editorial photography, a "
    "striking display typeface at large scale, asymmetric magazine-style layouts, and a "
    "restrained monochrome-plus-one-accent palette.",
}

DEFAULT_AWARD_REFERENCE = (
    "Award-winning small-business sites in general share: oversized confident typography used "
    "as a design element (not just text), asymmetric or full-bleed layouts instead of "
    "centered-hero-plus-three-cards, a real color story instead of navy-on-white, and generous "
    "whitespace with a clear single focal point per section."
)


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

        # Check if AI is actually configured — if not, warn loudly and use fallback.
        # Both providers matter: _plan/_revise run on `llm`, _build/_critique run on
        # `vision`, so either being unconfigured means real AI never actually runs.
        unconfigured = llm_unconfigured_reason() or vision_unconfigured_reason()
        fallback_reason = None

        try:
            if unconfigured:
                fallback_reason = f"AI NOT CONFIGURED: {unconfigured}"
                raise RuntimeError(fallback_reason)

            brief = await self._plan(llm, lead, style_traits)

            html_content = await self._build(vision, lead, style_traits, brief, reference_images, local_images)
            lead.add_log(f"Style palette used: {style_traits.color_palette} (source: {style_traits.reference_source})")
            best_html = html_content if self._looks_like_html(html_content) else None
            best_score = -1

            for round_num in range(MAX_REVISIONS + 1):
                if not self._looks_like_html(html_content):
                    break

                # Render a screenshot of the current HTML so the critic judges
                # the actual rendered output, not just raw code
                rendered_screenshot = await self._render_for_critique(html_content, lead_dir, round_num)

                critique = await self._critique(vision, lead, html_content, reference_images, rendered_screenshot)
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
            lead.add_log(f"⚠ FALLBACK TEMPLATE USED (not AI-generated). Reason: {fallback_reason}")

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

        # Use Referer header matching the lead's site — some CDNs (Wix,
        # Squarespace, Cloudinary) 403 requests with missing/wrong referer.
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": lead.website_url or "",
        }

        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True, headers=headers,
        ) as client:
            for i, url in enumerate(lead.source_image_urls[:MAX_SOURCE_IMAGES]):
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning(
                            f"Image download failed (HTTP {resp.status_code}): {url[:80]} "
                            f"— may be hotlink-blocked by CDN"
                        )
                        lead.add_log(f"Image {i+1} download failed: HTTP {resp.status_code} for {url[:60]}")
                        continue
                    content_type = resp.headers.get("content-type", "")
                    if not content_type.startswith("image/"):
                        logger.warning(f"Image URL returned non-image content-type: {content_type} for {url[:80]}")
                        continue
                    if len(resp.content) < 2048:  # almost certainly an icon/pixel, not a photo
                        continue
                    ext = content_type.split("/")[-1].split(";")[0].strip() or "jpg"
                    if ext == "jpeg":
                        ext = "jpg"
                    elif ext == "svg+xml":
                        ext = "svg"
                    if ext not in ("jpg", "png", "webp", "gif", "svg"):
                        ext = "jpg"
                    filename = f"photo_{i + 1}.{ext}"
                    (images_dir / filename).write_bytes(resp.content)
                    saved.append(filename)
                except Exception as e:
                    logger.warning(f"Could not download image {url[:80]}: {e}")
                    lead.add_log(f"Image {i+1} download exception: {e}")
                    continue

        lead.local_image_paths = saved
        if saved:
            lead.add_log(f"Downloaded {len(saved)} real photos from the client's site")
        else:
            lead.add_log(
                f"No usable photos downloaded (tried {len(lead.source_image_urls[:MAX_SOURCE_IMAGES])} URLs); "
                f"using a photo-free CSS-only design"
            )
        return saved

    async def _render_for_critique(self, html_content: str, lead_dir: Path, round_num: int) -> Optional[Path]:
        """Render the current HTML to a screenshot for the critic to judge visually.

        Returns the path to the screenshot, or None if Playwright isn't available.
        """
        try:
            from playwright.async_api import async_playwright

            lead_dir.mkdir(parents=True, exist_ok=True)
            # Write a temporary HTML file for rendering
            tmp_html = lead_dir / f"_critique_round_{round_num}.html"
            tmp_html.write_text(html_content, encoding="utf-8")

            screenshot_path = lead_dir / f"_critique_screenshot_{round_num}.png"

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                await page.goto(tmp_html.resolve().as_uri(), wait_until="networkidle")
                # Wait a moment for fonts/animations
                await page.wait_for_timeout(500)
                await page.screenshot(path=str(screenshot_path), full_page=True)
                await browser.close()

            # Clean up temp HTML
            tmp_html.unlink(missing_ok=True)

            if screenshot_path.exists():
                logger.info(f"Critique screenshot rendered: {screenshot_path.name}")
                return screenshot_path

        except ImportError:
            logger.warning("Playwright not available — critic will judge raw HTML only")
        except Exception as e:
            logger.warning(f"Critique screenshot render failed: {e}")

        return None

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

        award_reference = AWARD_REFERENCE_STYLES.get(lead.industry.lower().strip(), DEFAULT_AWARD_REFERENCE)

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
            award_reference=award_reference,
            phone=lead.phone or "not available — do not add a phone/call button",
            email=lead.email or "not available — do not add an email button",
            address=lead.address or lead.location,
            website_url=lead.website_url or "not available",
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

        # Add map instructions if coordinates are available
        settings = get_settings()
        if lead.latitude is not None and lead.longitude is not None and settings.mapbox_api_key:
            prompt += f"""

INTERACTIVE MAP (REQUIRED): Include a Mapbox GL JS map in the contact/location section.
Use this exact code snippet:
<div id="map" style="width:100%;height:300px;border-radius:12px;margin-top:1.5rem;"></div>
<link href="https://api.mapbox.com/mapbox-gl-js/v3.4.0/mapbox-gl.css" rel="stylesheet">
<script src="https://api.mapbox.com/mapbox-gl-js/v3.4.0/mapbox-gl.js"></script>
<script>
mapboxgl.accessToken='{settings.mapbox_api_key}';
var map=new mapboxgl.Map({{container:'map',style:'mapbox://styles/mapbox/streets-v12',center:[{lead.longitude},{lead.latitude}],zoom:15}});
map.addControl(new mapboxgl.NavigationControl());
new mapboxgl.Marker().setLngLat([{lead.longitude},{lead.latitude}]).addTo(map);
</script>
Place the map div INSIDE the contact section, after the address text."""

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

        # 8192 is qwen-max's hard max_tokens ceiling (DashScope returns 400
        # InvalidParameter above it) — don't raise this without checking the
        # configured model's actual limit first.
        response = await vision.complete(
            messages=[{"role": "user", "content": content_parts}],
            temperature=0.7,
            max_tokens=8192,
        )
        return self._strip_code_fence(response.content)

    async def _critique(self, vision, lead: Lead, html_content: str,
                        reference_images: list[Path], rendered_screenshot: Optional[Path] = None) -> dict:
        """Critic step: score the generated HTML against commercial-quality
        standards AND fidelity to the attached reference designs.

        When a rendered_screenshot is available, the critic judges the actual
        visual output — not just the raw HTML code."""
        prompt = HTML_CRITIQUE_PROMPT.format(
            company_name=lead.company_name,
            industry=lead.industry,
            html_content=html_content if not rendered_screenshot else html_content[:3000] + "\n... (truncated, see rendered screenshot below)",
            award_reference=AWARD_REFERENCE_STYLES.get(lead.industry.lower().strip(), DEFAULT_AWARD_REFERENCE),
        )
        content_parts = [{"type": "text", "text": prompt}]

        # Attach the rendered screenshot so the critic judges what actually rendered
        if rendered_screenshot and rendered_screenshot.exists():
            content_parts.append({
                "type": "text",
                "text": "\n📸 RENDERED SCREENSHOT of the generated page (this is what the client will actually see — judge layout, spacing, visual hierarchy, and responsiveness from THIS image, not just the code above):",
            })
            content_parts.extend(build_image_content_parts([rendered_screenshot]))

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
        """True only for a genuinely complete document — a response that starts
        correctly but got cut off mid-CSS/mid-markup (hitting max_tokens) must not
        be accepted as "valid HTML" just because it starts with <!DOCTYPE>."""
        lowered = content.strip().lower()
        starts_ok = lowered.startswith("<!doctype") or lowered.startswith("<html")
        return starts_ok and lowered.rstrip().endswith("</html>")

    def _generate_fallback_html(self, lead: Lead, style_traits: StyleTraits) -> str:
        """Generate industry-specific fallback HTML with varied layouts."""
        from app.services.fallback_layouts import generate_fallback
        return generate_fallback(lead, style_traits, INDUSTRY_PRESETS, DEFAULT_PRESET)
