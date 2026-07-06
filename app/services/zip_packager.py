"""Zip Packager - creates downloadable zip packages for leads."""

import logging
import zipfile
from pathlib import Path

from app.core.models import Lead
from app.storage.database import get_database

logger = logging.getLogger(__name__)


class ZipPackager:
    """Packages HTML and screenshots into a zip file."""

    def package(self, lead: Lead) -> Lead:
        """Create a zip package for the lead's output."""
        if not lead.html_path:
            lead.add_log("No HTML to package")
            return lead

        html_path = Path(lead.html_path)
        output_dir = html_path.parent
        zip_path = output_dir / f"{lead.company_name.replace(' ', '_')}_redesign.zip"

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Add HTML
                if html_path.exists():
                    zf.write(html_path, "index.html")

                # Add screenshots
                for ss_path_str in lead.screenshot_paths:
                    ss_path = Path(ss_path_str)
                    if ss_path.exists():
                        zf.write(ss_path, f"screenshots/{ss_path.name}")

            lead.zip_path = str(zip_path)
            lead.add_log(f"Zip package created: {zip_path.name}")

        except Exception as e:
            logger.error(f"Zip packaging failed: {e}")
            lead.add_log(f"Zip packaging failed: {str(e)}")

        db = get_database()
        db.save_lead(lead)
        return lead
