"""Data models for the application."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class LeadStatus(str, Enum):
    DISCOVERED = "discovered"
    ANALYZED = "analyzed"
    REDESIGN_GENERATED = "redesign_generated"
    EMAIL_DRAFTED = "email_drafted"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WebsiteAnalysis(BaseModel):
    """Analysis of a target website."""
    visual_age: str = ""
    modernity_score: int = Field(default=50, ge=0, le=100)
    responsiveness: str = ""
    responsiveness_score: int = Field(default=50, ge=0, le=100)
    content_clarity: str = ""
    content_clarity_score: int = Field(default=50, ge=0, le=100)
    cta_quality: str = ""
    cta_score: int = Field(default=50, ge=0, le=100)
    trust_signals: str = ""
    trust_score: int = Field(default=50, ge=0, le=100)
    layout_density: str = ""
    layout_score: int = Field(default=50, ge=0, le=100)
    mobile_friendliness: str = ""
    mobile_score: int = Field(default=50, ge=0, le=100)
    design_problems: list[str] = Field(default_factory=list)
    industry_fit: str = ""
    overall_weakness_score: int = Field(default=50, ge=0, le=100)
    summary: str = ""


class StyleTraits(BaseModel):
    """Extracted style signals from design references."""
    color_palette: list[str] = Field(default_factory=list)
    typography: str = ""
    layout_style: str = ""
    mood: str = ""
    industry_fit: list[str] = Field(default_factory=list)
    design_patterns: list[str] = Field(default_factory=list)
    quality_score: int = Field(default=70, ge=0, le=100)
    # Paths to the actual reference screenshots these traits were derived from.
    # Kept alongside the text summary so downstream steps (HTML build + critique)
    # can attach the real images to the model call instead of only a paraphrase.
    reference_image_paths: list[str] = Field(default_factory=list)


class ConfidenceScore(BaseModel):
    """Transparent confidence scoring."""
    website_weakness: int = Field(default=50, ge=0, le=100)
    style_fit: int = Field(default=50, ge=0, le=100)
    industry_match: int = Field(default=50, ge=0, le=100)
    opportunity_clarity: int = Field(default=50, ge=0, le=100)
    html_quality: int = Field(default=50, ge=0, le=100)
    outreach_confidence: int = Field(default=50, ge=0, le=100)
    overall: int = Field(default=50, ge=0, le=100)
    level: ConfidenceLevel = ConfidenceLevel.MEDIUM

    def compute_overall(self) -> None:
        """Compute overall score from components."""
        weights = {
            "website_weakness": 0.25,
            "style_fit": 0.15,
            "industry_match": 0.15,
            "opportunity_clarity": 0.20,
            "html_quality": 0.15,
            "outreach_confidence": 0.10,
        }
        self.overall = int(
            self.website_weakness * weights["website_weakness"]
            + self.style_fit * weights["style_fit"]
            + self.industry_match * weights["industry_match"]
            + self.opportunity_clarity * weights["opportunity_clarity"]
            + self.html_quality * weights["html_quality"]
            + self.outreach_confidence * weights["outreach_confidence"]
        )
        if self.overall >= 75:
            self.level = ConfidenceLevel.HIGH
        elif self.overall >= 50:
            self.level = ConfidenceLevel.MEDIUM
        else:
            self.level = ConfidenceLevel.LOW


class Lead(BaseModel):
    """A discovered business lead."""
    id: Optional[str] = None
    company_name: str = ""
    website_url: str = ""
    industry: str = ""
    location: str = ""
    address: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    phone: str = ""
    email: str = ""
    description: str = ""
    discovery_source: str = ""
    status: LeadStatus = LeadStatus.DISCOVERED
    website_analysis: Optional[WebsiteAnalysis] = None
    style_traits: Optional[StyleTraits] = None
    confidence: Optional[ConfidenceScore] = None
    html_path: Optional[str] = None
    html_quality_score: int = Field(default=0, ge=0, le=100)
    screenshot_paths: list[str] = Field(default_factory=list)
    # Real photo URLs scraped from the business's own current website (og:image,
    # largest content <img> tags). These are the only images the redesign should
    # ever use — they're actually of the business, unlike stock photography.
    source_image_urls: list[str] = Field(default_factory=list)
    # Google Places photo references (real, owner/visitor-submitted photos of
    # this specific business) — fallback real-photo source when the business's
    # own website has none. Only populated by GoogleMapsConnector.
    google_photo_refs: list[str] = Field(default_factory=list)
    google_photo_attribution: str = ""
    # Filenames (relative to the lead's output "images/" folder) that were
    # successfully downloaded and are safe to reference in the generated HTML.
    local_image_paths: list[str] = Field(default_factory=list)
    # filename -> required credit text, for images that came from Google Places
    # (Google's ToS requires attributing owner/visitor-submitted photos).
    image_attributions: dict[str, str] = Field(default_factory=dict)
    email_subject: str = ""
    email_body: str = ""
    zip_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    logs: list[str] = Field(default_factory=list)

    def add_log(self, message: str) -> None:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
        self.updated_at = datetime.utcnow()


class DiscoveryRequest(BaseModel):
    """Request to run discovery."""
    location: str = "Singapore"
    country: str = "SG"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    max_results: int = 5
    categories: list[str] = Field(default_factory=lambda: [
        "restaurant", "cafe", "bakery", "florist", "salon",
        "gym", "clinic", "retail", "spa", "tuition"
    ])


class EmailDraft(BaseModel):
    """Email draft for outreach."""
    lead_id: str
    to_address: str = ""
    subject: str = ""
    body: str = ""
    attachments: list[str] = Field(default_factory=list)
    status: str = "draft"  # draft, approved, rejected, sent
