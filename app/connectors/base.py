"""Base connector interface."""

from abc import ABC, abstractmethod
from typing import Optional


class DiscoveryResult:
    """A single discovery result from any connector."""

    def __init__(
        self,
        company_name: str,
        website_url: str = "",
        industry: str = "",
        location: str = "",
        address: str = "",
        phone: str = "",
        email: str = "",
        description: str = "",
        source: str = "",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        google_photo_refs: Optional[list[str]] = None,
        google_photo_attribution: str = "",
    ):
        self.company_name = company_name
        self.website_url = website_url
        self.industry = industry
        self.location = location
        self.address = address
        self.phone = phone
        self.email = email
        self.description = description
        self.source = source
        self.latitude = latitude
        self.longitude = longitude
        # Google Places photo "name" references (e.g. "places/X/photos/Y") and a
        # display-name credit for the first photo's author — used as a fallback
        # real-photo source when the business's own website has none. Only
        # GoogleMapsConnector populates these.
        self.google_photo_refs = google_photo_refs or []
        self.google_photo_attribution = google_photo_attribution


class BaseConnector(ABC):
    """Abstract base for all discovery connectors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Connector name for logging."""
        ...

    @abstractmethod
    async def discover(
        self,
        location: str,
        categories: list[str],
        max_results: int = 10,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> list[DiscoveryResult]:
        """Discover businesses in a location."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this connector has required credentials."""
        ...
