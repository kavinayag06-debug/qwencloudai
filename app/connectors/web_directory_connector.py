"""Web directory / search connector for discovering businesses."""

import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import BaseConnector, DiscoveryResult

logger = logging.getLogger(__name__)


class WebDirectoryConnector(BaseConnector):
    """Discover businesses via web search / directory scraping."""

    @property
    def name(self) -> str:
        return "web_directory"

    def is_available(self) -> bool:
        # Always available as fallback (uses public web)
        return True

    async def discover(
        self,
        location: str,
        categories: list[str],
        max_results: int = 10,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> list[DiscoveryResult]:
        """
        Search web directories for local businesses.
        This is a fallback connector that works without API keys.
        """
        results = []

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        ) as client:
            for category in categories[:3]:
                try:
                    # Use DuckDuckGo HTML search as fallback
                    query = f"{category} {location} business website"
                    url = "https://html.duckduckgo.com/html/"
                    response = await client.post(url, data={"q": query})

                    if response.status_code != 200:
                        continue

                    soup = BeautifulSoup(response.text, "html.parser")
                    links = soup.select(".result__a")

                    for link in links[:3]:
                        href = link.get("href", "")
                        title = link.get_text(strip=True)
                        if href and title and "ad" not in href.lower():
                            results.append(DiscoveryResult(
                                company_name=title,
                                website_url=href,
                                industry=category,
                                location=location,
                                source="web_directory",
                            ))

                except Exception as e:
                    logger.error(f"Web directory search failed for {category}: {e}")
                    continue

        return results[:max_results]
