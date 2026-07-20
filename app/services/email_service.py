"""
Email Service - drafts and sends outreach emails.

Rules:
- By default, no email is sent automatically - drafts are created and held
  for human review (pending_approval).
- Exception: if the "auto-send high confidence" setting is enabled
  (toggled on the Settings page), leads whose confidence level is HIGH are
  automatically approved and sent right after drafting - no human click
  required for that tier. Medium/low confidence leads always require a
  human to approve them, regardless of this setting.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

from app.config import get_settings
from app.core.llm_provider import get_llm_provider, llm_unconfigured_reason
from app.core.models import Lead, LeadStatus, ConfidenceLevel
from app.core.prompts import EMAIL_DRAFT_PROMPT
from app.core.scoring import compute_confidence
from app.storage.database import get_database, AUTO_SEND_SETTING_KEY

logger = logging.getLogger(__name__)


class EmailService:
    """Handles email drafting and sending with approval gate."""

    async def draft_email(self, lead: Lead) -> Lead:
        """Generate an email draft for the lead. Does NOT send."""
        logger.info(f"Drafting email for {lead.company_name}")
        lead.add_log("Drafting outreach email")

        # Check if LLM is actually configured
        unconfigured = llm_unconfigured_reason()
        fallback_used = False

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
            if unconfigured:
                raise RuntimeError(unconfigured)
            response = await llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                json_mode=True,
            )
            data = response.as_json()
            # Handle list responses from some models
            if isinstance(data, list) and len(data) > 0:
                data = data[0] if isinstance(data[0], dict) else {}
            if not isinstance(data, dict):
                data = {}
            lead.email_subject = data.get("subject", f"A fresh look for {lead.company_name}'s website")
            lead.email_body = data.get("body", self._fallback_email_body(lead))
        except Exception as e:
            fallback_used = True
            logger.error(f"Email draft failed: {e}")
            lead.add_log(f"Email draft generation failed: {str(e)}")
            lead.email_subject = f"A fresh look for {lead.company_name}'s website"
            lead.email_body = self._fallback_email_body(lead)

        # Loud warning when fallback is used
        if fallback_used:
            if unconfigured:
                warn_msg = f"NOT an AI-drafted email — AI NOT CONFIGURED: {unconfigured}"
            else:
                warn_msg = "NOT an AI-drafted email — LLM call failed, using generic template"
            logger.warning(warn_msg)
            lead.add_log("AI not configured: NOT an AI-drafted email, using fallback template.")

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

        # Auto-send gate: only fires for HIGH confidence leads, and only if
        # the human has explicitly turned this on via the Settings page.
        # Medium/low confidence always stops at pending_approval for review.
        auto_send_enabled = db.get_bool_setting(AUTO_SEND_SETTING_KEY, default=False)
        if auto_send_enabled and lead.confidence and lead.confidence.level == ConfidenceLevel.HIGH:
            lead.add_log("Auto-send enabled and confidence is HIGH - approving and sending automatically")
            lead.status = LeadStatus.APPROVED
            db.save_lead(lead)
            lead = await self.approve_and_send(lead)

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

        if settings.mail_dry_run:
            if not settings.dry_run_recipient:
                logger.error("MAIL_DRY_RUN is enabled but DRY_RUN_RECIPIENT is not configured")
                lead.add_log("Email sending failed: MAIL_DRY_RUN enabled but no DRY_RUN_RECIPIENT configured")
                db = get_database()
                db.save_lead(lead)
                return lead
            recipient = settings.dry_run_recipient
            logger.info(
                f"MAIL_DRY_RUN enabled: redirecting email intended for {lead.email!r} "
                f"to dry-run recipient {recipient!r}"
            )
            lead.add_log(f"Dry-run: email redirected to {recipient} (intended recipient: {lead.email or '(none)'})")
        else:
            if not lead.email:
                logger.error(f"Cannot send email for lead {lead.company_name!r}: lead.email is empty")
                lead.add_log("Email sending failed: lead has no email address on file")
                db = get_database()
                db.save_lead(lead)
                return lead
            recipient = lead.email

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
