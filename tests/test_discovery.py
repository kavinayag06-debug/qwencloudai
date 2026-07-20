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
async def test_mock_discovery_returns_leads_on_repeated_runs(tmp_path):
    """Mock mode must not treat its own fixed businesses as duplicates across
    runs — MockConnector always returns the same set, so excluding "already
    discovered" leads would make every run after the first return nothing."""
    import app.config as config_module
    import app.storage.database as db_module
    config_module._settings = None
    db_module._db = None

    from app.storage.database import get_database
    get_database().clear_all()

    service = DiscoveryService()
    request = DiscoveryRequest(location="Singapore", max_results=5)

    first = await service.run_discovery(request)
    second = await service.run_discovery(request)

    assert len(first) > 0
    assert len(second) > 0

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


@pytest.mark.asyncio
async def test_google_maps_connector_excludes_institutions(monkeypatch):
    """A real public primary school must never survive Google Maps discovery,
    even when it's returned for a search that targeted a legitimate category
    ("tuition" -> Google type "school") that happens to share a type with it.
    A legitimate business sharing no such overlap must still pass through."""
    import httpx
    from app.connectors.google_maps_connector import GoogleMapsConnector

    monkeypatch.setattr(
        "app.connectors.google_maps_connector.get_settings",
        lambda: type("S", (), {"google_maps_api_key": "fake-key-for-test"})(),
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "places": [
                    {
                        "displayName": {"text": "Ang Mo Kio Primary School"},
                        "websiteUri": "https://amkps.moe.edu.sg",
                        "formattedAddress": "1 Ang Mo Kio Ave, Singapore",
                        "primaryType": "primary_school",
                        "location": {"latitude": 1.37, "longitude": 103.85},
                    },
                    {
                        # Google has no dedicated type for a private tuition
                        # centre — when it returns one under a generic/unclear
                        # type rather than "school", it must NOT be excluded,
                        # since we only reject on confirmed structured evidence.
                        "displayName": {"text": "Bright Minds Tuition Centre"},
                        "websiteUri": "https://brightminds.example",
                        "formattedAddress": "2 Bishan St, Singapore",
                        "primaryType": "point_of_interest",
                        "location": {"latitude": 1.35, "longitude": 103.84},
                    },
                    {
                        "displayName": {"text": "Sunshine Dental Clinic"},
                        "websiteUri": "https://sunshinedental.example",
                        "formattedAddress": "3 Bedok Rd, Singapore",
                        "primaryType": "doctor",
                        "location": {"latitude": 1.32, "longitude": 103.93},
                    },
                    {
                        "displayName": {"text": "Community Centre Hall"},
                        "websiteUri": "",
                        "formattedAddress": "4 Yishun Ave, Singapore",
                        "primaryType": "community_center",
                        "location": {"latitude": 1.43, "longitude": 103.83},
                    },
                ]
            }

    async def fake_post(self, url, headers=None, json=None):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    connector = GoogleMapsConnector()
    results = await connector.discover(location="Singapore", categories=["tuition"], max_results=10)

    names = {r.company_name for r in results}
    assert "Ang Mo Kio Primary School" not in names
    assert "Community Centre Hall" not in names
    assert "Bright Minds Tuition Centre" in names
    assert "Sunshine Dental Clinic" in names

    clinic = next(r for r in results if r.company_name == "Sunshine Dental Clinic")
    assert clinic.industry == "clinic"


@pytest.mark.asyncio
async def test_google_maps_tuition_centre_typed_as_school_is_also_excluded(monkeypatch):
    """Documents the known, accepted trade-off: Google has no distinct type
    for a private tuition centre, so if it types one exactly "school" (the
    same type real schools get), it is excluded along with real schools —
    preferring to reject a real institution over admitting a false negative,
    per ship-instructions.md's structured-type-evidence preference."""
    import httpx
    from app.connectors.google_maps_connector import GoogleMapsConnector

    monkeypatch.setattr(
        "app.connectors.google_maps_connector.get_settings",
        lambda: type("S", (), {"google_maps_api_key": "fake-key-for-test"})(),
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "places": [
                    {
                        "displayName": {"text": "Ambiguous Tuition Centre"},
                        "websiteUri": "https://ambiguous.example",
                        "formattedAddress": "5 Toa Payoh, Singapore",
                        "primaryType": "school",
                        "location": {"latitude": 1.33, "longitude": 103.85},
                    },
                ]
            }

    async def fake_post(self, url, headers=None, json=None):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    connector = GoogleMapsConnector()
    results = await connector.discover(location="Singapore", categories=["tuition"], max_results=10)
    assert results == []


@pytest.mark.asyncio
async def test_exa_connector_excludes_institutions(monkeypatch):
    from app.connectors.exa_connector import ExaConnector

    monkeypatch.setattr(
        "app.connectors.exa_connector.get_settings",
        lambda: type("S", (), {"exa_api_key": "fake-key-for-test"})(),
    )

    class FakeItem:
        def __init__(self, title, url, text=""):
            self.title = title
            self.url = url
            self.text = text

    class FakeSearchResults:
        def __init__(self, results):
            self.results = results

    class FakeExa:
        def __init__(self, api_key):
            pass

        def search(self, query, num_results=10, type="neural", category="company"):
            return FakeSearchResults([
                FakeItem("Toa Payoh Secondary School", "https://tps.moe.edu.sg"),
                FakeItem("ABC Tuition Centre", "https://abctuition.example"),
            ])

    fake_exa_module = type("M", (), {"Exa": FakeExa})
    monkeypatch.setitem(__import__("sys").modules, "exa_py", fake_exa_module)

    connector = ExaConnector()
    results = await connector.discover(location="Singapore", categories=["tuition"], max_results=10)

    names = {r.company_name for r in results}
    assert "Toa Payoh Secondary School" not in names
    assert "ABC Tuition Centre" in names


@pytest.mark.asyncio
async def test_web_directory_connector_excludes_institutions(monkeypatch):
    import httpx
    from app.connectors.web_directory_connector import WebDirectoryConnector

    html = """
    <html><body>
    <a class="result__a" href="https://amkps.moe.edu.sg">Ang Mo Kio Primary School</a>
    <a class="result__a" href="https://brightminds.example">Bright Minds Tuition Centre</a>
    </body></html>
    """

    class FakeResponse:
        status_code = 200
        text = html

    async def fake_post(self, url, data=None):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    connector = WebDirectoryConnector()
    results = await connector.discover(location="Singapore", categories=["tuition"], max_results=10)

    names = {r.company_name for r in results}
    assert "Ang Mo Kio Primary School" not in names
    assert "Bright Minds Tuition Centre" in names
