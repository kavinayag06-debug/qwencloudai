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
from urllib.parse import urljoin, urlparse

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

        # Fetch page content + preferred real photos from the business's own
        # site. If none are usable, generation may use that business's Google
        # Places photos or produce a photo-free design, never stock imagery.
        is_placeholder_url = not lead.website_url or lead.website_url.startswith("https://example.com")
        page_content, image_urls = await self._fetch_page(lead.website_url)
        lead.source_image_urls = image_urls
        if image_urls:
            lead.add_log(f"Found {len(image_urls)} candidate photos on the original site")
        elif is_placeholder_url:
            lead.add_log("Source URL is a placeholder/test URL — no real site to extract photos from")
        else:
            lead.add_log("No usable candidate photos found on the original site")

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
            # Handle case where model returns a list instead of dict
            if isinstance(data, list) and len(data) > 0:
                data = data[0] if isinstance(data[0], dict) else {}
            if not isinstance(data, dict):
                data = {}

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

    async def _fetch_page(self, url: str) -> tuple[Optional[str], list[str]]:
        """Fetch a URL once and extract both text content and candidate photo URLs.

        Returns (text_content, image_urls). image_urls is ordered by likely
        relevance: og:image first, then <img> tags with real business photos
        (icons, logos, and tracking pixels are filtered out heuristically).
        """
        if not url or url.startswith("https://example.com"):
            return None, []

        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            ) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None, []

                soup = BeautifulSoup(response.text, "html.parser")
                image_urls = self._extract_image_urls(soup, str(response.url))

                # Remove scripts and styles before extracting text
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                text = soup.get_text(separator="\n", strip=True)
                return text[:5000], image_urls

        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None, []

    @staticmethod
    def _extract_image_urls(soup: BeautifulSoup, base_url: str, limit: int = 8) -> list[str]:
        """Pull real, likely-relevant photo URLs from a parsed page.

        Heuristics: prefer og:image / twitter:image (usually the site's best
        hero photo), then large <img> tags, skipping obvious icons, logos,
        tracking pixels, and data: URIs (which we can't safely re-host).
        """
        skip_hints = ("logo", "icon", "sprite", "pixel", "avatar", "badge", "spinner",
                      "placeholder", "loading", "blank", "transparent", "favicon", "svg")
        urls: list[str] = []
        seen = set()

        def add(candidate: Optional[str]):
            if not candidate or candidate.startswith("data:"):
                return
            resolved = urljoin(base_url, candidate.strip())
            parsed = urlparse(resolved)
            if parsed.scheme not in ("http", "https"):
                return
            lowered = resolved.lower()
            if any(hint in lowered for hint in skip_hints):
                return
            # Skip SVG files (usually logos/icons, not photos)
            if lowered.endswith(".svg"):
                return
            if resolved not in seen:
                seen.add(resolved)
                urls.append(resolved)

        for meta_name in ("og:image", "og:image:secure_url", "twitter:image"):
            tag = soup.find("meta", attrs={"property": meta_name}) or soup.find("meta", attrs={"name": meta_name})
            if tag and tag.get("content"):
                add(tag["content"])

        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            # Skip tiny images (width/height attrs are a weak but free signal)
            try:
                width = int(img.get("width", 0) or 0)
                height = int(img.get("height", 0) or 0)
                if 0 < width < 80 or 0 < height < 80:
                    continue
            except ValueError:
                pass
            add(src)
            if len(urls) >= limit:
                break

        return urls[:limit]
