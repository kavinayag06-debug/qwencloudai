"""Google Places API (New) connector for discovering businesses."""

import logging
import random
from typing import Optional

import httpx

from app.config import get_settings
from app.connectors.base import BaseConnector, DiscoveryResult
from app.connectors.institution_filter import is_institution_place_type

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
                            "places.id,"
                            "places.photos"
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

                        # Check the authoritative place type BEFORE any category
                        # relabeling. Some categories we search for (e.g. "tuition")
                        # have no dedicated Google type and share a type with a
                        # non-commercial institution (e.g. "school") — reject those
                        # here, while the type is still Google's own classification,
                        # rather than after they've been relabeled into a
                        # plausible-looking commercial industry.
                        primary_type = place.get("primaryType", "")
                        if is_institution_place_type(primary_type):
                            logger.debug(
                                f"Filtered non-commercial institution ({primary_type}): {display_name}"
                            )
                            continue

                        # Use Google's actual primaryType for accurate industry
                        # classification instead of blindly using our search category.
                        # If Google classifies this place as something outside our
                        # hardcoded local-business industries (e.g. parking, bank,
                        # real estate agency), skip it rather than mislabeling it.
                        actual_industry = self._type_to_industry(primary_type, category)
                        if actual_industry is None:
                            logger.debug(
                                f"Skipping '{display_name}': primaryType "
                                f"'{primary_type}' is not a recognized local-business industry"
                            )
                            continue

                        # Real, business-specific photos (owner/visitor-submitted) to
                        # fall back on when the business's own website has none —
                        # never fabricated, just a second real source.
                        photos = place.get("photos", [])
                        photo_refs = [p["name"] for p in photos[:3] if p.get("name")]
                        photo_attribution = ""
                        if photos:
                            authors = photos[0].get("authorAttributions", [])
                            if authors:
                                photo_attribution = authors[0].get("displayName", "")

                        results.append(DiscoveryResult(
                            company_name=display_name,
                            website_url=website,
                            industry=actual_industry,
                            location=location,
                            address=address,
                            phone=phone,
                            source="google_maps",
                            latitude=place_lat,
                            longitude=place_lng,
                            google_photo_refs=photo_refs,
                            google_photo_attribution=photo_attribution,
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
    def _type_to_industry(primary_type: str, fallback_category: str) -> Optional[str]:
        """Map Google's primaryType back to a human-readable industry label.

        This ensures that if we searched for 'salon' but Google returned a
        sports centre, we label it correctly as 'sports' not 'salon'.

        Returns None when primary_type is present but not a recognized
        local-business industry (e.g. parking, bank, real_estate_agency) —
        the caller should skip that result rather than mislabel it via
        fallback_category.
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
            "health": "clinic",
            "pharmacy": "clinic",
            "spa": "spa",
            "store": "retail",
            "shopping_mall": "retail",
            "clothing_store": "fashion",
            "shoe_store": "fashion",
            "jewelry_store": "fashion",
            # Note: "school"/"primary_school"/"secondary_school"/"hospital"/
            # "community_center" are non-commercial institutions, rejected by
            # is_institution_place_type() above before this map is ever
            # consulted for them — intentionally absent here, not an oversight.
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
            return type_industry_map.get(primary_type.lower())
        return fallback_category
