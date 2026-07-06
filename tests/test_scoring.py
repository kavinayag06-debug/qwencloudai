"""Unit tests for confidence scoring logic."""

import pytest
from app.core.models import WebsiteAnalysis, StyleTraits, ConfidenceLevel
from app.core.scoring import compute_confidence, get_routing_decision


def test_high_confidence_score():
    """Test that a weak site with good style fit scores high."""
    analysis = WebsiteAnalysis(
        overall_weakness_score=90,
        design_problems=["no mobile", "outdated layout", "no CTA", "slow", "no trust signals"],
    )
    traits = StyleTraits(
        industry_fit=["restaurant", "cafe"],
        quality_score=85,
    )

    score = compute_confidence(
        analysis=analysis,
        style_traits=traits,
        industry="restaurant",
        html_generated=True,
        email_drafted=True,
    )

    assert score.overall >= 70
    assert score.level == ConfidenceLevel.HIGH


def test_low_confidence_no_problems():
    """Test that a site with no problems scores low."""
    analysis = WebsiteAnalysis(
        overall_weakness_score=20,
        design_problems=[],
    )

    score = compute_confidence(
        analysis=analysis,
        style_traits=None,
        industry="unknown",
    )

    assert score.overall < 50
    assert score.level == ConfidenceLevel.LOW


def test_medium_confidence():
    """Test medium confidence case."""
    analysis = WebsiteAnalysis(
        overall_weakness_score=70,
        design_problems=["slow loading", "no mobile", "no CTA"],
    )
    traits = StyleTraits(
        industry_fit=["salon", "spa"],
        quality_score=75,
    )

    score = compute_confidence(
        analysis=analysis,
        style_traits=traits,
        industry="salon",
        html_generated=True,
        email_drafted=True,
    )

    assert 50 <= score.overall < 75
    assert score.level == ConfidenceLevel.MEDIUM


def test_routing_decision_high():
    """High confidence leads are eligible for send."""
    analysis = WebsiteAnalysis(overall_weakness_score=90,
                               design_problems=["a", "b", "c", "d", "e"])
    traits = StyleTraits(industry_fit=["florist"], quality_score=90)
    score = compute_confidence(analysis, traits, "florist", True, True)
    decision = get_routing_decision(score)
    assert decision == "eligible_for_send"


def test_routing_decision_low():
    """Low confidence leads are draft only."""
    analysis = WebsiteAnalysis(overall_weakness_score=15, design_problems=[])
    score = compute_confidence(analysis, None, "")
    decision = get_routing_decision(score)
    assert decision == "draft_only"


def test_compute_overall_weights():
    """Test that compute_overall uses correct weights."""
    from app.core.models import ConfidenceScore
    score = ConfidenceScore(
        website_weakness=100,
        style_fit=100,
        industry_match=100,
        opportunity_clarity=100,
        html_quality=100,
        outreach_confidence=100,
    )
    score.compute_overall()
    assert score.overall == 100


def test_compute_overall_zero():
    """Test all zeros gives zero."""
    from app.core.models import ConfidenceScore
    score = ConfidenceScore(
        website_weakness=0,
        style_fit=0,
        industry_match=0,
        opportunity_clarity=0,
        html_quality=0,
        outreach_confidence=0,
    )
    score.compute_overall()
    assert score.overall == 0
