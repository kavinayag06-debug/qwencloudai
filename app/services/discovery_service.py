"""
Discovery Service - orchestrates business discovery across multiple connectors.

Pipeline:
1. Determine location scope
2. Query all available connectors
3. Filter for brick-and-mortar with weak websites
4. Rank by redesign opportunity and proximity
5. Return top N candidates
"""

import logging
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
            # In mock mode, use mock connector
            connectors.append(MockConnector())
        else:
            # Real connectors
            google = GoogleMapsConnector()
            if google.is_available():
                connectors.append(google)

            exa = ExaConnector()
            if exa.is_available():
                connectors.append(exa)

            web = WebDirectoryConnector()
            if web.is_available():
                connectors.append(web)

            # Always keep mock as ultimate fallback
            if not connectors:
                connectors.append(MockConnector())

        return connectors

    async def run_discovery(self, request: DiscoveryRequest) -> list[Lead]:
        """
        Run the full discovery pipeline.

        Returns top N leads ranked by opportunity.
        """
        logger.info(f"Starting discovery for {request.location}, max={request.max_results}")

        all_results: list[DiscoveryResult] = []

        # Query all available connectors
        for connector in self.connectors:
            try:
                logger.info(f"Querying connector: {connector.name}")
                results = await connector.discover(
                    location=request.location,
                    categories=request.categories,
                    max_results=request.max_results * 2,
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

        # Deduplicate by company name
        seen_names = set()
        unique_results = []
        for r in all_results:
            name_key = r.company_name.lower().strip()
            if name_key not in seen_names:
                seen_names.add(name_key)
                unique_results.append(r)

        # Filter: must have a website URL (otherwise can't analyze)
        with_website = [r for r in unique_results if r.website_url]

        # If not enough results, expand scope message
        if len(with_website) < request.max_results:
            logger.info(
                f"Only {len(with_website)} results with websites. "
                f"Including all {len(unique_results)} results."
            )
            candidates = unique_results
        else:
            candidates = with_website

        # Rank: prioritize by proximity if coordinates available
        if request.latitude and request.longitude:
            candidates = self._sort_by_proximity(
                candidates, request.latitude, request.longitude
            )

        # Convert to Leads and save
        leads = []
        db = get_database()
        for result in candidates[:request.max_results]:
            # Check if lead already exists by website URL or company name
            existing_leads = db.get_all_leads()
            already_exists = any(
                (el.website_url == result.website_url and result.website_url)
                or el.company_name.lower() == result.company_name.lower()
                for el in existing_leads
            )
            if already_exists:
                # Find and reuse existing lead
                existing = next(
                    (el for el in existing_leads
                     if (el.website_url == result.website_url and result.website_url)
                     or el.company_name.lower() == result.company_name.lower()),
                    None,
                )
                if existing:
                    existing.add_log(f"Re-discovered via {result.source}")
                    db.save_lead(existing)
                    leads.append(existing)
                continue

            lead = Lead(
                company_name=result.company_name,
                website_url=result.website_url,
                industry=result.industry,
                location=result.location,
                address=result.address,
                phone=result.phone,
                email=result.email,
                description=result.description,
                discovery_source=result.source,
                status=LeadStatus.DISCOVERED,
            )
            lead.add_log(f"Discovered via {result.source} in {request.location}")
            lead = db.save_lead(lead)
            leads.append(lead)

        logger.info(f"Discovery complete: {len(leads)} leads saved")
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
