"""
Screenshot Renderer - renders screenshots from generated HTML using Playwright.

Uses Playwright to:
- Open the generated HTML file
- Capture full-page screenshots at different viewport sizes
- Save screenshots to the output folder
"""

import logging
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.core.models import Lead
from app.storage.database import get_database

logger = logging.getLogger(__name__)


class ScreenshotRenderer:
    """Renders screenshots from HTML files using Playwright."""

    VIEWPORTS = [
        {"name": "desktop", "width": 1440, "height": 900},
        {"name": "tablet", "width": 768, "height": 1024},
        {"name": "mobile", "width": 375, "height": 812},
    ]

    async def render(self, lead: Lead) -> Lead:
        """Render screenshots from the lead's HTML file."""
        if not lead.html_path:
            lead.add_log("No HTML file to render screenshots from")
            return lead

        html_path = Path(lead.html_path)
        if not html_path.exists():
            lead.add_log(f"HTML file not found: {html_path}")
            return lead

        lead.add_log("Starting screenshot rendering")
        screenshot_paths = []

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)

                for viewport in self.VIEWPORTS:
                    try:
                        page = await browser.new_page(
                            viewport={"width": viewport["width"], "height": viewport["height"]}
                        )

                        # Load local HTML file
                        file_url = html_path.resolve().as_uri()
                        await page.goto(file_url, wait_until="networkidle")

                        # Take screenshot
                        output_dir = html_path.parent
                        screenshot_path = output_dir / f"screenshot_{viewport['name']}.png"
                        await page.screenshot(
                            path=str(screenshot_path),
                            full_page=True,
                        )

                        screenshot_paths.append(str(screenshot_path))
                        lead.add_log(f"Screenshot saved: {viewport['name']} ({viewport['width']}x{viewport['height']})")

                        await page.close()

                    except Exception as e:
                        logger.error(f"Screenshot failed for {viewport['name']}: {e}")
                        lead.add_log(f"Screenshot failed for {viewport['name']}: {str(e)}")

                await browser.close()

        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            lead.add_log("Playwright not available - screenshots skipped")
        except Exception as e:
            logger.error(f"Screenshot rendering failed: {e}")
            lead.add_log(f"Screenshot rendering error: {str(e)}")

        lead.screenshot_paths = screenshot_paths
        db = get_database()
        db.save_lead(lead)
        return lead
