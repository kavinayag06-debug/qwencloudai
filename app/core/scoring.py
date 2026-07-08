"""Confidence scoring logic."""

from app.core.models import ConfidenceScore, ConfidenceLevel, WebsiteAnalysis, StyleTraits


def compute_confidence(
    analysis: WebsiteAnalysis,
    style_traits: StyleTraits | None = None,
    industry: str = "",
    html_generated: bool = False,
    email_drafted: bool = False,
    html_quality_score: int | None = None,
) -> ConfidenceScore:
    """
    Compute transparent confidence score for a lead.

    Scoring breakdown:
    - website_weakness (25%): How badly the site needs redesign
    - style_fit (15%): How well our style references match
    - industry_match (15%): How well we can serve this industry
    - opportunity_clarity (20%): How clear the redesign opportunity is
    - html_quality (15%): Quality of generated redesign
    - outreach_confidence (10%): Confidence in outreach copy
    """
    score = ConfidenceScore()

    # Website weakness: higher = more opportunity
    score.website_weakness = analysis.overall_weakness_score

    # Style fit: based on whether we have relevant style references
    if style_traits:
        if industry.lower() in [i.lower() for i in style_traits.industry_fit]:
            score.style_fit = 85
        elif style_traits.quality_score > 70:
            score.style_fit = 65
        else:
            score.style_fit = 45
    else:
        score.style_fit = 30

    # Industry match: certain industries are easier to redesign
    high_opportunity_industries = [
        "restaurant", "cafe", "bakery", "florist", "salon",
        "spa", "retail", "boutique", "clinic", "gym"
    ]
    if industry.lower() in high_opportunity_industries:
        score.industry_match = 80
    elif industry:
        score.industry_match = 55
    else:
        score.industry_match = 35

    # Opportunity clarity: based on number of clear problems
    num_problems = len(analysis.design_problems)
    if num_problems >= 5:
        score.opportunity_clarity = 90
    elif num_problems >= 3:
        score.opportunity_clarity = 70
    elif num_problems >= 1:
        score.opportunity_clarity = 50
    else:
        score.opportunity_clarity = 30

    # HTML quality: use the critic's actual score if available, else a flat base score
    if html_generated:
        score.html_quality = html_quality_score if html_quality_score is not None else 70
    else:
        score.html_quality = 0

    # Outreach confidence
    if email_drafted:
        score.outreach_confidence = 70
    else:
        score.outreach_confidence = 0

    score.compute_overall()
    return score


def get_routing_decision(score: ConfidenceScore) -> str:
    """
    Determine routing based on confidence level.

    - HIGH: eligible for one-click approval and sending
    - MEDIUM: requires manual review before sending
    - LOW: draft only, do not send
    """
    if score.level == ConfidenceLevel.HIGH:
        return "eligible_for_send"
    elif score.level == ConfidenceLevel.MEDIUM:
        return "requires_review"
    else:
        return "draft_only"
