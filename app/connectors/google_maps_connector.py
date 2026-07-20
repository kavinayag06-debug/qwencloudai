"""Google Places API (New) connector for discovering businesses."""

import logging
import random
from typing import Optional

import httpx

from app.config import get_settings
from app.connectors.base import BaseConnector, DiscoveryResult

logger = logging.getLogger(__name__)


class GoogleMapsConnector(BaseConnector):
    """Discover businesses using Google Places API (New)."""

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
        lat = latitude if latitude is not None else 1.3521
        lng = longitude if longitude is not None else 103.8198

        # Vary the search radius between runs to get different results
        # Google returns different places at different radii
        radius = random.choice([2000.0, 3000.0, 5000.0, 7000.0, 10000.0])

        results = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for category in categories[:5]:
                try:
                    # Use Places API (New) - Nearby Search
                    url = "https://places.googleapis.com/v1/places:searchNearby"
                    headers = {
                        "Content-Type": "application/json",
                        "X-Goog-Api-Key": settings.google_maps_api_key,
                        "X-Goog-FieldMask": (
                            "places.displayName,"
                            "places.formattedAddress,"
                            "places.websiteUri,"
                            "places.nationalPhoneNumber,"
                            "places.location,"
                            "places.primaryType,"
                            "places.id"
                        ),
                    }
                    body = {
                        "includedTypes": [self._map_category_to_type(category)],
                        "maxResultCount": 10,
                        "locationRestriction": {
                            "circle": {
                                "center": {
                                    "latitude": lat,
                                    "longitude": lng,
                                },
                                "radius": radius,
                            }
                        },
                    }

                    response = await client.post(url, headers=headers, json=body)
                    response.raise_for_status()
                    data = response.json()

                    for place in data.get("places", []):
                        display_name = place.get("displayName", {}).get("text", "Unknown")
                        website = place.get("websiteUri", "")
                        address = place.get("formattedAddress", "")
                        phone = place.get("nationalPhoneNumber", "")
                        loc = place.get("location", {})
                        place_lat = loc.get("latitude")
                        place_lng = loc.get("longitude")

                        # Use Google's actual primaryType for accurate industry
                        # classification instead of blindly using our search category
                        primary_type = place.get("primaryType", "")
                        actual_industry = self._type_to_industry(primary_type, category)

                        results.append(DiscoveryResult(
                            company_name=display_name,
                            website_url=website,
                            industry=actual_industry,
                            location=self._extract_short_location(address, location),
                            address=address,
                            phone=phone,
                            source="google_maps",
                            latitude=place_lat,
                            longitude=place_lng,
                        ))

                    logger.info(f"Google Places: '{category}' returned {len(data.get('places', []))} results")

                except httpx.HTTPStatusError as e:
                    logger.error(f"Google Places API error for '{category}': {e.response.status_code} - {e.response.text[:200]}")
                    continue
                except Exception as e:
                    logger.error(f"Google Places discovery failed for '{category}': {e}")
                    continue

        logger.info(f"Google Places total: {len(results)} results across {len(categories[:5])} categories")
        return results[:max_results]

    @staticmethod
    def _map_category_to_type(category: str) -> str:
        """Map our category names to Google Places API types."""
        type_map = {
            "restaurant": "restaurant",
            "cafe": "cafe",
            "bakery": "bakery",
            "florist": "florist",
            "salon": "hair_salon",
            "gym": "gym",
            "clinic": "doctor",
            "spa": "spa",
            "retail": "store",
            "boutique": "clothing_store",
            "tuition": "school",
        }
        return type_map.get(category.lower(), category.lower())

    @staticmethod
    def _type_to_industry(primary_type: str, fallback_category: str) -> str:
        """Map Google's primaryType back to a human-readable industry label.

        This ensures that if we searched for 'salon' but Google returned a
        sports centre, we label it correctly as 'sports' not 'salon'.
        """
        type_industry_map = {
            "restaurant": "restaurant",
            "cafe": "cafe",
            "coffee_shop": "cafe",
            "bakery": "bakery",
            "florist": "florist",
            "hair_salon": "salon",
            "beauty_salon": "salon",
            "hair_care": "salon",
            "gym": "gym",
            "fitness_center": "gym",
            "sports_club": "sports",
            "sports_complex": "sports",
            "sports_activity_location": "sports",
            "stadium": "sports",
            "athletic_field": "sports",
            "doctor": "clinic",
            "dentist": "clinic",
            "hospital": "clinic",
            "health": "clinic",
            "pharmacy": "clinic",
            "spa": "spa",
            "store": "retail",
            "shopping_mall": "retail",
            "clothing_store": "fashion",
            "shoe_store": "fashion",
            "jewelry_store": "fashion",
            "school": "tuition",
            "primary_school": "tuition",
            "secondary_school": "tuition",
            "community_center": "sports",
            "meal_delivery": "restaurant",
            "meal_takeaway": "restaurant",
            "bar": "restaurant",
            "night_club": "entertainment",
            "movie_theater": "entertainment",
            "pet_store": "retail",
            "supermarket": "retail",
            "convenience_store": "retail",
        }
        if primary_type:
            industry = type_industry_map.get(primary_type.lower())
            if industry:
                return industry
        return fallback_category

    @staticmethod
    def _extract_short_location(address: str, fallback: str) -> str:
        """Extract a short neighborhood/area name from a full Google address.

        e.g. '1 Jurong West Central 3, #01-01, Singapore 648886'
             -> 'Jurong West, Singapore'
        """
        if not address:
            return fallback

        # Singapore addresses typically end with 'Singapore XXXXXX'
        # Try to extract the neighborhood from the address parts
        parts = [p.strip() for p in address.split(",")]

        # Look for a part that contains a recognizable area name (not just a number)
        # Skip the first part (usually street number + name) and the last (country + postal)
        if len(parts) >= 3:
            # Try the second-to-last part or a middle part that looks like a neighborhood
            for part in parts[1:-1]:
                # Skip parts that are just unit numbers like '#01-01'
                if part.startswith("#") or part.strip().isdigit():
                    continue
                # Skip Singapore postal codes
                if "Singapore" in part and any(c.isdigit() for c in part):
                    continue
                return f"{part}, Singapore"

        # If the address has 'Singapore' in it, try to grab area from first part
        if "Singapore" in address and len(parts) >= 2:
            first = parts[0]
            # Try to get a general area from the street name
            # Remove street numbers from the beginning
            words = first.split()
            area_words = [w for w in words if not w.isdigit() and not w.startswith("#")]
            if area_words:
                return f"{' '.join(area_words[:3])}, Singapore"

        return fallback
