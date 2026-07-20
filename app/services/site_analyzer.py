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

        # Fetch page content + real photos from the business's own site. These
        # photos (not stock/placeholder images) are what the redesign will use,
        # so the client's landing page always shows real, relevant imagery.
        page_content, image_urls = await self._fetch_page(lead.website_url)
        lead.source_image_urls = image_urls
        if image_urls:
            lead.add_log(f"Found {len(image_urls)} candidate photos on the original site")

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
        """Fetch a URL and extract both text content and candidate photo URLs.

        Primary: Uses Playwright to render JS-heavy pages, scroll to trigger
        lazy-loading, then extracts images from the live DOM (covers srcset,
        data-original, CSS background-image on hero elements, etc.)

        Fallback: plain httpx GET + BeautifulSoup if Playwright unavailable.

        Returns (text_content, image_urls).
        """
        if not url or url.startswith("https://example.com"):
            return None, []

        # Try Playwright first — renders JS, scrolls for lazy content
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                await page.goto(url, wait_until="networkidle", timeout=25000)

                # Scroll down to trigger lazy-loaded images
                for _ in range(5):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await page.wait_for_timeout(400)
                await page.evaluate("window.scrollTo(0, 0)")

                # Extract images from the live rendered DOM
                image_urls = await page.evaluate("""() => {
                    const skip = /logo|icon|sprite|pixel|avatar|badge|spinner|data:/i;
                    const urls = new Set();

                    // og:image and twitter:image
                    document.querySelectorAll('meta[property="og:image"], meta[name="twitter:image"]')
                        .forEach(m => { if (m.content && !skip.test(m.content)) urls.add(m.content); });

                    // All <img> tags — check src, srcset, data-src, data-lazy-src, data-original
                    document.querySelectorAll('img').forEach(img => {
                        const candidates = [
                            img.src, img.dataset.src, img.dataset.lazySrc,
                            img.dataset.original, img.getAttribute('data-src'),
                            img.getAttribute('data-lazy-src'), img.getAttribute('data-original')
                        ];
                        // Also extract first URL from srcset
                        const srcset = img.getAttribute('srcset');
                        if (srcset) {
                            const first = srcset.split(',')[0].trim().split(/\\s+/)[0];
                            candidates.push(first);
                        }
                        // Skip tiny images
                        if ((img.naturalWidth > 0 && img.naturalWidth < 80) ||
                            (img.naturalHeight > 0 && img.naturalHeight < 80)) return;

                        for (const c of candidates) {
                            if (c && c.startsWith('http') && !skip.test(c)) {
                                urls.add(c);
                                break;
                            }
                        }
                    });

                    // CSS background-image on hero/banner elements
                    document.querySelectorAll('[class*="hero"], [class*="banner"], [class*="bg"], section, .header')
                        .forEach(el => {
                            const bg = getComputedStyle(el).backgroundImage;
                            if (bg && bg !== 'none') {
                                const match = bg.match(/url\\(["']?(https?[^"')]+)["']?\\)/);
                                if (match && !skip.test(match[1])) urls.add(match[1]);
                            }
                        });

                    return [...urls].slice(0, 8);
                }""")

                # Extract text content
                text = await page.evaluate("""() => {
                    const remove = document.querySelectorAll('script, style, nav, footer, header');
                    remove.forEach(el => el.remove());
                    return document.body.innerText.substring(0, 5000);
                }""")

                await browser.close()

                if text and len(text.strip()) > 50:
                    return text[:5000], image_urls
                # If text is too short, fall through to httpx
                if image_urls:
                    return text[:5000] if text else None, image_urls

        except ImportError:
            logger.info("Playwright not available for page fetch, using httpx fallback")
        except Exception as e:
            logger.warning(f"Playwright fetch failed for {url}, falling back to httpx: {e}")

        # Fallback: plain HTTP
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
        tracking pixels, and data: URIs.

        Checks src, data-src, data-lazy-src, data-original, and srcset.
        Also looks for CSS background-image on hero/banner elements.
        """
        skip_hints = ("logo", "icon", "sprite", "pixel", "avatar", "badge", "spinner")
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
            if resolved not in seen:
                seen.add(resolved)
                urls.append(resolved)

        # Meta tags (highest quality hero images)
        for meta_name in ("og:image", "og:image:secure_url", "twitter:image"):
            tag = soup.find("meta", attrs={"property": meta_name}) or soup.find("meta", attrs={"name": meta_name})
            if tag and tag.get("content"):
                add(tag["content"])

        # <img> tags with multiple lazy-load attribute patterns
        for img in soup.find_all("img"):
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("data-original")
            )
            # Also check srcset — take the first (usually largest) URL
            if not src:
                srcset = img.get("srcset")
                if srcset:
                    first = srcset.split(",")[0].strip().split()[0]
                    src = first

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

        # CSS background-image on hero/banner elements
        import re
        bg_pattern = re.compile(r'url\(["\']?(https?://[^"\')\s]+)["\']?\)')
        for el in soup.find_all(attrs={"style": bg_pattern}):
            style = el.get("style", "")
            match = bg_pattern.search(style)
            if match:
                add(match.group(1))
            if len(urls) >= limit:
                break

        return urls[:limit]
