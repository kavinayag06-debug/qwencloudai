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
INDUSTRY_SCREENSHOT_MAP = {
    "florist": ["florist"],
    "flower": ["florist"],
    "bakery": ["bakery", "dessert"],
    "cafe": ["bakery", "dessert"],
    "dessert": ["dessert", "bakery"],
    "pastry": ["dessert", "bakery"],
    "restaurant": ["bakery", "dessert"],
    "food": ["bakery", "dessert"],
    "fashion": ["fashion"],
    "clothing": ["fashion"],
    "boutique": ["fashion"],
    "retail": ["fashion"],
    "gym": ["sports"],
    "fitness": ["sports"],
    "sports": ["sports"],
    "salon": ["fashion"],
    "spa": ["fashion", "florist"],
}


class DesignAnalyzer:
    """Analyzes past design screenshots to extract style signals per industry."""

    def __init__(self):
        self._cache: dict[str, StyleTraits] = {}

    async def analyze_for_industry(self, industry: str) -> StyleTraits:
        """
        Analyze design screenshots relevant to the given industry.

        Selects only the screenshots that match the industry, sends them
        to the vision model, and returns industry-specific style traits.
        """
        cache_key = industry.lower().strip()
        if cache_key in self._cache:
            return self._cache[cache_key]

        settings = get_settings()
        screenshots_dir = settings.design_screenshots_dir

        # Find relevant screenshots based on industry
        relevant_images = self._select_images_for_industry(screenshots_dir, industry)

        if not relevant_images:
            # Fallback: use ALL available screenshots
            image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
            relevant_images = [
                f for f in screenshots_dir.iterdir()
                if f.is_file() and f.suffix.lower() in image_extensions
            ]

        if not relevant_images:
            logger.warning(f"No design screenshots found for industry '{industry}'")
            traits = self._default_traits(industry)
            self._cache[cache_key] = traits
            return traits

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
        """Select screenshots that match the industry based on filename patterns."""
        industry_lower = industry.lower().strip()
        patterns = INDUSTRY_SCREENSHOT_MAP.get(industry_lower, [])

        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        all_images = [
            f for f in screenshots_dir.iterdir()
            if f.is_file() and f.suffix.lower() in image_extensions
        ]

        if not patterns:
            # No known mapping — try to match industry keyword in filename
            patterns = [industry_lower]

        matched = []
        for img in all_images:
            stem = img.stem.lower()
            for pattern in patterns:
                if pattern in stem:
                    matched.append(img)
                    break

        return matched if matched else all_images

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
        """Return default traits when no screenshots are available."""
        return StyleTraits(
            color_palette=["#2C3E50", "#ECF0F1", "#3498DB", "#27AE60", "#E74C3C"],
            typography="modern sans-serif, clean and readable",
            layout_style="clean minimalist with clear sections",
            mood="professional and approachable",
            industry_fit=[industry, "services"],
            design_patterns=["hero section", "card grid", "testimonials", "CTA buttons"],
            quality_score=70,
        )
