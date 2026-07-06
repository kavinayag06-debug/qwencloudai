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

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

from app.agents.pipeline import AgentPipeline
from app.core.models import LeadStatus, DiscoveryRequest
from app.storage.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter()
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

_pipeline = None


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
    })


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
async def run_pipeline_action(request: Request):
    """Run the full pipeline from the dashboard."""
    pipeline = _get_pipeline()
    leads = await pipeline.run_full_pipeline()
    return RedirectResponse(url="/", status_code=303)


@router.post("/run-discovery", response_class=HTMLResponse)
async def run_discovery_action(request: Request):
    """Run discovery only."""
    pipeline = _get_pipeline()
    await pipeline.run_discovery_only()
    return RedirectResponse(url="/", status_code=303)


@router.get("/leads/{lead_id}/preview", response_class=HTMLResponse)
async def preview_html(lead_id: str):
    """Preview the generated HTML."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead or not lead.html_path:
        raise HTTPException(status_code=404, detail="HTML not available")

    html_path = Path(lead.html_path)
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="HTML file not found")

    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


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
    """View all logs."""
    db = get_database()
    leads = db.get_all_leads()
    all_logs = []
    for lead in leads:
        for log_entry in lead.logs:
            all_logs.append({"company": lead.company_name, "id": lead.id, "log": log_entry})

    return _render(request, "logs.html", {
        "logs": all_logs,
        "title": "Logs",
    })
