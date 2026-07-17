"""Tests for DesignAnalyzer industry-specific screenshot selection and trait parsing."""

import os
from pathlib import Path

os.environ["LLM_PROVIDER"] = "mock"
os.environ["VISION_PROVIDER"] = "mock"

from app.services.design_analyzer import DesignAnalyzer


def test_select_images_for_florist_industry(tmp_path):
    """Florist industry selects florist-named screenshots."""
    # Create fake screenshots
    (tmp_path / "florist.jpg").write_bytes(b"fake")
    (tmp_path / "bakery.jpg").write_bytes(b"fake")
    (tmp_path / "fashion.jpg").write_bytes(b"fake")

    analyzer = DesignAnalyzer()
    selected = analyzer._select_images_for_industry(tmp_path, "florist")
    names = [p.name for p in selected]
    assert "florist.jpg" in names
    assert "bakery.jpg" not in names


def test_select_images_for_bakery_includes_dessert(tmp_path):
    """Bakery industry selects bakery and dessert screenshots."""
    (tmp_path / "bakery.jpg").write_bytes(b"fake")
    (tmp_path / "dessert1.jpg").write_bytes(b"fake")
    (tmp_path / "dessert2.jpg").write_bytes(b"fake")
    (tmp_path / "fashion.jpg").write_bytes(b"fake")

    analyzer = DesignAnalyzer()
    selected = analyzer._select_images_for_industry(tmp_path, "bakery")
    names = [p.name for p in selected]
    assert "bakery.jpg" in names
    assert "dessert1.jpg" in names
    assert "dessert2.jpg" in names
    assert "fashion.jpg" not in names


def test_select_images_falls_back_to_all_when_no_match(tmp_path):
    """Unknown industry falls back to all available screenshots."""
    (tmp_path / "bakery.jpg").write_bytes(b"fake")
    (tmp_path / "fashion.jpg").write_bytes(b"fake")

    analyzer = DesignAnalyzer()
    selected = analyzer._select_images_for_industry(tmp_path, "plumbing")
    # Should return all since no pattern matches
    assert len(selected) == 2


def test_parse_traits_handles_wrapped_response():
    """Vision model response wrapped in style_traits key is parsed correctly."""
    raw = {
        "style_traits": {
            "color_palette": ["#2C3E50", "#ECF0F1"],
            "typography": "serif",
            "layout_style": "elegant",
            "mood": "luxurious",
            "industry_fit": ["florist"],
        },
        "design_patterns": ["hero section", "gallery"],
        "quality_score": 85,
    }
    analyzer = DesignAnalyzer()
    traits = analyzer._parse_traits(raw, "florist")
    assert traits.color_palette == ["#2C3E50", "#ECF0F1"]
    assert traits.design_patterns == ["hero section", "gallery"]
    assert traits.quality_score == 85
    assert traits.mood == "luxurious"


def test_parse_traits_handles_flat_response():
    """Flat response without wrapper is parsed correctly."""
    raw = {
        "color_palette": ["#111", "#222"],
        "typography": "sans-serif",
        "layout_style": "grid",
        "mood": "bold",
        "industry_fit": ["gym"],
        "design_patterns": ["hero section"],
        "quality_score": 60,
    }
    analyzer = DesignAnalyzer()
    traits = analyzer._parse_traits(raw, "gym")
    assert traits.design_patterns == ["hero section"]
    assert traits.quality_score == 60
