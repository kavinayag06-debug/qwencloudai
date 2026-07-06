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
