"""
Discovery Service - orchestrates business discovery across multiple connectors.

Pipeline:
1. Determine location scope
2. Query all available connectors
3. Filter for brick-and-mortar with weak websites
4. EXCLUDE previously discovered businesses (always find new ones)
5. Rank by redesign opportunity and proximity
6. Return top N NEW candidates
"""

import logging
import random
from typing import Optional

from app.config import get_settings
from app.connectors.base import BaseConnector, DiscoveryResult
from app.connectors.mock_connector import MockConnector
from app.connectors.exa_connector import ExaConnector
from app.connectors.google_maps_connector import GoogleMapsConnector
from app.connectors.web_directory_connector import WebDirectoryConnector
from app.core.models import Lead, LeadStatus, DiscoveryRequest
from app.storage.database import get_database

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Orchestrates business discovery from multiple sources."""

    def __init__(self):
        self.connectors: list[BaseConnector] = self._init_connectors()

    def _init_connectors(self) -> list[BaseConnector]:
        """Initialize all available connectors."""
        settings = get_settings()
        connectors: list[BaseConnector] = []

        # Add connectors in priority order
        if settings.llm_provider == "mock":
            connectors.append(MockConnector())
        else:
            google = GoogleMapsConnector()
            if google.is_available():
                connectors.append(google)

            exa = ExaConnector()
            if exa.is_available():
                connectors.append(exa)

            web = WebDirectoryConnector()
            if web.is_available():
                connectors.append(web)

            if not connectors:
                connectors.append(MockConnector())

        return connectors

    async def run_discovery(self, request: DiscoveryRequest) -> list[Lead]:
        """
        Run the full discovery pipeline.

        ALWAYS returns NEW businesses that haven't been discovered before.
        Excludes any company already in the database.
        """
        logger.info(f"Starting discovery for {request.location}, max={request.max_results}")

        # Get names of all previously discovered leads to exclude them. Skip this in
        # mock mode: MockConnector always returns the same fixed businesses, so
        # excluding "already discovered" ones would make every run after the first
        # return zero leads — a dev/test dead end, not a real duplicate.
        db = get_database()
        use_mock = any(isinstance(c, MockConnector) for c in self.connectors)
        existing_names: set[str] = set()
        existing_urls: set[str] = set()
        if use_mock:
            logger.info("Mock mode: skipping dedup against previously discovered businesses")
        else:
            existing_leads = db.get_all_leads()
            existing_names = {el.company_name.lower().strip() for el in existing_leads}
            existing_urls = {el.website_url.lower().strip() for el in existing_leads if el.website_url}
            logger.info(f"Excluding {len(existing_names)} previously discovered businesses")

        # Randomize category order each run to get different results
        categories = list(request.categories)
        random.shuffle(categories)

        all_results: list[DiscoveryResult] = []

        # Query all available connectors
        for connector in self.connectors:
            try:
                logger.info(f"Querying connector: {connector.name}")
                results = await connector.discover(
                    location=request.location,
                    categories=categories,
                    max_results=request.max_results * 4,  # Fetch more to have room after filtering
                    latitude=request.latitude,
                    longitude=request.longitude,
                )
                all_results.extend(results)
                logger.info(f"{connector.name} returned {len(results)} results")
            except Exception as e:
                logger.error(f"Connector {connector.name} failed: {e}")
                continue

        if not all_results:
            logger.warning("No results from any connector")
            return []

        # Deduplicate by company name within this batch
        seen_names = set()
        unique_results = []
        for r in all_results:
            name_key = r.company_name.lower().strip()
            if name_key not in seen_names:
                seen_names.add(name_key)
                unique_results.append(r)

        # EXCLUDE previously discovered businesses
        new_results = []
        for r in unique_results:
            name_key = r.company_name.lower().strip()
            url_key = r.website_url.lower().strip() if r.website_url else ""
            if name_key in existing_names:
                continue
            if url_key and url_key in existing_urls:
                continue
            new_results.append(r)

        logger.info(f"After excluding existing: {len(new_results)} new businesses (from {len(unique_results)} unique)")

        # Filter out chain stores / multi-location brands
        # We want single-location brick-and-mortar businesses, not franchises
        independent_results = self._filter_chains(new_results, all_results)
        logger.info(f"After chain filter: {len(independent_results)} independent businesses")

        # Filter: must have a website URL
        with_website = [r for r in independent_results if r.website_url]

        if not with_website:
            logger.warning("No new businesses with websites found. Try different categories.")
            # Fall back to all new results even without websites
            candidates = new_results
        else:
            candidates = with_website

        # Shuffle to add variety between runs with same params
        random.shuffle(candidates)

        # Rank: prioritize by proximity if coordinates available
        if request.latitude is not None and request.longitude is not None:
            candidates = self._sort_by_proximity(
                candidates, request.latitude, request.longitude
            )

        # Save NEW leads only
        leads = []
        for result in candidates[:request.max_results]:
            lead = Lead(
                company_name=result.company_name,
                website_url=result.website_url,
                industry=result.industry,
                location=result.location,
                address=result.address,
                latitude=result.latitude,
                longitude=result.longitude,
                phone=result.phone,
                email=result.email,
                description=result.description,
                discovery_source=result.source,
                status=LeadStatus.DISCOVERED,
                google_photo_refs=result.google_photo_refs,
                google_photo_attribution=result.google_photo_attribution,
            )
            lead.add_log(f"Discovered via {result.source} in {request.location}")
            lead = db.save_lead(lead)
            leads.append(lead)

        logger.info(f"Discovery complete: {len(leads)} NEW leads saved")
        return leads

    def _sort_by_proximity(
        self, results: list[DiscoveryResult], lat: float, lng: float
    ) -> list[DiscoveryResult]:
        """Sort results by distance from given coordinates."""
        import math

        def distance(r: DiscoveryResult) -> float:
            if r.latitude is None or r.longitude is None:
                return float("inf")
            dlat = r.latitude - lat
            dlng = r.longitude - lng
            return math.sqrt(dlat**2 + dlng**2)

        return sorted(results, key=distance)

    # Well-known chain store brands to filter out
    KNOWN_CHAINS = {
        "starbucks", "mcdonald", "mcdonalds", "burger king", "subway", "kfc",
        "pizza hut", "dominos", "domino's", "dunkin", "dunkin'", "tim hortons",
        "safra", "ntuc", "fairprice", "cold storage", "guardian", "watsons",
        "7-eleven", "cheers", "popular", "courts", "harvey norman",
        "breadtalk", "toast box", "ya kun", "old chang kee", "mr bean",
        "the coffee bean", "coffee bean", "gong cha", "koi", "liho",
        "paris baguette", "tous les jours", "four leaves",
        "jean yip", "ec house", "action cut", "qb house",
        "gold's gym", "anytime fitness", "fitness first", "virgin active",
        "guardian pharmacy", "unity pharmacy", "caring pharmacy",
        "miniso", "daiso", "don don donki", "donki",
        "uniqlo", "h&m", "zara", "cotton on", "charles & keith",
        "sephora", "innisfree", "the face shop",
        "comfort delgro", "grab",
    }

    def _filter_chains(
        self, results: list[DiscoveryResult], all_results: list[DiscoveryResult]
    ) -> list[DiscoveryResult]:
        """Filter out chain stores and multi-location businesses.

        Signals used:
        1. Name matches a known chain brand
        2. Name appears at multiple different addresses in the full result set
           (indicates a franchise with multiple outlets)
        3. Name contains branch indicators like '@', '#', 'outlet', 'branch'
           combined with a base name that appears multiple times
        """
        # Count how many distinct addresses each base name has
        from collections import Counter
        name_addresses: dict[str, set] = {}
        for r in all_results:
            base = self._extract_base_name(r.company_name)
            if base not in name_addresses:
                name_addresses[base] = set()
            if r.address:
                name_addresses[base].add(r.address.lower().strip())

        filtered = []
        for r in results:
            name_lower = r.company_name.lower().strip()
            base = self._extract_base_name(r.company_name)

            # Check against known chains
            if any(chain in name_lower for chain in self.KNOWN_CHAINS):
                logger.debug(f"Filtered chain (known brand): {r.company_name}")
                continue

            # Check if this base name appears at 3+ different addresses (chain store)
            if base in name_addresses and len(name_addresses[base]) > 2:
                logger.debug(f"Filtered chain (3+ locations): {r.company_name}")
                continue

            filtered.append(r)

        return filtered

    @staticmethod
    def _extract_base_name(name: str) -> str:
        """Extract the base business name, stripping branch/location suffixes.

        'Bake House @ Jurong' -> 'bake house'
        'FairPrice #123' -> 'fairprice'
        'Starbucks (Orchard)' -> 'starbucks'
        """
        import re
        name = name.lower().strip()
        # Remove everything after @ (branch indicator)
        name = re.split(r'\s*[@#]\s*', name)[0]
        # Remove parenthetical location info
        name = re.sub(r'\s*\(.*?\)\s*', '', name)
        # Remove common suffixes
        for suffix in (" outlet", " branch", " store", " pte ltd", " pte. ltd.", " ptd ltd"):
            name = name.replace(suffix, "")
        return name.strip()
