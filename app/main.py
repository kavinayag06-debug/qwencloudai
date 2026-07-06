"""
QwenCloud AI - Website Redesign Agent

Main FastAPI application entry point.
Run with: uvicorn app.main:app --reload
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.ui.dashboard import router as ui_router
from app.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize app
app = FastAPI(
    title="QwenCloud AI Redesign Agent",
    description="AI-powered website redesign agent for local businesses",
    version="0.1.0",
)

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
app.include_router(api_router)
app.include_router(ui_router)


@app.on_event("startup")
async def startup():
    """Application startup."""
    settings = get_settings()
    logger.info("=" * 50)
    logger.info("QwenCloud AI Redesign Agent starting up")
    logger.info(f"  LLM Provider: {settings.llm_provider}")
    logger.info(f"  LLM Model: {settings.llm_model}")
    logger.info(f"  Location: {settings.default_location}")
    logger.info(f"  Max Leads: {settings.max_leads}")
    logger.info(f"  Data Dir: {settings.data_dir}")
    logger.info("=" * 50)


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )
