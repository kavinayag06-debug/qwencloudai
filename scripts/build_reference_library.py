#!/usr/bin/env python3
"""
Build Reference Library — populates data/design_screenshots/<industry>/
with real commercial template screenshots from template marketplaces.

Usage:
    python scripts/build_reference_library.py                    # all industries
    python scripts/build_reference_library.py restaurant salon   # specific ones
    python scripts/build_reference_library.py --max-age-days 7   # skip if < 7 days old

Requirements:
    - playwright (pip install playwright && playwright install chromium)
    - This is a standalone offline script, NOT part of the live pipeline.

What it does:
    For each industry keyword:
    1. Searches Themeforest, Framer, and Webflow template marketplaces
    2. Screenshots the search results grid
    3. Opens the top 3-5 template preview pages and takes full-page screenshots
    4. Saves under data/design_screenshots/<industry>/<marketplace>_<n>.png
    5. Caches with timestamps — skips industries scraped within --max-age-days

These screenshots inform composition/spacing/type-scale/layout caliber for the
vision model. They are NEVER used to copy specific templates.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Project root
ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = ROOT / "data" / "design_screenshots"
CACHE_FILE = SCREENSHOTS_DIR / ".cache_metadata.json"

# All industries to populate
ALL_INDUSTRIES = [
    "restaurant",
    "cafe",
    "bakery",
    "florist",
    "salon",
    "spa",
    "gym",
    "clinic",
    "retail",
    "fashion",
    "sports",
]

# Marketplace search configs
MARKETPLACES = {
    "themeforest": {
        "search_url": "https://themeforest.net/search/{query}",
        "query_transform": lambda industry: f"{industry} website template",
        "preview_selector": "a.product-card__link, a[data-item-id], .product-list__item a",
        "max_previews": 4,
    },
    "framer": {
        "search_url": "https://framer.com/marketplace/templates?query={query}",
        "query_transform": lambda industry: industry,
        "preview_selector": "a[href*='/templates/']",
        "max_previews": 4,
    },
    "webflow": {
        "search_url": "https://webflow.com/templates/search?query={query}",
        "query_transform": lambda industry: industry,
        "preview_selector": "a[href*='/templates/']",
        "max_previews": 4,
    },
}


def load_cache() -> dict:
    """Load the cache metadata."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_cache(cache: dict):
    """Save cache metadata."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def is_fresh(cache: dict, industry: str, max_age_days: int) -> bool:
    """Check if an industry's screenshots are fresh enough."""
    entry = cache.get(industry)
    if not entry:
        return False
    timestamp = entry.get("timestamp", 0)
    age_days = (time.time() - timestamp) / 86400
    return age_days < max_age_days


async def screenshot_marketplace(
    page, industry: str, marketplace_name: str, config: dict, output_dir: Path
) -> int:
    """Search a marketplace and screenshot top template previews.

    Returns number of screenshots saved.
    """
    query = config["query_transform"](industry)
    search_url = config["search_url"].format(query=query.replace(" ", "+"))
    saved = 0

    try:
        logger.info(f"  [{marketplace_name}] Searching: {search_url}")
        await page.goto(search_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)  # Let lazy content load

        # Check if page loaded something meaningful
        content = await page.content()
        if len(content) < 5000:
            logger.warning(f"  [{marketplace_name}] Page seems empty or blocked, skipping")
            return 0

        # Screenshot the search results grid
        grid_path = output_dir / f"{marketplace_name}_grid.png"
        await page.screenshot(path=str(grid_path), full_page=False)
        logger.info(f"  [{marketplace_name}] Saved search grid: {grid_path.name}")
        saved += 1

        # Find preview links
        preview_selector = config["preview_selector"]
        links = await page.query_selector_all(preview_selector)

        if not links:
            logger.warning(f"  [{marketplace_name}] No preview links found with selector: {preview_selector}")
            return saved

        # Collect unique hrefs
        hrefs = []
        for link in links[:20]:  # Check up to 20 links
            href = await link.get_attribute("href")
            if href and href not in hrefs:
                # Make absolute if relative
                if href.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(search_url)
                    href = f"{parsed.scheme}://{parsed.netloc}{href}"
                hrefs.append(href)
            if len(hrefs) >= config["max_previews"]:
                break

        logger.info(f"  [{marketplace_name}] Found {len(hrefs)} template preview links")

        # Screenshot each preview page
        for i, href in enumerate(hrefs):
            try:
                await page.goto(href, wait_until="networkidle", timeout=25000)
                await page.wait_for_timeout(1500)

                # Scroll down to load lazy content
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await page.wait_for_timeout(300)
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(500)

                preview_path = output_dir / f"{marketplace_name}_{i + 1}.png"
                await page.screenshot(path=str(preview_path), full_page=True)
                logger.info(f"  [{marketplace_name}] Saved preview {i + 1}: {preview_path.name}")
                saved += 1

            except Exception as e:
                logger.warning(f"  [{marketplace_name}] Preview {i + 1} failed: {e}")
                continue

    except Exception as e:
        logger.warning(f"  [{marketplace_name}] Search failed: {e}")

    return saved


async def build_for_industry(industry: str):
    """Build reference screenshots for a single industry."""
    from playwright.async_api import async_playwright

    output_dir = SCREENSHOTS_DIR / industry
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Building references for: {industry}")
    total_saved = 0

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
                count = await screenshot_marketplace(
                    page, industry, marketplace_name, config, output_dir
                )
                total_saved += count
            except Exception as e:
                logger.error(f"  [{marketplace_name}] Completely failed: {e}")
                continue

        await browser.close()

    logger.info(f"  → {industry}: {total_saved} screenshots saved to {output_dir}")
    return total_saved


async def main(industries: list[str], max_age_days: int):
    """Main entry point."""
    cache = load_cache()
    processed = 0
    skipped = 0

    for industry in industries:
        if is_fresh(cache, industry, max_age_days):
            logger.info(f"Skipping '{industry}' — references are less than {max_age_days} days old")
            skipped += 1
            continue

        count = await build_for_industry(industry)

        # Update cache
        cache[industry] = {
            "timestamp": time.time(),
            "count": count,
        }
        save_cache(cache)
        processed += 1

    logger.info(f"\nDone! Processed: {processed}, Skipped (fresh): {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build design reference screenshot library from template marketplaces."
    )
    parser.add_argument(
        "industries",
        nargs="*",
        default=ALL_INDUSTRIES,
        help="Industries to build references for (default: all)",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=14,
        help="Skip industries with references newer than N days (default: 14)",
    )
    args = parser.parse_args()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("ERROR: Playwright is required. Install it with:")
        print("  pip install playwright && playwright install chromium")
        sys.exit(1)

    asyncio.run(main(args.industries, args.max_age_days))
