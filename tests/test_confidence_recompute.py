"""Tests for confidence recompute after HTML generation and email drafting (C-2)."""

import os

import pytest

os.environ["LLM_PROVIDER"] = "mock"
os.environ["VISION_PROVIDER"] = "mock"

from app.core.models import ConfidenceLevel, Lead, LeadStatus, StyleTraits, WebsiteAnalysis
from app.core.scoring import compute_confidence
from app.services.email_service import EmailService
from app.services.html_generator import HTMLGenerator


@pytest.fixture
def analyzed_lead():
    """A lead as it looks right after SiteAnalyzer.analyze, before HTML/email exist."""
    analysis = WebsiteAnalysis(
        overall_weakness_score=80,
        design_problems=["outdated layout", "no mobile support", "slow loading"],
    )
    lead = Lead(
        id="test-lead-recompute",
        company_name="Test Bakery",
        website_url="https://example.com/test-bakery",
        industry="bakery",
        location="Singapore",
        status=LeadStatus.ANALYZED,
        website_analysis=analysis,
    )
    # Mirrors SiteAnalyzer.analyze: computed once, before html/email exist.
    lead.confidence = compute_confidence(
        analysis=analysis, style_traits=None, industry=lead.industry
    )
    return lead


@pytest.fixture
def sample_traits():
    return StyleTraits(
        color_palette=["#2C3E50", "#ECF0F1", "#E74C3C"],
        typography="modern sans-serif",
        layout_style="clean minimalist",
        mood="warm and inviting",
        industry_fit=["bakery", "cafe", "food"],
        design_patterns=["hero section", "card grid", "testimonials"],
        quality_score=80,
    )


def test_initial_confidence_has_zeroed_html_and_outreach(analyzed_lead):
    """Sanity check on the fixture: matches the documented pre-fix bug state."""
    assert analyzed_lead.confidence.html_quality == 0
    assert analyzed_lead.confidence.outreach_confidence == 0


async def test_html_generation_recomputes_confidence(analyzed_lead, sample_traits, tmp_path, monkeypatch):
    """After HTML generation, html_quality must no longer be stuck at 0."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    import app.storage.database as db_module
    db_module._db = None

    from app.storage.database import get_database
    get_database().save_lead(analyzed_lead)

    result = await HTMLGenerator().generate(analyzed_lead, sample_traits)

    assert result.confidence is not None
    assert result.confidence.html_quality > 0
    # Email hasn't been drafted yet at this point in the pipeline.
    assert result.confidence.outreach_confidence == 0


async def test_email_draft_recomputes_confidence(analyzed_lead, tmp_path, monkeypatch):
    """After drafting the email, outreach_confidence must no longer be stuck at 0."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    import app.storage.database as db_module
    db_module._db = None

    from app.storage.database import get_database
    get_database().save_lead(analyzed_lead)

    result = await EmailService().draft_email(analyzed_lead)

    assert result.confidence is not None
    assert result.confidence.outreach_confidence > 0


async def test_full_pipeline_recompute_unlocks_high_confidence(analyzed_lead, sample_traits, tmp_path, monkeypatch):
    """Once both html_quality and outreach_confidence are scored, overall can clear the HIGH cutoff."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    import app.storage.database as db_module
    db_module._db = None

    from app.storage.database import get_database
    get_database().save_lead(analyzed_lead)

    analyzed_lead.style_traits = sample_traits
    lead = await HTMLGenerator().generate(analyzed_lead, sample_traits)
    lead = await EmailService().draft_email(lead)

    assert lead.confidence.html_quality > 0
    assert lead.confidence.outreach_confidence > 0
    assert lead.confidence.overall >= 75
    assert lead.confidence.level == ConfidenceLevel.HIGH
