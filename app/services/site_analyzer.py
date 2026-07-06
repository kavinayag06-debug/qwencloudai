"""
Site Analyzer Service - analyzes target websites for redesign opportunity.

Evaluates:
- Visual age / modernity
- Responsiveness
- Content clarity
- CTA quality
- Trust signals
- Layout density
- Mobile friendliness
- Design problems
"""

import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.core.llm_provider import get_llm_provider
from app.core.models import Lead, LeadStatus, WebsiteAnalysis
from app.core.prompts import WEBSITE_ANALYSIS_PROMPT
from app.core.scoring import compute_confidence
from app.storage.database import get_database

logger = logging.getLogger(__name__)


class SiteAnalyzer:
    """Analyzes websites for redesign opportunities."""

    async def analyze(self, lead: Lead) -> Lead:
        """Analyze a lead's website and update the lead."""
        logger.info(f"Analyzing website for {lead.company_name}: {lead.website_url}")
        lead.add_log(f"Starting website analysis: {lead.website_url}")

        # Fetch page content
        page_content = await self._fetch_page_content(lead.website_url)

        if not page_content:
            lead.add_log("Warning: Could not fetch website content, using description")
            page_content = lead.description or "Website could not be reached"

        # Use LLM to analyze
        llm = get_llm_provider()
        prompt = WEBSITE_ANALYSIS_PROMPT.format(
            url=lead.website_url,
            industry=lead.industry,
            location=lead.location,
            page_content=page_content[:3000],
        )

        try:
            response = await llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                json_mode=True,
            )
            data = response.as_json()

            lead.website_analysis = WebsiteAnalysis(
                visual_age=data.get("visual_age", ""),
                modernity_score=data.get("modernity_score", 50),
                responsiveness=data.get("responsiveness", ""),
                responsiveness_score=data.get("responsiveness_score", 50),
                content_clarity=data.get("content_clarity", ""),
                content_clarity_score=data.get("content_clarity_score", 50),
                cta_quality=data.get("cta_quality", ""),
                cta_score=data.get("cta_score", 50),
                trust_signals=data.get("trust_signals", ""),
                trust_score=data.get("trust_score", 50),
                layout_density=data.get("layout_density", ""),
                layout_score=data.get("layout_score", 50),
                mobile_friendliness=data.get("mobile_friendliness", ""),
                mobile_score=data.get("mobile_score", 50),
                design_problems=data.get("design_problems", []),
                industry_fit=data.get("industry_fit", ""),
                overall_weakness_score=data.get("overall_weakness_score", 50),
                summary=data.get("summary", ""),
            )

            # Compute confidence score
            lead.confidence = compute_confidence(
                analysis=lead.website_analysis,
                style_traits=lead.style_traits,
                industry=lead.industry,
            )

            lead.status = LeadStatus.ANALYZED
            lead.add_log(f"Analysis complete. Weakness score: {lead.website_analysis.overall_weakness_score}")

        except Exception as e:
            logger.error(f"Analysis failed for {lead.company_name}: {e}")
            lead.add_log(f"Analysis failed: {str(e)}")
            # Create default analysis
            lead.website_analysis = WebsiteAnalysis(
                summary=f"Analysis failed: {str(e)}",
                design_problems=["Could not analyze website"],
                overall_weakness_score=50,
            )

        # Save
        db = get_database()
        db.save_lead(lead)
        return lead

    async def _fetch_page_content(self, url: str) -> Optional[str]:
        """Fetch and extract text content from a URL."""
        if not url or url.startswith("https://example.com"):
            return None

        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            ) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None

                soup = BeautifulSoup(response.text, "html.parser")
                # Remove scripts and styles
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                text = soup.get_text(separator="\n", strip=True)
                return text[:5000]

        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
