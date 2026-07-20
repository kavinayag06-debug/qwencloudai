"""
Design Reference Analyzer - extracts style signals from past design screenshots.

The agent selects industry-relevant screenshots from data/design_screenshots/
based on the target business's industry, then analyzes only those to produce
style traits that directly inform the HTML generation.

Screenshots should be named by industry/category (e.g. florist.jpg, bakery.jpg).
"""

import logging
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.core.llm_provider import get_vision_provider
from app.core.models import StyleTraits
from app.core.prompts import STYLE_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)

# Mapping of industry keywords to screenshot filename patterns.
# The agent uses this to pick which reference designs are relevant.
# Each industry should have its own dedicated references — avoid aliasing
# unrelated industries (e.g. don't give restaurant bakery's screenshots).
INDUSTRY_SCREENSHOT_MAP = {
    "florist": ["florist", "flower"],
    "flower": ["florist", "flower"],
    "bakery": ["bakery", "dessert"],
    "cafe": ["cafe", "coffee", "bakery"],
    "dessert": ["dessert", "bakery"],
    "pastry": ["dessert", "bakery"],
    "restaurant": ["restaurant", "food"],
    "food": ["restaurant", "food", "cafe"],
    "fashion": ["fashion", "boutique"],
    "clothing": ["fashion", "clothing"],
    "boutique": ["fashion", "boutique"],
    "retail": ["retail", "fashion"],
    "gym": ["gym", "fitness", "sports"],
    "fitness": ["fitness", "gym", "sports"],
    "sports": ["sports", "gym", "fitness"],
    "salon": ["salon", "beauty", "fashion"],
    "beauty": ["salon", "beauty"],
    "spa": ["spa", "wellness"],
    "wellness": ["spa", "wellness"],
    "clinic": ["clinic", "medical", "health"],
    "medical": ["clinic", "medical", "health"],
    "health": ["clinic", "medical", "health"],
}


class DesignAnalyzer:
    """Analyzes past design screenshots to extract style signals per industry."""

    def __init__(self):
        self._cache: dict[str, StyleTraits] = {}

    async def analyze_for_industry(self, industry: str) -> StyleTraits:
        """
        Analyze design screenshots relevant to the given industry.

        Primary path: scrape template marketplaces (Themeforest, Framer, Webflow)
        for real commercial references. Uses a 14-day cache so it doesn't re-scrape
        every time.

        Fallback: if scraping fails or returns nothing, uses any local screenshots
        that match the industry. If those also don't exist, uses category-aware defaults.
        """
        cache_key = industry.lower().strip()
        if cache_key in self._cache:
            return self._cache[cache_key]

        settings = get_settings()
        screenshots_dir = settings.design_screenshots_dir

        # PRIMARY: Always try scraping marketplaces first (cached for 14 days)
        from app.services.reference_scraper import scrape_references_for_industry, is_fresh
        scrape_succeeded = False
        logger.info(f"Building reference library for '{industry}' from template marketplaces...")
        try:
            await scrape_references_for_industry(industry)
            scrape_succeeded = is_fresh(cache_key)
        except Exception as e:
            logger.warning(f"Reference scraping failed for '{industry}': {e}")

        # Now check what we have (scraped + any pre-existing local screenshots)
        relevant_images = self._select_images_for_industry(screenshots_dir, industry)

        if not relevant_images:
            # Nothing from scraping or local — use category-aware defaults
            logger.warning(f"No references for '{industry}' even after scraping; using generic defaults")
            traits = self._default_traits(industry)
            traits.reference_source = "defaults"
            self._cache[cache_key] = traits
            return traits

        # Determine reference source for UI display
        if scrape_succeeded:
            reference_source = "scraped"
        else:
            reference_source = "local_fallback"
            logger.warning(f"⚠ Scraper failed for '{industry}' — using pre-existing local screenshots as fallback")

        logger.info(
            f"Selected {len(relevant_images)} reference screenshots for '{industry}': "
            f"{[img.name for img in relevant_images]}"
        )

        # Analyze with vision model
        vision = get_vision_provider()
        prompt = STYLE_ANALYSIS_PROMPT + (
            f"\n\nContext: These designs are being used as style references for a "
            f"'{industry}' business. Focus on extracting style elements that would "
            f"work well for a {industry} landing page."
        )

        try:
            response = await vision.vision(
                prompt=prompt,
                image_paths=relevant_images[:4],  # Max 4 images per call
                temperature=0.3,
            )
            data = response.as_json()
            traits = self._parse_traits(data, industry)
        except Exception as e:
            logger.error(f"Vision analysis failed for '{industry}': {e}")
            traits = self._default_traits(industry)

        # Store the actual image paths so HTML generator can pass them to the model
        traits.reference_image_paths = [str(p) for p in relevant_images]
        traits.reference_source = reference_source

        self._cache[cache_key] = traits
        logger.info(f"Style analysis for '{industry}': mood={traits.mood}, colors={traits.color_palette}")
        return traits

    async def analyze_references(self, force: bool = False) -> StyleTraits:
        """Legacy method — analyze all screenshots generically."""
        return await self.analyze_for_industry("general")

    def get_reference_images_for_industry(self, industry: str) -> list[Path]:
        """Get the file paths of reference screenshots relevant to an industry."""
        settings = get_settings()
        return self._select_images_for_industry(settings.design_screenshots_dir, industry)

    def _select_images_for_industry(self, screenshots_dir: Path, industry: str) -> list[Path]:
        """Select screenshots that match the industry based on filename patterns.

        Searches both flat files (e.g. bakery.jpg) and subdirectories
        (e.g. restaurant/themeforest_1.png) under screenshots_dir.
        """
        industry_lower = industry.lower().strip()
        patterns = INDUSTRY_SCREENSHOT_MAP.get(industry_lower, [industry_lower])

        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

        # Collect all images: flat files + files inside subdirectories
        all_images = []
        for item in screenshots_dir.iterdir():
            if item.is_file() and item.suffix.lower() in image_extensions:
                all_images.append(item)
            elif item.is_dir() and not item.name.startswith("."):
                # Include all images from subdirectories
                for sub_item in item.iterdir():
                    if sub_item.is_file() and sub_item.suffix.lower() in image_extensions:
                        all_images.append(sub_item)

        matched = []
        for img in all_images:
            # Match against: filename stem, or parent directory name
            stem = img.stem.lower()
            parent_name = img.parent.name.lower()
            for pattern in patterns:
                if pattern in stem or pattern == parent_name:
                    matched.append(img)
                    break

        # No "else all_images" fallback here on purpose: showing the vision model
        # every screenshot regardless of industry (e.g. bakery photos for a clinic)
        # produces style traits with no real relation to the business. The caller
        # (analyze_for_industry) falls back to generic defaults instead.
        return matched

    def _parse_traits(self, data: dict, industry: str) -> StyleTraits:
        """Parse the vision model response into StyleTraits."""
        # Handle wrapped responses
        if "style_traits" in data and isinstance(data["style_traits"], dict):
            inner = dict(data["style_traits"])
            for key in ("design_patterns", "quality_score"):
                if key in data and key not in inner:
                    inner[key] = data[key]
            data = inner

        return StyleTraits(
            color_palette=data.get("color_palette", []),
            typography=data.get("typography", "modern sans-serif"),
            layout_style=data.get("layout_style", "clean and modern"),
            mood=data.get("mood", "professional"),
            industry_fit=data.get("industry_fit", [industry]),
            design_patterns=data.get("design_patterns", []),
            quality_score=data.get("quality_score", 70),
        )

    def _default_traits(self, industry: str) -> StyleTraits:
        """Return category-aware default traits when no screenshots are available."""
        logger.warning(
            f"⚠ _default_traits() fired for industry='{industry}' — "
            f"output will use generic palette, not AI-analyzed style. "
            f"Add matching screenshots to data/design_screenshots/ to fix this."
        )

        # Category-specific defaults instead of one universal bland palette
        CATEGORY_DEFAULTS = {
            "food": {
                "color_palette": ["#8B1A1A", "#FFF8E7", "#D4A017", "#1A1A1A", "#F5E6D3"],
                "typography": "warm serif heading (Merriweather, Playfair Display) with clean sans body",
                "layout_style": "full-bleed hero with warm editorial sections",
                "mood": "warm, inviting, appetizing",
            },
            "beauty": {
                "color_palette": ["#C4547A", "#FFF5F7", "#2C2C2C", "#E8B4B8", "#1A1A1A"],
                "typography": "bold display heading (Montserrat, Oswald) with elegant sans body",
                "layout_style": "editorial fashion-magazine composition with bold typography",
                "mood": "stylish, confident, bold",
            },
            "wellness": {
                "color_palette": ["#5B7B7A", "#F7F3EF", "#C9B99A", "#2C3E3D", "#E8DFD4"],
                "typography": "elegant thin serif (Cormorant Garamond) with minimal sans body",
                "layout_style": "immersive full-bleed with generous whitespace",
                "mood": "serene, luxurious, calming",
            },
            "fitness": {
                "color_palette": ["#E63946", "#1D3557", "#F1FAEE", "#457B9D", "#000000"],
                "typography": "bold uppercase display (Oswald) with strong geometric sans body",
                "layout_style": "angular section breaks with high contrast",
                "mood": "energetic, powerful, motivating",
            },
            "retail": {
                "color_palette": ["#1A1A1A", "#FAFAFA", "#C9A96E", "#333333", "#F5F5F5"],
                "typography": "elegant display (Playfair Display) with clean sans body",
                "layout_style": "disciplined grid with editorial photography",
                "mood": "elegant, curated, premium",
            },
        }

        # Map industries to broad categories
        INDUSTRY_CATEGORY = {
            "restaurant": "food", "cafe": "food", "bakery": "food",
            "dessert": "food", "food": "food",
            "salon": "beauty", "fashion": "beauty", "boutique": "beauty",
            "spa": "wellness", "clinic": "wellness",
            "gym": "fitness", "sports": "fitness", "fitness": "fitness",
            "retail": "retail", "clothing": "retail",
        }

        category = INDUSTRY_CATEGORY.get(industry.lower().strip(), None)
        defaults = CATEGORY_DEFAULTS.get(category, {})

        return StyleTraits(
            color_palette=defaults.get("color_palette", ["#2C3E50", "#ECF0F1", "#3498DB", "#27AE60", "#E74C3C"]),
            typography=defaults.get("typography", "modern sans-serif, clean and readable"),
            layout_style=defaults.get("layout_style", "clean minimalist with clear sections"),
            mood=defaults.get("mood", "professional and approachable"),
            industry_fit=[industry, "services"],
            design_patterns=["hero section", "card grid", "testimonials", "CTA buttons"],
            quality_score=70,
        )
