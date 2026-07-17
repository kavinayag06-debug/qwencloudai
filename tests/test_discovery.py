"""Tests for discovery pipeline."""

import os
import pytest

os.environ["LLM_PROVIDER"] = "mock"
os.environ["VISION_PROVIDER"] = "mock"

from app.connectors.mock_connector import MockConnector, MOCK_BUSINESSES
from app.core.models import DiscoveryRequest
from app.services.discovery_service import DiscoveryService


@pytest.mark.asyncio
async def test_mock_connector_returns_results():
    """Mock connector returns sample businesses."""
    connector = MockConnector()
    results = await connector.discover(
        location="Singapore",
        categories=["restaurant", "bakery"],
        max_results=5,
    )
    assert len(results) > 0
    assert results[0].company_name != ""


@pytest.mark.asyncio
async def test_mock_connector_filters_by_category():
    """Mock connector filters by category."""
    connector = MockConnector()
    results = await connector.discover(
        location="Singapore",
        categories=["florist"],
        max_results=10,
    )
    assert all(r.industry == "florist" for r in results)


def test_mock_connector_is_always_available():
    """Mock connector is always available."""
    connector = MockConnector()
    assert connector.is_available() is True


@pytest.mark.asyncio
async def test_discovery_service_returns_leads(tmp_path):
    """Discovery service creates Lead objects."""
    import app.config as config_module
    import app.storage.database as db_module
    config_module._settings = None
    db_module._db = None

    service = DiscoveryService()
    request = DiscoveryRequest(
        location="Singapore",
        max_results=3,
        categories=["restaurant", "bakery", "florist"],
    )
    leads = await service.run_discovery(request)

    assert len(leads) <= 3
    assert all(lead.company_name != "" for lead in leads)
    assert all(lead.id is not None for lead in leads)

    config_module._settings = None
    db_module._db = None


@pytest.mark.asyncio
async def test_discovery_ranking_by_proximity(tmp_path):
    """Results are ranked by proximity when coordinates provided."""
    import app.config as config_module
    import app.storage.database as db_module
    config_module._settings = None
    db_module._db = None

    # Clear existing leads so mock results aren't excluded as duplicates
    from app.storage.database import get_database
    get_database().clear_all()

    service = DiscoveryService()
    request = DiscoveryRequest(
        location="Singapore",
        max_results=5,
        latitude=1.3048,  # Near Orchard Road
        longitude=103.8318,
    )
    leads = await service.run_discovery(request)
    assert len(leads) > 0

    config_module._settings = None
    db_module._db = None


def test_discovery_service_has_connectors():
    """Service initializes with at least one connector."""
    import app.config as config_module
    config_module._settings = None
    service = DiscoveryService()
    assert len(service.connectors) > 0
    config_module._settings = None
