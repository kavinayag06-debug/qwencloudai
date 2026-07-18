"""Tests for EmailService.approve_and_send recipient routing (C-1)."""

import logging
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ["LLM_PROVIDER"] = "mock"
os.environ["VISION_PROVIDER"] = "mock"

from app.core.models import Lead, LeadStatus
from app.services.email_service import EmailService


async def test_draft_email_unconfigured_llm_is_loud(caplog):
    """Drafting with a mock/unconfigured LLM must warn loudly, matching the
    same "NOT AI-generated" loudness html_generator.generate() has — silently
    producing a generic canned draft with no warning is the bug being fixed."""
    lead = Lead(id="lead-2", company_name="Real Biz", industry="bakery", location="Singapore")

    with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
        result = await EmailService().draft_email(lead)

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("NOT an AI-drafted email" in msg for msg in warnings)
    assert any("AI not configured" in log for log in result.logs)


def _make_approved_lead(email: str) -> Lead:
    return Lead(
        id="lead-1",
        company_name="Real Biz",
        email=email,
        status=LeadStatus.APPROVED,
        email_subject="A fresh look for your website",
        email_body="Hi there, ...",
    )


@pytest.fixture
def smtp_configured(monkeypatch):
    """Non-empty SMTP creds so the 'configured' check passes."""
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")


def _mock_smtp_server():
    sent_messages = []
    server = MagicMock()
    server.__enter__.return_value = server
    server.send_message.side_effect = lambda msg: sent_messages.append(msg)
    return server, sent_messages


async def test_dry_run_redirects_away_from_lead_email(smtp_configured, monkeypatch):
    """MAIL_DRY_RUN=true must never send to the real lead.email."""
    monkeypatch.setenv("MAIL_DRY_RUN", "true")
    monkeypatch.setenv("DRY_RUN_RECIPIENT", "dryrun-inbox@example.com")

    lead = _make_approved_lead(email="realbusiness@example.com")
    server, sent_messages = _mock_smtp_server()

    with patch("smtplib.SMTP", return_value=server):
        result = await EmailService().approve_and_send(lead)

    assert result.status == LeadStatus.SENT
    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "dryrun-inbox@example.com"
    assert "realbusiness@example.com" not in sent_messages[0]["To"]
    # The real intended recipient must still be visible in the lead's logs.
    assert any("realbusiness@example.com" in log for log in result.logs)


async def test_real_send_uses_lead_email_when_dry_run_disabled(smtp_configured, monkeypatch):
    """MAIL_DRY_RUN=false must send to the actual lead.email, not a hardcoded address."""
    monkeypatch.setenv("MAIL_DRY_RUN", "false")

    lead = _make_approved_lead(email="realbusiness@example.com")
    server, sent_messages = _mock_smtp_server()

    with patch("smtplib.SMTP", return_value=server):
        result = await EmailService().approve_and_send(lead)

    assert result.status == LeadStatus.SENT
    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "realbusiness@example.com"


async def test_real_send_refuses_when_lead_email_missing(smtp_configured, monkeypatch):
    """No hardcoded fallback: refuse and log an error instead of silently no-op'ing."""
    monkeypatch.setenv("MAIL_DRY_RUN", "false")

    lead = _make_approved_lead(email="")

    with patch("smtplib.SMTP") as mock_smtp_cls:
        result = await EmailService().approve_and_send(lead)

    mock_smtp_cls.assert_not_called()
    assert result.status != LeadStatus.SENT
    assert any("no email address" in log.lower() for log in result.logs)


async def test_dry_run_refuses_when_recipient_not_configured(smtp_configured, monkeypatch):
    """Dry-run mode with no DRY_RUN_RECIPIENT configured must not silently drop or crash."""
    monkeypatch.setenv("MAIL_DRY_RUN", "true")
    monkeypatch.setenv("DRY_RUN_RECIPIENT", "")

    lead = _make_approved_lead(email="realbusiness@example.com")

    with patch("smtplib.SMTP") as mock_smtp_cls:
        result = await EmailService().approve_and_send(lead)

    mock_smtp_cls.assert_not_called()
    assert result.status != LeadStatus.SENT
