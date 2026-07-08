"""
Design Reference Analyzer - extracts style signals from past design screenshots.

Scans the data/design_screenshots/ folder, analyzes each image,
and builds a style profile for HTML generation.
"""

import logging
from typing import Optional

from app.config import get_settings
from app.core.llm_provider import get_vision_provider
from app.core.models import StyleTraits
from app.core.prompts import STYLE_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)


class DesignAnalyzer:
    """Analyzes past design screenshots to extract style signals."""

    def __init__(self):
        self._cached_traits: Optional[StyleTraits] = None

    async def analyze_references(self, force: bool = False) -> StyleTraits:
        """
        Analyze all design screenshots in the references folder.

        Returns aggregated style traits.
        Caches result to avoid re-analyzing on every call.
        """
        if self._cached_traits and not force:
            return self._cached_traits

        settings = get_settings()
        screenshots_dir = settings.design_screenshots_dir

        # Find all image files
        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        images = [
            f for f in screenshots_dir.iterdir()
            if f.is_file() and f.suffix.lower() in image_extensions
        ]

        if not images:
            logger.warning(f"No design screenshots found in {screenshots_dir}")
            # Return default traits
            self._cached_traits = StyleTraits(
                color_palette=["#2C3E50", "#ECF0F1", "#3498DB", "#27AE60", "#E74C3C"],
                typography="modern sans-serif, clean and readable",
                layout_style="clean minimalist with clear sections",
                mood="professional and approachable",
                industry_fit=["retail", "services", "food", "wellness"],
                design_patterns=["hero section", "card grid", "testimonials", "CTA buttons"],
                quality_score=70,
            )
            return self._cached_traits

        logger.info(f"Found {len(images)} design screenshots to analyze")

        # Use vision model to analyze screenshots
        vision = get_vision_provider()

        # Analyze in batches (max 4 images per call for token limits)
        batch_size = 4
        all_traits: list[dict] = []

        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            logger.info(f"Analyzing batch {i // batch_size + 1}: {[img.name for img in batch]}")

            try:
                response = await vision.vision(
                    prompt=STYLE_ANALYSIS_PROMPT,
                    image_paths=batch,
                    temperature=0.3,
                )
                data = response.as_json()
                all_traits.append(data)
            except Exception as e:
                logger.error(f"Vision analysis failed for batch: {e}")
                continue

        # Aggregate traits from all batches
        self._cached_traits = self._aggregate_traits(all_traits)
        logger.info(f"Style analysis complete: {self._cached_traits.model_dump()}")
        return self._cached_traits

    def _aggregate_traits(self, traits_list: list[dict]) -> StyleTraits:
        """Aggregate multiple analysis results into one StyleTraits."""
        if not traits_list:
            return StyleTraits()

        # Normalize: some models return {"style_traits": {...}} or direct traits
        normalized = []
        for t in traits_list:
            if isinstance(t, dict):
                # If wrapped in a key like "style_traits", unwrap it, but keep
                # sibling fields (e.g. design_patterns, quality_score) that live
                # alongside "style_traits" in the same top-level object.
                if "style_traits" in t and isinstance(t["style_traits"], dict):
                    inner = dict(t["style_traits"])
                    for sibling_key in ("design_patterns", "quality_score"):
                        if sibling_key in t and sibling_key not in inner:
                            inner[sibling_key] = t[sibling_key]
                    normalized.append(inner)
                elif "color_palette" in t:
                    normalized.append(t)
                else:
                    # Try to find the first dict value that looks like traits
                    for v in t.values():
                        if isinstance(v, dict) and "color_palette" in v:
                            normalized.append(v)
                            break
                    else:
                        normalized.append(t)
            else:
                continue

        if not normalized:
            return StyleTraits()

        # Merge color palettes (deduplicate)
        all_colors = []
        for t in normalized:
            colors = t.get("color_palette", [])
            if isinstance(colors, list):
                all_colors.extend(colors)
        unique_colors = list(dict.fromkeys(all_colors))[:8]

        # Take most common traits
        all_patterns = []
        for t in normalized:
            patterns = t.get("design_patterns", [])
            if isinstance(patterns, list):
                all_patterns.extend(patterns)
        unique_patterns = list(dict.fromkeys(all_patterns))[:10]

        all_industries = []
        for t in normalized:
            industries = t.get("industry_fit", [])
            if isinstance(industries, list):
                all_industries.extend(industries)
        unique_industries = list(dict.fromkeys(all_industries))[:10]

        # Use the last analysis for text fields (most representative)
        last = normalized[-1]

        return StyleTraits(
            color_palette=unique_colors,
            typography=last.get("typography", "modern sans-serif"),
            layout_style=last.get("layout_style", "clean and modern"),
            mood=last.get("mood", "professional"),
            industry_fit=unique_industries,
            design_patterns=unique_patterns,
            quality_score=int(sum(t.get("quality_score", 70) for t in normalized) / len(normalized)),
        )

    def get_traits_for_industry(self, industry: str) -> StyleTraits:
        """Get cached traits, optionally adjusted for a specific industry."""
        if self._cached_traits:
            return self._cached_traits
        # Return defaults if not yet analyzed
        return StyleTraits(
            color_palette=["#2C3E50", "#ECF0F1", "#3498DB"],
            typography="modern sans-serif",
            layout_style="clean minimalist",
            mood="professional",
            industry_fit=[industry],
            design_patterns=["hero section", "card grid", "CTA buttons"],
            quality_score=70,
        )
