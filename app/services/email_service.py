"""
Email Service - drafts and sends outreach emails.

Rules:
- No email may be sent automatically until approved.
- Drafts are created and held for human review.
- Sending only happens after explicit approval.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

from app.config import get_settings
from app.core.llm_provider import get_llm_provider
from app.core.models import Lead, LeadStatus
from app.core.prompts import EMAIL_DRAFT_PROMPT
from app.core.scoring import compute_confidence
from app.storage.database import get_database

logger = logging.getLogger(__name__)


class EmailService:
    """Handles email drafting and sending with approval gate."""

    async def draft_email(self, lead: Lead) -> Lead:
        """Generate an email draft for the lead. Does NOT send."""
        logger.info(f"Drafting email for {lead.company_name}")
        lead.add_log("Drafting outreach email")

        design_problems = ", ".join(
            lead.website_analysis.design_problems[:5] if lead.website_analysis else ["outdated design"]
        )

        prompt = EMAIL_DRAFT_PROMPT.format(
            company_name=lead.company_name,
            industry=lead.industry,
            location=lead.location,
            design_problems=design_problems,
            redesign_summary=f"Modern, responsive landing page with {lead.style_traits.mood if lead.style_traits else 'professional'} design",
        )

        llm = get_llm_provider()
        try:
            response = await llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                json_mode=True,
            )
            data = response.as_json()
            lead.email_subject = data.get("subject", f"A fresh look for {lead.company_name}'s website")
            lead.email_body = data.get("body", self._fallback_email_body(lead))
        except Exception as e:
            logger.error(f"Email draft failed: {e}")
            lead.add_log(f"Email draft generation failed: {str(e)}")
            lead.email_subject = f"A fresh look for {lead.company_name}'s website"
            lead.email_body = self._fallback_email_body(lead)

        lead.status = LeadStatus.PENDING_APPROVAL
        lead.add_log("Email draft ready for approval")

        # Recompute confidence now that outreach_confidence can be scored
        if lead.website_analysis:
            lead.confidence = compute_confidence(
                analysis=lead.website_analysis,
                style_traits=lead.style_traits,
                industry=lead.industry,
                html_generated=bool(lead.html_path),
                email_drafted=True,
            )

        db = get_database()
        db.save_lead(lead)
        return lead

    async def approve_and_send(self, lead: Lead) -> Lead:
        """Approve and send the email. Only called after human approval."""
        if lead.status != LeadStatus.APPROVED:
            lead.add_log("Cannot send: email not approved")
            return lead

        settings = get_settings()
        if not settings.smtp_user or not settings.smtp_password:
            lead.add_log("Email sending skipped: SMTP not configured")
            lead.status = LeadStatus.APPROVED
            db = get_database()
            db.save_lead(lead)
            return lead

        # Force recipient to the configured client email
        recipient = "xxpotatoot@gmail.com"

        try:
            msg = MIMEMultipart()
            msg["From"] = f"{settings.email_from_name} <{settings.email_from_address}>"
            msg["To"] = recipient
            msg["Subject"] = lead.email_subject

            msg.attach(MIMEText(lead.email_body, "plain"))

            # Attach zip if available
            if lead.zip_path and Path(lead.zip_path).exists():
                zip_path = Path(lead.zip_path)
                attachment = MIMEBase("application", "zip")
                attachment.set_payload(zip_path.read_bytes())
                encoders.encode_base64(attachment)
                attachment.add_header(
                    "Content-Disposition", f"attachment; filename={zip_path.name}"
                )
                msg.attach(attachment)

            # Send
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)

            lead.status = LeadStatus.SENT
            lead.add_log("Email sent successfully")

        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            lead.add_log(f"Email sending failed: {str(e)}")

        db = get_database()
        db.save_lead(lead)
        return lead

    def _fallback_email_body(self, lead: Lead) -> str:
        """Fallback email body when LLM generation fails."""
        return f"""Hi there,

I came across {lead.company_name}'s website and noticed a few areas where a fresh design could help attract more customers and better showcase what you offer.

As a web designer specializing in {lead.industry} businesses in {lead.location}, I've put together a complimentary landing page concept for you. It's modern, mobile-friendly, and designed to convert visitors into customers.

I'd love to share the design with you — no strings attached. Would you be open to a quick chat about it?

Best regards,
[Your Name]
"""
