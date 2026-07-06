"""Google Maps / Places connector for discovering businesses."""

import logging
from typing import Optional

import httpx

from app.config import get_settings
from app.connectors.base import BaseConnector, DiscoveryResult

logger = logging.getLogger(__name__)


class GoogleMapsConnector(BaseConnector):
    """Discover businesses using Google Places API."""

    @property
    def name(self) -> str:
        return "google_maps"

    def is_available(self) -> bool:
        settings = get_settings()
        return bool(settings.google_maps_api_key)

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
            logger.warning("Google Maps API key not configured, skipping")
            return []

        # Default coordinates for Singapore
        lat = latitude or 1.3521
        lng = longitude or 103.8198

        results = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for category in categories[:5]:
                try:
                    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
                    params = {
                        "location": f"{lat},{lng}",
                        "radius": 5000,
                        "keyword": category,
                        "key": settings.google_maps_api_key,
                    }
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()

                    for place in data.get("results", [])[:3]:
                        # Try to get website
                        place_id = place.get("place_id")
                        website = ""
                        if place_id:
                            detail_url = "https://maps.googleapis.com/maps/api/place/details/json"
                            detail_params = {
                                "place_id": place_id,
                                "fields": "website,formatted_phone_number",
                                "key": settings.google_maps_api_key,
                            }
                            detail_resp = await client.get(detail_url, params=detail_params)
                            if detail_resp.status_code == 200:
                                detail_data = detail_resp.json().get("result", {})
                                website = detail_data.get("website", "")

                        results.append(DiscoveryResult(
                            company_name=place.get("name", "Unknown"),
                            website_url=website,
                            industry=category,
                            location=location,
                            address=place.get("vicinity", ""),
                            source="google_maps",
                            latitude=place.get("geometry", {}).get("location", {}).get("lat"),
                            longitude=place.get("geometry", {}).get("location", {}).get("lng"),
                        ))

                except Exception as e:
                    logger.error(f"Google Maps discovery failed for {category}: {e}")
                    continue

        return results[:max_results]
