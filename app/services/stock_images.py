"""Stock image service — provides industry-mapped fallback images.

When client website images can't be downloaded, this service provides
pre-mapped stock images from Unsplash. Each image is used at most once
per lead to avoid repetition.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_IMAGE_MAP: Optional[dict] = None


def _load_image_map() -> dict:
    """Load the stock image mapping from JSON."""
    global _IMAGE_MAP
    if _IMAGE_MAP is not None:
        return _IMAGE_MAP

    settings = get_settings()
    map_path = settings.base_dir / "data" / "stock_images" / "image_map.json"
    if not map_path.exists():
        logger.warning(f"Stock image map not found at {map_path}")
        _IMAGE_MAP = {}
        return _IMAGE_MAP

    with open(map_path, "r", encoding="utf-8") as f:
        _IMAGE_MAP = json.load(f)
    return _IMAGE_MAP


async def get_stock_images_for_industry(industry: str, lead_dir: Path, max_images: int = 3) -> list[str]:
    """Download stock images for the given industry into the lead's images folder.

    Returns a list of local filenames (relative to lead_dir) that were saved.
    Each image is only used once — subsequent calls with same lead_dir skip
    already-downloaded files.
    """
    image_map = _load_image_map()
    industry_key = industry.lower().strip()

    # Get industry-specific images, fall back to default
    entries = image_map.get(industry_key, image_map.get("_default", []))
    if not entries:
        return []

    images_dir = lead_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    ) as client:
        for entry in entries[:max_images]:
            filename = entry["filename"]
            filepath = images_dir / filename

            # Skip if already downloaded
            if filepath.exists() and filepath.stat().st_size > 1000:
                saved.append(filename)
                continue

            try:
                url = entry["url"]
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) > 5000:
                    filepath.write_bytes(resp.content)
                    saved.append(filename)
                    logger.info(f"Downloaded stock image: {filename}")
                else:
                    logger.warning(f"Stock image download failed for {filename}: status={resp.status_code}")
            except Exception as e:
                logger.warning(f"Stock image download error for {filename}: {e}")
                continue

    return saved


def get_stock_image_alt_texts(industry: str) -> dict[str, str]:
    """Get a mapping of filename -> alt text for stock images."""
    image_map = _load_image_map()
    industry_key = industry.lower().strip()
    entries = image_map.get(industry_key, image_map.get("_default", []))
    return {entry["filename"]: entry["alt"] for entry in entries}
