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
from app.config import get_settings
from app.core.models import Lead, LeadStatus, ConfidenceLevel, DiscoveryRequest
from app.storage.database import get_database, AUTO_SEND_SETTING_KEY

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
    # Always pass auto_send_enabled for the nav popup
    db = get_database()
    context.setdefault("auto_send_enabled", db.get_bool_setting(AUTO_SEND_SETTING_KEY, default=False))
    return templates.TemplateResponse(request, template_name, context)


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Dashboard home - shows leads grouped by whether they need human review."""
    db = get_database()
    leads = db.get_all_leads()

    need_intervention = []
    no_intervention = []
    for lead in leads:
        if lead.confidence and lead.confidence.level == ConfidenceLevel.HIGH:
            no_intervention.append(lead)
        else:
            need_intervention.append(lead)

    # How many of the "no intervention" leads are actually still waiting to
    # be sent (i.e. what "Send All" would act on).
    sendable_high_confidence_count = sum(
        1 for lead in no_intervention if lead.status == LeadStatus.PENDING_APPROVAL
    )

    return _render(request, "index.html", {
        "need_intervention": need_intervention,
        "no_intervention": no_intervention,
        "sendable_high_confidence_count": sendable_high_confidence_count,
        "title": "Reb Design - Redesign Agent",
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
    """Run the full pipeline from the dashboard with geolocation."""
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
    await pipeline.run_full_pipeline(discovery_request)
    return RedirectResponse(url="/", status_code=303)


@router.post("/run-discovery", response_class=HTMLResponse)
async def run_discovery_action(request: Request):
    """Run discovery only with geolocation."""
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


@router.post("/leads/send-all", response_class=HTMLResponse)
async def send_all_high_confidence(request: Request):
    """Send All - approve and send every high-confidence lead still pending approval."""
    db = get_database()
    leads = db.get_all_leads()
    pipeline = _get_pipeline()

    for lead in leads:
        if (
            lead.confidence
            and lead.confidence.level == ConfidenceLevel.HIGH
            and lead.status == LeadStatus.PENDING_APPROVAL
        ):
            lead.status = LeadStatus.APPROVED
            lead.add_log("Approved via 'Send All' (high confidence)")
            db.save_lead(lead)
            await pipeline.email_service.approve_and_send(lead)

    return RedirectResponse(url="/", status_code=303)


@router.post("/leads/{lead_id}/regenerate", response_class=HTMLResponse)
async def regenerate_lead(lead_id: str):
    """Regenerate the redesign (analysis -> HTML -> screenshots -> email draft) for a lead."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.add_log("Regenerating redesign...")
    db.save_lead(lead)

    pipeline = _get_pipeline()
    await pipeline.process_single_lead(lead_id)

    return RedirectResponse(url="/", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page - currently: toggle auto-send for high-confidence leads."""
    db = get_database()
    auto_send_enabled = db.get_bool_setting(AUTO_SEND_SETTING_KEY, default=False)
    return _render(request, "settings.html", {
        "auto_send_enabled": auto_send_enabled,
        "title": "Settings",
    })


@router.post("/settings/auto-send", response_class=HTMLResponse)
async def update_auto_send_setting(enabled: bool = Form(False)):
    """Toggle the auto-send-for-high-confidence setting (called via fetch from popup)."""
    db = get_database()
    db.set_bool_setting(AUTO_SEND_SETTING_KEY, enabled)
    return HTMLResponse(content="ok", status_code=200)


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
