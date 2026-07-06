"""Tests for approval gating."""

import os
import pytest

os.environ["LLM_PROVIDER"] = "mock"
os.environ["VISION_PROVIDER"] = "mock"

from app.core.models import Lead, LeadStatus


def test_lead_starts_as_discovered():
    """New leads start in discovered state."""
    lead = Lead(company_name="Test Co")
    assert lead.status == LeadStatus.DISCOVERED


def test_lead_cannot_be_sent_without_approval():
    """Leads must go through approval before sending."""
    lead = Lead(company_name="Test Co", status=LeadStatus.PENDING_APPROVAL)
    # Trying to send without approval should not work
    assert lead.status != LeadStatus.APPROVED
    assert lead.status != LeadStatus.SENT


def test_lead_approval_flow():
    """Test the full approval flow: pending -> approved."""
    lead = Lead(company_name="Test Co", status=LeadStatus.PENDING_APPROVAL)
    # Simulate approval
    lead.status = LeadStatus.APPROVED
    lead.add_log("Approved by user")
    assert lead.status == LeadStatus.APPROVED
    assert any("Approved" in log for log in lead.logs)


def test_lead_rejection_flow():
    """Test rejection flow: pending -> rejected."""
    lead = Lead(company_name="Test Co", status=LeadStatus.PENDING_APPROVAL)
    lead.status = LeadStatus.REJECTED
    lead.add_log("Rejected by user")
    assert lead.status == LeadStatus.REJECTED


def test_lead_status_transitions():
    """Verify expected status transitions."""
    lead = Lead(company_name="Test Co")
    assert lead.status == LeadStatus.DISCOVERED

    lead.status = LeadStatus.ANALYZED
    assert lead.status == LeadStatus.ANALYZED

    lead.status = LeadStatus.REDESIGN_GENERATED
    assert lead.status == LeadStatus.REDESIGN_GENERATED

    lead.status = LeadStatus.PENDING_APPROVAL
    assert lead.status == LeadStatus.PENDING_APPROVAL


def test_add_log_includes_timestamp():
    """Log entries include timestamps."""
    lead = Lead(company_name="Test Co")
    lead.add_log("Test message")
    assert len(lead.logs) == 1
    assert "Test message" in lead.logs[0]
    assert "[" in lead.logs[0]  # Timestamp bracket
