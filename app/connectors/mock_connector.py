"""Mock connector for testing without external API keys."""

import logging
from typing import Optional

from app.connectors.base import BaseConnector, DiscoveryResult

logger = logging.getLogger(__name__)

MOCK_BUSINESSES = [
    DiscoveryResult(
        company_name="Blossom Floristry",
        website_url="https://example.com/blossom-floristry",
        industry="florist",
        location="Singapore",
        address="123 Orchard Road, Singapore 238858",
        phone="+65 6123 4567",
        description="Local flower shop with outdated website, basic HTML layout from 2010s",
        source="mock",
        latitude=1.3048,
        longitude=103.8318,
    ),
    DiscoveryResult(
        company_name="Uncle Tan's Kopitiam",
        website_url="https://example.com/uncle-tans",
        industry="restaurant",
        location="Singapore",
        address="45 Tanjong Pagar Road, Singapore 088464",
        phone="+65 6234 5678",
        description="Traditional kopitiam with no mobile-friendly site, cluttered layout",
        source="mock",
        latitude=1.2767,
        longitude=103.8455,
    ),
    DiscoveryResult(
        company_name="Serenity Spa & Wellness",
        website_url="https://example.com/serenity-spa",
        industry="spa",
        location="Singapore",
        address="78 Holland Road, Singapore 278992",
        phone="+65 6345 6789",
        description="Spa with flash-era website design, no clear CTAs",
        source="mock",
        latitude=1.3113,
        longitude=103.7952,
    ),
    DiscoveryResult(
        company_name="FitZone Gym",
        website_url="https://example.com/fitzone",
        industry="gym",
        location="Singapore",
        address="12 Bukit Timah Road, Singapore 229616",
        phone="+65 6456 7890",
        description="Local gym with slow loading, text-heavy website",
        source="mock",
        latitude=1.3290,
        longitude=103.8354,
    ),
    DiscoveryResult(
        company_name="Dr. Lee's Family Clinic",
        website_url="https://example.com/dr-lee-clinic",
        industry="clinic",
        location="Singapore",
        address="56 Clementi Ave 3, Singapore 129902",
        phone="+65 6567 8901",
        description="Family clinic with basic Wix site, poor trust signals",
        source="mock",
        latitude=1.3152,
        longitude=103.7649,
    ),
    DiscoveryResult(
        company_name="The Bake House",
        website_url="https://example.com/bake-house",
        industry="bakery",
        location="Singapore",
        address="89 Joo Chiat Road, Singapore 427387",
        phone="+65 6678 9012",
        description="Artisan bakery with Facebook-only presence, no proper website",
        source="mock",
        latitude=1.3140,
        longitude=103.9010,
    ),
    DiscoveryResult(
        company_name="Glamour Cuts Salon",
        website_url="https://example.com/glamour-cuts",
        industry="salon",
        location="Singapore",
        address="34 Upper Thomson Road, Singapore 574349",
        phone="+65 6789 0123",
        description="Hair salon with generic template site, no portfolio",
        source="mock",
        latitude=1.3577,
        longitude=103.8283,
    ),
]


class MockConnector(BaseConnector):
    """Mock connector returning sample data for testing."""

    @property
    def name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    async def discover(
        self,
        location: str,
        categories: list[str],
        max_results: int = 10,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> list[DiscoveryResult]:
        logger.info(f"MockConnector: returning {min(max_results, len(MOCK_BUSINESSES))} results")
        # Filter by category if possible
        filtered = [b for b in MOCK_BUSINESSES if b.industry in categories]
        if not filtered:
            filtered = MOCK_BUSINESSES
        return filtered[:max_results]
