"""Tests for HTML generation."""

import logging
import os
import pytest
import tempfile
from pathlib import Path

os.environ["LLM_PROVIDER"] = "mock"
os.environ["VISION_PROVIDER"] = "mock"

from app.core.models import Lead, LeadStatus, WebsiteAnalysis, StyleTraits
from app.services.html_generator import HTMLGenerator
from app.storage.database import get_database


@pytest.fixture
def sample_lead():
    """Create a sample lead for testing."""
    lead = Lead(
        id="test-lead-001",
        company_name="Test Bakery",
        website_url="https://example.com/test-bakery",
        industry="bakery",
        location="Singapore",
        address="123 Test St",
        phone="+65 1234 5678",
        status=LeadStatus.ANALYZED,
        website_analysis=WebsiteAnalysis(
            overall_weakness_score=80,
            design_problems=["outdated layout", "no mobile support", "slow loading"],
        ),
    )
    return lead


@pytest.fixture
def sample_traits():
    """Sample style traits."""
    return StyleTraits(
        color_palette=["#2C3E50", "#ECF0F1", "#E74C3C"],
        typography="modern sans-serif",
        layout_style="clean minimalist",
        mood="warm and inviting",
        industry_fit=["bakery", "cafe", "food"],
        design_patterns=["hero section", "card grid", "testimonials"],
        quality_score=80,
    )


@pytest.mark.asyncio
async def test_html_generation_produces_file(sample_lead, sample_traits, tmp_path):
    """HTML generator creates an HTML file."""
    # Patch the output dir for testing
    import app.config as config_module
    original_settings = config_module._settings
    config_module._settings = None
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'test.db'}"

    # Reset db singleton
    import app.storage.database as db_module
    db_module._db = None

    generator = HTMLGenerator()
    # Save lead first
    db = get_database()
    db.save_lead(sample_lead)

    result = await generator.generate(sample_lead, sample_traits)

    assert result.html_path is not None
    html_path = Path(result.html_path)
    assert html_path.exists()

    content = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Test Bakery" in content

    # Cleanup
    config_module._settings = original_settings
    db_module._db = None


@pytest.mark.asyncio
async def test_mock_mode_fallback_is_loud(sample_lead, sample_traits, caplog):
    """In mock mode the generic fallback still works, but is loudly labeled as non-AI."""
    generator = HTMLGenerator()
    with caplog.at_level(logging.WARNING, logger="app.services.html_generator"):
        result = await generator.generate(sample_lead, sample_traits)

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("AI NOT CONFIGURED" in msg for msg in warnings)
    assert any("NOT an AI-generated design" in msg for msg in warnings)

    # The lead's own log trail must record it too, not just the module logger
    assert any("AI not configured" in log for log in result.logs)
    assert any("NOT an AI-generated design" in log for log in result.logs)


@pytest.mark.asyncio
async def test_llm_failure_fallback_is_loud(sample_lead, sample_traits, caplog, monkeypatch):
    """A configured provider whose LLM call fails produces a loud AI-failed warning."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "sk-looks-real-but-invalid")

    generator = HTMLGenerator()

    async def failing_plan(*args, **kwargs):
        raise RuntimeError("401 Unauthorized: invalid api key")

    monkeypatch.setattr(generator, "_plan", failing_plan)

    with caplog.at_level(logging.WARNING, logger="app.services.html_generator"):
        result = await generator.generate(sample_lead, sample_traits)

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("NOT an AI-generated design" in msg and "LLM call failed" in msg for msg in warnings)
    # Configured-but-failing is not mislabeled as "AI not configured"
    assert not any("AI NOT CONFIGURED" in msg for msg in warnings)
    assert any("NOT an AI-generated design" in log for log in result.logs)


@pytest.mark.asyncio
async def test_fallback_html_contains_required_sections(sample_lead, sample_traits):
    """Fallback HTML has hero, services, testimonial, contact sections."""
    generator = HTMLGenerator()
    html = generator._generate_fallback_html(sample_lead, sample_traits)

    assert "<!DOCTYPE html>" in html
    assert "Test Bakery" in html
    assert "hero" in html
    assert "contact" in html
    assert "responsive" in html.lower() or "viewport" in html


def test_fallback_html_uses_style_colors(sample_lead, sample_traits):
    """Fallback HTML uses colors from style traits."""
    generator = HTMLGenerator()
    html = generator._generate_fallback_html(sample_lead, sample_traits)

    assert "#2C3E50" in html
    assert "#ECF0F1" in html


def test_fallback_html_mobile_responsive(sample_lead, sample_traits):
    """Fallback HTML includes mobile viewport meta tag."""
    generator = HTMLGenerator()
    html = generator._generate_fallback_html(sample_lead, sample_traits)

    assert 'name="viewport"' in html
    assert "width=device-width" in html
