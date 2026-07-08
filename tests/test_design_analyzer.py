"""Tests for DesignAnalyzer._aggregate_traits (C-3)."""

import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ["VISION_PROVIDER"] = "mock"

from app.services.design_analyzer import DesignAnalyzer


def test_aggregate_traits_preserves_siblings_of_style_traits_wrapper():
    """design_patterns/quality_score living alongside a style_traits wrapper must survive."""
    # Shape returned by MockProvider.vision() (app/core/llm_provider.py) and,
    # per the audit, plausibly by real vision providers too.
    raw_response = {
        "style_traits": {
            "color_palette": ["#2C3E50", "#ECF0F1", "#3498DB", "#E74C3C"],
            "typography": "modern sans-serif",
            "layout_style": "clean minimalist",
            "mood": "professional and approachable",
            "industry_fit": ["retail", "services", "food"],
        },
        "design_patterns": ["hero section", "grid cards", "sticky nav", "CTA buttons"],
        "quality_score": 82,
    }

    traits = DesignAnalyzer()._aggregate_traits([raw_response])

    assert traits.design_patterns == ["hero section", "grid cards", "sticky nav", "CTA buttons"]
    assert traits.quality_score == 82
    assert traits.color_palette == ["#2C3E50", "#ECF0F1", "#3498DB", "#E74C3C"]


def test_aggregate_traits_still_handles_flat_response():
    """Responses without a style_traits wrapper (already flat) keep working."""
    raw_response = {
        "color_palette": ["#111111", "#222222"],
        "typography": "serif",
        "layout_style": "grid",
        "mood": "bold",
        "industry_fit": ["gym"],
        "design_patterns": ["hero section"],
        "quality_score": 60,
    }

    traits = DesignAnalyzer()._aggregate_traits([raw_response])

    assert traits.design_patterns == ["hero section"]
    assert traits.quality_score == 60


def test_aggregate_traits_averages_quality_score_across_batches():
    """Multiple wrapped batches should merge design_patterns and average quality_score."""
    batch_1 = {
        "style_traits": {"color_palette": ["#111"], "mood": "calm"},
        "design_patterns": ["hero section"],
        "quality_score": 80,
    }
    batch_2 = {
        "style_traits": {"color_palette": ["#222"], "mood": "bold"},
        "design_patterns": ["card grid"],
        "quality_score": 60,
    }

    traits = DesignAnalyzer()._aggregate_traits([batch_1, batch_2])

    assert set(traits.design_patterns) == {"hero section", "card grid"}
    assert traits.quality_score == 70
