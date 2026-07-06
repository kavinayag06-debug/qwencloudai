"""
Agent Pipeline - orchestrates the full redesign workflow.

Steps:
1. Analyze design references
2. Run discovery
3. Analyze each target site
4. Generate HTML redesign
5. Render screenshots
6. Package zip
7. Draft emails
8. Queue for approval
"""

import logging
from typing import Optional

from app.config import get_settings
from app.core.models import Lead, DiscoveryRequest, LeadStatus
from app.services.design_analyzer import DesignAnalyzer
from app.services.discovery_service import DiscoveryService
from app.services.site_analyzer import SiteAnalyzer
from app.services.html_generator import HTMLGenerator
from app.services.screenshot_renderer import ScreenshotRenderer
from app.services.zip_packager import ZipPackager
from app.services.email_service import EmailService
from app.storage.database import get_database

logger = logging.getLogger(__name__)


class AgentPipeline:
    """Orchestrates the full redesign agent workflow."""

    def __init__(self):
        self.design_analyzer = DesignAnalyzer()
        self.discovery_service = DiscoveryService()
        self.site_analyzer = SiteAnalyzer()
        self.html_generator = HTMLGenerator()
        self.screenshot_renderer = ScreenshotRenderer()
        self.zip_packager = ZipPackager()
        self.email_service = EmailService()

    async def run_full_pipeline(self, request: Optional[DiscoveryRequest] = None) -> list[Lead]:
        """
        Run the complete agent pipeline end-to-end.

        Returns the list of processed leads.
        """
        settings = get_settings()

        if request is None:
            request = DiscoveryRequest(
                location=settings.default_location,
                country=settings.default_country,
                max_results=settings.max_leads,
            )

        logger.info(f"=== Starting full pipeline for {request.location} ===")

        # Step 1: Analyze design references
        logger.info("Step 1: Analyzing design references...")
        style_traits = await self.design_analyzer.analyze_references()
        logger.info(f"Style traits: {style_traits.mood}, {len(style_traits.color_palette)} colors")

        # Step 2: Run discovery
        logger.info("Step 2: Running discovery...")
        leads = await self.discovery_service.run_discovery(request)
        logger.info(f"Discovered {len(leads)} leads")

        if not leads:
            logger.warning("No leads discovered. Pipeline complete.")
            return []

        # Step 3-7: Process each lead
        processed_leads = []
        for i, lead in enumerate(leads):
            logger.info(f"Processing lead {i+1}/{len(leads)}: {lead.company_name}")
            lead = await self._process_lead(lead, style_traits)
            processed_leads.append(lead)

        logger.info(f"=== Pipeline complete: {len(processed_leads)} leads processed ===")
        return processed_leads

    async def _process_lead(self, lead: Lead, style_traits) -> Lead:
        """Process a single lead through the full pipeline."""
        try:
            # Attach style traits
            lead.style_traits = style_traits

            # Step 3: Analyze website
            lead = await self.site_analyzer.analyze(lead)

            # Step 4: Generate HTML
            lead = await self.html_generator.generate(lead, style_traits)

            # Step 5: Render screenshots
            lead = await self.screenshot_renderer.render(lead)

            # Step 6: Package zip
            lead = self.zip_packager.package(lead)

            # Step 7: Draft email
            lead = await self.email_service.draft_email(lead)

            logger.info(f"Lead {lead.company_name} fully processed. Status: {lead.status.value}")

        except Exception as e:
            logger.error(f"Pipeline failed for {lead.company_name}: {e}")
            lead.add_log(f"Pipeline error: {str(e)}")
            db = get_database()
            db.save_lead(lead)

        return lead

    async def run_discovery_only(self, request: Optional[DiscoveryRequest] = None) -> list[Lead]:
        """Run only the discovery step."""
        settings = get_settings()
        if request is None:
            request = DiscoveryRequest(
                location=settings.default_location,
                country=settings.default_country,
                max_results=settings.max_leads,
            )
        return await self.discovery_service.run_discovery(request)

    async def process_single_lead(self, lead_id: str) -> Optional[Lead]:
        """Process a single lead through analysis, generation, and email drafting."""
        db = get_database()
        lead = db.get_lead(lead_id)
        if not lead:
            return None

        style_traits = await self.design_analyzer.analyze_references()
        return await self._process_lead(lead, style_traits)
