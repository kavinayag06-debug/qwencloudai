"""
Reference Scraper — auto-populates design_screenshots/<industry>/ from
template marketplaces when no references exist for a given industry.

Called automatically by DesignAnalyzer.analyze_for_industry() when it
detects missing or stale references. NOT a manual script.

Searches Themeforest, Framer, and Webflow for the industry keyword,
screenshots the top template preview pages, and saves them locally.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# Cache metadata file
CACHE_FILENAME = ".reference_cache.json"

# How old references can be before re-scraping (days)
MAX_AGE_DAYS = 14

# Max preview pages to screenshot per marketplace
MAX_PREVIEWS_PER_SITE = 3

# Marketplace configs
MARKETPLACES = {
    "themeforest": {
        "search_url": "https://themeforest.net/search/{query}",
        "query_transform": lambda industry: f"{industry} website template",
        "preview_selector": "a[href*='/item/']",
    },
    "framer": {
        "search_url": "https://framer.com/marketplace/templates?query={query}",
        "query_transform": lambda industry: industry,
        "preview_selector": "a[href*='/templates/']",
    },
    "webflow": {
        "search_url": "https://webflow.com/templates/search?query={query}",
        "query_transform": lambda industry: industry,
        "preview_selector": "a[href*='/templates/']",
    },
}


def _cache_path() -> Path:
    settings = get_settings()
    return settings.design_screenshots_dir / CACHE_FILENAME


def _load_cache() -> dict:
    path = _cache_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict):
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2))


def is_fresh(industry: str) -> bool:
    """Check if references for this industry are fresh enough to skip scraping."""
    cache = _load_cache()
    entry = cache.get(industry.lower().strip())
    if not entry:
        return False
    timestamp = entry.get("timestamp", 0)
    count = entry.get("count", 0)
    age_days = (time.time() - timestamp) / 86400
    # Fresh if less than MAX_AGE_DAYS old AND we actually got some screenshots
    return age_days < MAX_AGE_DAYS and count > 0


async def scrape_references_for_industry(industry: str) -> list[Path]:
    """Scrape template marketplaces for an industry and save screenshots.

    Returns list of saved screenshot paths.
    Skips if references are already fresh (< MAX_AGE_DAYS old).
    Handles all failures gracefully — never raises, just logs and returns [].
    """
    industry_key = industry.lower().strip()

    if is_fresh(industry_key):
        logger.info(f"References for '{industry_key}' are fresh, skipping scrape")
        return _get_existing_screenshots(industry_key)

    logger.info(f"Auto-scraping reference screenshots for '{industry_key}' from template marketplaces...")

    settings = get_settings()
    output_dir = settings.design_screenshots_dir / industry_key
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed — cannot auto-scrape references")
        return []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            for marketplace_name, config in MARKETPLACES.items():
                try:
                    paths = await _scrape_marketplace(
                        page, industry_key, marketplace_name, config, output_dir
                    )
                    saved_paths.extend(paths)
                except Exception as e:
                    logger.warning(f"[{marketplace_name}] Failed for '{industry_key}': {e}")
                    continue

            await browser.close()

    except Exception as e:
        logger.error(f"Reference scraping completely failed for '{industry_key}': {e}")

    # Update cache
    cache = _load_cache()
    cache[industry_key] = {
        "timestamp": time.time(),
        "count": len(saved_paths),
    }
    _save_cache(cache)

    logger.info(f"Reference scraping for '{industry_key}': saved {len(saved_paths)} screenshots")
    return saved_paths


async def _scrape_marketplace(
    page, industry: str, marketplace_name: str, config: dict, output_dir: Path
) -> list[Path]:
    """Search one marketplace and screenshot top template previews."""
    query = config["query_transform"](industry)
    search_url = config["search_url"].format(query=query.replace(" ", "+"))
    saved: list[Path] = []

    logger.info(f"  [{marketplace_name}] Searching: {search_url}")

    await page.goto(search_url, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(2000)

    # Verify page loaded something meaningful
    content = await page.content()
    if len(content) < 3000:
        logger.warning(f"  [{marketplace_name}] Page seems empty or blocked")
        return saved

    # Screenshot the search grid
    grid_path = output_dir / f"{marketplace_name}_grid.png"
    await page.screenshot(path=str(grid_path), full_page=False)
    saved.append(grid_path)

    # Find template preview links
    links = await page.query_selector_all(config["preview_selector"])
    if not links:
        logger.warning(f"  [{marketplace_name}] No preview links found")
        return saved

    # Collect unique hrefs
    hrefs = []
    for link in links[:15]:
        href = await link.get_attribute("href")
        if href and href not in hrefs:
            if href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(search_url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"
            hrefs.append(href)
        if len(hrefs) >= MAX_PREVIEWS_PER_SITE:
            break

    # Screenshot each preview page
    for i, href in enumerate(hrefs):
        try:
            await page.goto(href, wait_until="networkidle", timeout=25000)
            await page.wait_for_timeout(1500)

            # Scroll to load lazy content
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(300)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(500)

            preview_path = output_dir / f"{marketplace_name}_{i + 1}.png"
            await page.screenshot(path=str(preview_path), full_page=True)
            saved.append(preview_path)
            logger.info(f"  [{marketplace_name}] Saved: {preview_path.name}")

        except Exception as e:
            logger.warning(f"  [{marketplace_name}] Preview {i + 1} failed: {e}")
            continue

    return saved


def _get_existing_screenshots(industry: str) -> list[Path]:
    """Return existing screenshot paths for an industry."""
    settings = get_settings()
    industry_dir = settings.design_screenshots_dir / industry.lower().strip()
    if not industry_dir.exists():
        return []

    image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    return [
        f for f in industry_dir.iterdir()
        if f.is_file() and f.suffix.lower() in image_extensions
    ]
