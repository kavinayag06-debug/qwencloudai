"""Tests for HTML generation."""

import logging
import os
import pytest
import tempfile
from pathlib import Path

import httpx

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
    monkeypatch.setenv("VISION_PROVIDER", "openai")
    monkeypatch.setenv("VISION_API_KEY", "sk-looks-real-but-invalid")

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


def test_stock_images_module_is_gone():
    """Regression guard: stock photography must never be reintroduced as a
    hidden fallback path, in mock mode or otherwise."""
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.services.stock_images")


@pytest.mark.asyncio
async def test_no_source_image_produces_photo_free_design(sample_lead, sample_traits, tmp_path):
    """A lead with no source-business photos (the mock/example.com case) must
    never receive a stock photo — the generated site is photo-free instead."""
    import app.config as config_module
    config_module._settings = None
    import app.storage.database as db_module
    db_module._db = None

    generator = HTMLGenerator()
    db = get_database()
    db.save_lead(sample_lead)

    assert sample_lead.source_image_urls == []  # example.com URL never yields candidates

    result = await generator.generate(sample_lead, sample_traits)

    assert result.local_image_paths == []
    assert any("photo-free" in log for log in result.logs)
    # No stray reference to a downloaded/stock image filename anywhere in the output
    html_path = Path(result.html_path)
    content = html_path.read_text(encoding="utf-8")
    assert "images/photo_" not in content

    config_module._settings = None
    db_module._db = None


@pytest.mark.asyncio
async def test_source_photo_extraction_failure_is_logged_distinctly(sample_lead, sample_traits, monkeypatch):
    """A lead that DID have candidate source-photo URLs, but where every
    download/filter check failed, must log a distinct message from the
    "never had any candidates" case — not the same generic line."""
    sample_lead.source_image_urls = ["https://realbiz.example/photo1.jpg"]

    import httpx as httpx_module

    class FailingResponse:
        status_code = 404
        headers = {}
        content = b""

    async def failing_get(self, url):
        return FailingResponse()

    monkeypatch.setattr(httpx_module.AsyncClient, "get", failing_get)

    generator = HTMLGenerator()
    result = await generator.generate(sample_lead, sample_traits)

    assert result.local_image_paths == []
    assert any("extraction failed" in log for log in result.logs)
    assert not any("No source-business photos available" in log for log in result.logs)


@pytest.mark.asyncio
async def test_google_photo_fallback_does_not_log_photo_free_design(
    sample_lead, tmp_path, monkeypatch
):
    sample_lead.source_image_urls = ["https://realbiz.example/missing.jpg"]
    sample_lead.google_photo_refs = ["places/example/photos/1"]

    class Response:
        content = b"real image bytes"

        def __init__(self, status_code, content_type=""):
            self.status_code = status_code
            self.headers = {"content-type": content_type}

    async def fake_get(self, url, params=None):
        if "places.googleapis.com" in url:
            return Response(200, "image/jpeg")
        return Response(404)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(
        "app.services.html_generator.get_settings",
        lambda: type("Settings", (), {"google_maps_api_key": "test-key"})(),
    )

    saved = await HTMLGenerator()._prepare_images(sample_lead, tmp_path)

    assert saved == ["gphoto_1.jpg"]
    assert any("Google Places photos" in log for log in sample_lead.logs)
    assert not any("photo-free" in log for log in sample_lead.logs)
