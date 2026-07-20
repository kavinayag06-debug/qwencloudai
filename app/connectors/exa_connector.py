"""Exa search connector for discovering businesses."""

import logging
from typing import Optional

from app.config import get_settings
from app.connectors.base import BaseConnector, DiscoveryResult
from app.connectors.institution_filter import is_institution_name_or_domain

logger = logging.getLogger(__name__)


class ExaConnector(BaseConnector):
    """Discover businesses using Exa search API."""

    @property
    def name(self) -> str:
        return "exa"

    def is_available(self) -> bool:
        settings = get_settings()
        return bool(settings.exa_api_key)

    async def discover(
        self,
        location: str,
        categories: list[str],
        max_results: int = 10,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> list[DiscoveryResult]:
        settings = get_settings()
        if not self.is_available():
            logger.warning("Exa API key not configured, skipping")
            return []

        try:
            from exa_py import Exa

            exa = Exa(api_key=settings.exa_api_key)
            results = []

            for category in categories[:5]:  # Limit categories per run
                query = f"{category} business in {location} website"
                logger.info(f"Exa search: {query}")

                search_results = exa.search(
                    query,
                    num_results=max_results // len(categories[:5]),
                    type="neural",
                    category="company",
                )

                for item in search_results.results:
                    name = item.title or "Unknown"
                    url = item.url or ""
                    if is_institution_name_or_domain(name, url):
                        logger.debug(f"Filtered likely non-commercial institution: {name}")
                        continue
                    results.append(DiscoveryResult(
                        company_name=name,
                        website_url=url,
                        industry=category,
                        location=location,
                        description=getattr(item, "text", "")[:500],
                        source="exa",
                    ))

            return results[:max_results]

        except Exception as e:
            logger.error(f"Exa discovery failed: {e}")
            return []
