"""SQLite database layer using SQLAlchemy."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import get_settings
from app.core.models import Lead, LeadStatus, WebsiteAnalysis, StyleTraits, ConfidenceScore

Base = declarative_base()


class LeadRecord(Base):
    """SQLite table for leads."""
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_name = Column(String, nullable=False)
    website_url = Column(String, default="")
    industry = Column(String, default="")
    location = Column(String, default="")
    address = Column(String, default="")
    phone = Column(String, default="")
    email = Column(String, default="")
    description = Column(String, default="")
    discovery_source = Column(String, default="")
    status = Column(String, default=LeadStatus.DISCOVERED.value)
    website_analysis_json = Column(Text, default=None)
    style_traits_json = Column(Text, default=None)
    confidence_json = Column(Text, default=None)
    html_path = Column(String, default=None)
    screenshot_paths_json = Column(Text, default="[]")
    email_subject = Column(String, default="")
    email_body = Column(Text, default="")
    zip_path = Column(String, default=None)
    logs_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Database:
    """Database access layer."""

    def __init__(self):
        settings = get_settings()
        db_path = settings.data_dir / "app.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def save_lead(self, lead: Lead) -> Lead:
        """Save or update a lead."""
        session = self.get_session()
        try:
            if not lead.id:
                lead.id = str(uuid.uuid4())

            record = session.query(LeadRecord).filter_by(id=lead.id).first()
            if record is None:
                record = LeadRecord(id=lead.id)
                session.add(record)

            record.company_name = lead.company_name
            record.website_url = lead.website_url
            record.industry = lead.industry
            record.location = lead.location
            record.address = lead.address
            record.phone = lead.phone
            record.email = lead.email
            record.description = lead.description
            record.discovery_source = lead.discovery_source
            record.status = lead.status.value
            record.html_path = lead.html_path
            record.email_subject = lead.email_subject
            record.email_body = lead.email_body
            record.zip_path = lead.zip_path
            record.screenshot_paths_json = json.dumps(lead.screenshot_paths)
            record.logs_json = json.dumps(lead.logs)
            record.updated_at = datetime.utcnow()

            if lead.website_analysis:
                record.website_analysis_json = lead.website_analysis.model_dump_json()
            if lead.style_traits:
                record.style_traits_json = lead.style_traits.model_dump_json()
            if lead.confidence:
                record.confidence_json = lead.confidence.model_dump_json()

            session.commit()
            return lead
        finally:
            session.close()

    def get_lead(self, lead_id: str) -> Optional[Lead]:
        """Get a lead by ID."""
        session = self.get_session()
        try:
            record = session.query(LeadRecord).filter_by(id=lead_id).first()
            if not record:
                return None
            return self._record_to_lead(record)
        finally:
            session.close()

    def get_all_leads(self) -> list[Lead]:
        """Get all leads."""
        session = self.get_session()
        try:
            records = session.query(LeadRecord).order_by(LeadRecord.updated_at.desc()).all()
            return [self._record_to_lead(r) for r in records]
        finally:
            session.close()

    def delete_lead(self, lead_id: str) -> bool:
        """Delete a lead."""
        session = self.get_session()
        try:
            record = session.query(LeadRecord).filter_by(id=lead_id).first()
            if record:
                session.delete(record)
                session.commit()
                return True
            return False
        finally:
            session.close()

    def clear_all(self) -> None:
        """Clear all leads (for testing)."""
        session = self.get_session()
        try:
            session.query(LeadRecord).delete()
            session.commit()
        finally:
            session.close()

    def _record_to_lead(self, record: LeadRecord) -> Lead:
        """Convert DB record to Lead model."""
        lead = Lead(
            id=record.id,
            company_name=record.company_name,
            website_url=record.website_url,
            industry=record.industry,
            location=record.location,
            address=record.address,
            phone=record.phone,
            email=record.email,
            description=record.description,
            discovery_source=record.discovery_source,
            status=LeadStatus(record.status),
            html_path=record.html_path,
            email_subject=record.email_subject,
            email_body=record.email_body,
            zip_path=record.zip_path,
            screenshot_paths=json.loads(record.screenshot_paths_json or "[]"),
            logs=json.loads(record.logs_json or "[]"),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        if record.website_analysis_json:
            lead.website_analysis = WebsiteAnalysis.model_validate_json(record.website_analysis_json)
        if record.style_traits_json:
            lead.style_traits = StyleTraits.model_validate_json(record.style_traits_json)
        if record.confidence_json:
            lead.confidence = ConfidenceScore.model_validate_json(record.confidence_json)
        return lead


# Singleton
_db: Optional[Database] = None


def get_database() -> Database:
    """Get or create database singleton."""
    global _db
    if _db is None:
        _db = Database()
    return _db
