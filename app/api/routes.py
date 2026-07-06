"""
API Routes - RESTful endpoints for the redesign agent.

Endpoints:
- GET /api/health - Health check
- POST /api/discovery/run - Run discovery pipeline
- GET /api/leads - List all leads
- GET /api/leads/{lead_id} - Lead detail
- POST /api/leads/{lead_id}/generate - Generate redesign
- POST /api/leads/{lead_id}/screenshots - Render screenshots
- POST /api/leads/{lead_id}/email - Create email draft
- POST /api/leads/{lead_id}/approve - Approve send
- POST /api/leads/{lead_id}/reject - Reject send
- GET /api/leads/{lead_id}/download - Download zip
- GET /api/logs - View logs
- POST /api/pipeline/run - Run full pipeline
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.agents.pipeline import AgentPipeline
from app.core.models import DiscoveryRequest, Lead, LeadStatus
from app.storage.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Singleton pipeline
_pipeline: Optional[AgentPipeline] = None


def get_pipeline() -> AgentPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = AgentPipeline()
    return _pipeline


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "message": "QwenCloud AI Redesign Agent is running"}


@router.post("/discovery/run")
async def run_discovery(request: DiscoveryRequest = None, background_tasks: BackgroundTasks = None):
    """Run business discovery."""
    pipeline = get_pipeline()
    if request is None:
        request = DiscoveryRequest()
    leads = await pipeline.run_discovery_only(request)
    return {
        "status": "complete",
        "count": len(leads),
        "leads": [_lead_summary(l) for l in leads],
    }


@router.post("/pipeline/run")
async def run_full_pipeline(request: DiscoveryRequest = None):
    """Run the full agent pipeline."""
    pipeline = get_pipeline()
    if request is None:
        request = DiscoveryRequest()
    leads = await pipeline.run_full_pipeline(request)
    return {
        "status": "complete",
        "count": len(leads),
        "leads": [_lead_summary(l) for l in leads],
    }


@router.get("/leads")
async def list_leads():
    """Get all leads."""
    db = get_database()
    leads = db.get_all_leads()
    return {"leads": [_lead_summary(l) for l in leads]}


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str):
    """Get lead detail."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _lead_detail(lead)


@router.post("/leads/{lead_id}/generate")
async def generate_redesign(lead_id: str):
    """Generate HTML redesign for a lead."""
    pipeline = get_pipeline()
    lead = await pipeline.process_single_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"status": "complete", "lead": _lead_summary(lead)}


@router.post("/leads/{lead_id}/screenshots")
async def render_screenshots(lead_id: str):
    """Render screenshots for a lead's HTML."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    pipeline = get_pipeline()
    lead = await pipeline.screenshot_renderer.render(lead)
    return {"status": "complete", "screenshots": lead.screenshot_paths}


@router.post("/leads/{lead_id}/email")
async def create_email_draft(lead_id: str):
    """Create an email draft for a lead."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    pipeline = get_pipeline()
    lead = await pipeline.email_service.draft_email(lead)
    return {
        "status": "complete",
        "subject": lead.email_subject,
        "body": lead.email_body,
    }


@router.post("/leads/{lead_id}/approve")
async def approve_send(lead_id: str):
    """Approve email sending for a lead."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = LeadStatus.APPROVED
    lead.add_log("Email approved for sending")
    db.save_lead(lead)

    # Actually send
    pipeline = get_pipeline()
    lead = await pipeline.email_service.approve_and_send(lead)
    return {"status": "approved", "lead_status": lead.status.value}


@router.post("/leads/{lead_id}/reject")
async def reject_send(lead_id: str):
    """Reject email for a lead."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = LeadStatus.REJECTED
    lead.add_log("Email rejected")
    db.save_lead(lead)
    return {"status": "rejected"}


@router.get("/leads/{lead_id}/download")
async def download_zip(lead_id: str):
    """Download the zip package for a lead."""
    db = get_database()
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.zip_path or not Path(lead.zip_path).exists():
        raise HTTPException(status_code=404, detail="Zip package not available")

    return FileResponse(
        path=lead.zip_path,
        filename=Path(lead.zip_path).name,
        media_type="application/zip",
    )


@router.get("/logs")
async def get_logs():
    """Get all lead logs."""
    db = get_database()
    leads = db.get_all_leads()
    all_logs = []
    for lead in leads:
        for log_entry in lead.logs:
            all_logs.append({"lead": lead.company_name, "log": log_entry})
    return {"logs": all_logs}


@router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str):
    """Delete a lead."""
    db = get_database()
    success = db.delete_lead(lead_id)
    if not success:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"status": "deleted"}


def _lead_summary(lead: Lead) -> dict:
    """Compact lead summary for list views."""
    return {
        "id": lead.id,
        "company_name": lead.company_name,
        "website_url": lead.website_url,
        "industry": lead.industry,
        "location": lead.location,
        "status": lead.status.value,
        "confidence_level": lead.confidence.level.value if lead.confidence else "unknown",
        "confidence_score": lead.confidence.overall if lead.confidence else 0,
        "has_html": bool(lead.html_path),
        "has_screenshots": len(lead.screenshot_paths) > 0,
        "has_email": bool(lead.email_subject),
    }


def _lead_detail(lead: Lead) -> dict:
    """Full lead detail."""
    return {
        "id": lead.id,
        "company_name": lead.company_name,
        "website_url": lead.website_url,
        "industry": lead.industry,
        "location": lead.location,
        "address": lead.address,
        "phone": lead.phone,
        "email": lead.email,
        "description": lead.description,
        "discovery_source": lead.discovery_source,
        "status": lead.status.value,
        "website_analysis": lead.website_analysis.model_dump() if lead.website_analysis else None,
        "style_traits": lead.style_traits.model_dump() if lead.style_traits else None,
        "confidence": lead.confidence.model_dump() if lead.confidence else None,
        "html_path": lead.html_path,
        "screenshot_paths": lead.screenshot_paths,
        "email_subject": lead.email_subject,
        "email_body": lead.email_body,
        "zip_path": lead.zip_path,
        "logs": lead.logs,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
    }
