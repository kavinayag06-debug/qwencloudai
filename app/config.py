"""Application configuration loaded from environment variables."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """All application settings. Change .env to switch providers/models."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    # LLM Provider
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://api.openai.com/v1", alias="LLM_BASE_URL")

    # Vision Provider
    vision_provider: str = Field(default="mock", alias="VISION_PROVIDER")
    vision_model: str = Field(default="gpt-4o", alias="VISION_MODEL")
    vision_api_key: str = Field(default="", alias="VISION_API_KEY")
    vision_base_url: str = Field(default="https://api.openai.com/v1", alias="VISION_BASE_URL")

    # Discovery
    exa_api_key: str = Field(default="", alias="EXA_API_KEY")
    google_maps_api_key: str = Field(default="", alias="GOOGLE_MAPS_API_KEY")
    mapbox_api_key: str = Field(default="", alias="MAPBOX_API_KEY")

    # Email
    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    email_from_name: str = Field(default="", alias="EMAIL_FROM_NAME")
    email_from_address: str = Field(default="", alias="EMAIL_FROM_ADDRESS")

    # App
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    database_url: str = Field(default="sqlite:///data/app.db", alias="DATABASE_URL")
    max_leads: int = Field(default=5, alias="MAX_LEADS")
    default_location: str = Field(default="Singapore", alias="DEFAULT_LOCATION")
    default_country: str = Field(default="SG", alias="DEFAULT_COUNTRY")

    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    @property
    def data_dir(self) -> Path:
        return BASE_DIR / "data"

    @property
    def design_screenshots_dir(self) -> Path:
        return self.data_dir / "design_screenshots"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "output"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def knowledge_dir(self) -> Path:
        return self.data_dir / "knowledge"

    def ensure_directories(self) -> None:
        """Create all required directories."""
        for d in [self.data_dir, self.design_screenshots_dir, self.output_dir,
                  self.cache_dir, self.knowledge_dir]:
            d.mkdir(parents=True, exist_ok=True)


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get cached settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings
