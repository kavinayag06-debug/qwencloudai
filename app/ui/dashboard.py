"""
Dashboard - Server-rendered web UI using FastAPI + Jinja2.

Provides:
- Lead list with scores, confidence, status
- Detail pages with analysis, preview, email draft
- Approve/reject controls
- Download zip packages
"""

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

from app.agents.pipeline import AgentPipeline
from app.config import get_settings
from app.core.models import LeadStatus, DiscoveryRequest
from app.storage.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter()
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

_pipeline = None

# ponytail: single-process in-memory flag, not a job queue — good enough for a
# local single-worker dashboard. Resets to False (silently) if the server
# restarts mid-run; a real deployment would track this in the DB instead.
_pipeline_status = {"running": False}


async def _run_pipeline_in_background(pipeline: AgentPipeline, discovery_request: DiscoveryRequest) -> None:
    _pipeline_status["running"] = True
    try:
        await pipeline.run_full_pipeline(discovery_request)
    finally:
        _pipeline_status["running"] = False


# Same pattern as _pipeline_status, per-lead: which leads are currently being
# processed via the single-lead "Process This Lead" button.
_processing_lead_ids: set[str] = set()


async def _process_single_lead_in_background(pipeline: AgentPipeline, lead_id: str) -> None:
    _processing_lead_ids.add(lead_id)
    try:
        await pipeline.process_single_lead(lead_id)
    finally:
        _processing_lead_ids.discard(lead_id)


def _get_pipeline() -> AgentPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = AgentPipeline()
    return _pipeline


def _render(request: Request, template_name: str, context: dict) -> HTMLResponse:
    """Helper to render templates with consistent interface."""
    return templates.TemplateResponse(request, template_name, context)


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Dashboard home - shows lead list."""
    db = get_database()
    leads = db.get_all_leads()
    return _render(request, "index.html", {
        "leads": leads,
        "title": "QwenCloud AI - Redesign Agent",
        "pipeline_running": _pipeline_status["running"],
    })


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
async def lead_detail_page(request: Request, lead_id: str):
    """Lead detail page."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return _render(request, "lead_detail.html", {
        "lead": lead,
        "title": f"{lead.company_name} - Detail",
        "processing": lead_id in _processing_lead_ids,
    })


@router.post("/leads/{lead_id}/process", response_class=HTMLResponse)
async def process_lead_action(lead_id: str, background_tasks: BackgroundTasks):
    """Run the full per-lead pipeline (analysis -> HTML -> screenshots -> email) for
    just this one lead, in the background so the page doesn't hang."""
    db = get_database()
    if not db.get_lead(lead_id):
        raise HTTPException(status_code=404, detail="Lead not found")

    pipeline = _get_pipeline()
    background_tasks.add_task(_process_single_lead_in_background, pipeline, lead_id)
    return RedirectResponse(url=f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/approve", response_class=HTMLResponse)
async def approve_lead(lead_id: str):
    """Approve email sending."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = LeadStatus.APPROVED
    lead.add_log("Email approved via dashboard")
    db.save_lead(lead)

    # Send email
    pipeline = _get_pipeline()
    await pipeline.email_service.approve_and_send(lead)

    return RedirectResponse(url=f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/reject", response_class=HTMLResponse)
async def reject_lead(lead_id: str):
    """Reject email."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = LeadStatus.REJECTED
    lead.add_log("Email rejected via dashboard")
    db.save_lead(lead)

    return RedirectResponse(url=f"/leads/{lead_id}", status_code=303)


@router.post("/run-pipeline", response_class=HTMLResponse)
async def run_pipeline_action(request: Request, background_tasks: BackgroundTasks):
    """Kick off the full pipeline in the background and return immediately.

    The pipeline can take many minutes (multiple leads, each several LLM
    calls) — awaiting it here would leave the browser looking hung with no
    feedback. Each lead's status is saved to the DB as it progresses, so the
    dashboard already shows live progress on every refresh.
    """
    form = await request.form()
    lat = form.get("latitude")
    lng = form.get("longitude")

    settings = get_settings()
    discovery_request = DiscoveryRequest(
        location=settings.default_location,
        country=settings.default_country,
        max_results=settings.max_leads,
        latitude=float(lat) if lat else None,
        longitude=float(lng) if lng else None,
    )

    pipeline = _get_pipeline()
    background_tasks.add_task(_run_pipeline_in_background, pipeline, discovery_request)
    return RedirectResponse(url="/", status_code=303)


@router.post("/run-discovery", response_class=HTMLResponse)
async def run_discovery_action(request: Request):
    """Run discovery only with optional geolocation."""
    form = await request.form()
    lat = form.get("latitude")
    lng = form.get("longitude")

    settings = get_settings()
    discovery_request = DiscoveryRequest(
        location=settings.default_location,
        country=settings.default_country,
        max_results=settings.max_leads,
        latitude=float(lat) if lat else None,
        longitude=float(lng) if lng else None,
    )

    pipeline = _get_pipeline()
    await pipeline.run_discovery_only(discovery_request)
    return RedirectResponse(url="/", status_code=303)


@router.get("/leads/{lead_id}/preview", response_class=HTMLResponse)
async def preview_html(lead_id: str):
    """Preview the generated HTML with image paths rewritten for web serving."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead or not lead.html_path:
        raise HTTPException(status_code=404, detail="HTML not available")

    html_path = Path(lead.html_path)
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="HTML file not found")

    html_content = html_path.read_text(encoding="utf-8")

    # Rewrite relative image paths (e.g. "images/photo_1.jpg") to our serving endpoint
    html_content = html_content.replace(
        'src="images/',
        f'src="/leads/{lead_id}/images/'
    )
    html_content = html_content.replace(
        "src='images/",
        f"src='/leads/{lead_id}/images/"
    )

    return HTMLResponse(content=html_content)


@router.get("/leads/{lead_id}/images/{filename}")
async def serve_lead_image(lead_id: str, filename: str):
    """Serve images from a lead's output/images folder."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead or not lead.html_path:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Images are stored in the same directory as the HTML, under images/
    lead_dir = Path(lead.html_path).parent
    image_path = lead_dir / "images" / filename

    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    # Determine media type
    suffix = image_path.suffix.lower()
    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                   ".webp": "image/webp", ".gif": "image/gif"}
    media_type = media_types.get(suffix, "image/jpeg")

    return FileResponse(path=str(image_path), media_type=media_type)


@router.get("/leads/{lead_id}/download")
async def download_zip(lead_id: str):
    """Download zip package."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead or not lead.zip_path:
        raise HTTPException(status_code=404, detail="Zip not available")

    zip_path = Path(lead.zip_path)
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Zip file not found")

    return FileResponse(
        path=str(zip_path),
        filename=zip_path.name,
        media_type="application/zip",
    )


@router.get("/leads/{lead_id}/screenshot/{filename}")
async def serve_screenshot(lead_id: str, filename: str):
    """Serve a screenshot image."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    for ss_path in lead.screenshot_paths:
        if Path(ss_path).name == filename:
            if Path(ss_path).exists():
                return FileResponse(path=ss_path, media_type="image/png")

    raise HTTPException(status_code=404, detail="Screenshot not found")


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """View all logs - one entry per lead with latest status."""
    db = get_database()
    leads = db.get_all_leads()
    all_logs = []
    for lead in leads:
        latest_log = lead.logs[-1] if lead.logs else "No activity"
        all_logs.append({
            "company": lead.company_name,
            "id": lead.id,
            "status": lead.status.value,
            "latest_log": latest_log,
        })

    return _render(request, "logs.html", {
        "logs": all_logs,
        "title": "Logs",
    })
