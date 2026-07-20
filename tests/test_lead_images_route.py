"""Tests for the /leads/{id}/images/{filename} preview-image serving route."""

import os
import shutil
import pytest

os.environ["LLM_PROVIDER"] = "mock"
os.environ["VISION_PROVIDER"] = "mock"

from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.models import Lead, LeadStatus
from app.main import app
from app.storage.database import get_database

client = TestClient(app)

_TEST_LEAD_IDS = [
    "test-lead-images-a", "test-lead-images-b", "test-lead-images-c", "test-lead-images-ghost",
]


@pytest.fixture(autouse=True)
def _cleanup_lead_dirs():
    yield
    settings = get_settings()
    for lead_id in _TEST_LEAD_IDS:
        shutil.rmtree(settings.output_dir / lead_id, ignore_errors=True)


def _make_lead_with_image(lead_id, filename="photo_1.jpg", content=b"fake-jpeg-bytes"):
    settings = get_settings()
    lead = Lead(id=lead_id, company_name="Test Biz", industry="bakery", location="Singapore",
                status=LeadStatus.REDESIGN_GENERATED, local_image_paths=[filename])
    images_dir = settings.output_dir / lead_id / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / filename).write_bytes(content)
    get_database().save_lead(lead)
    return lead


def test_serves_a_valid_lead_image():
    _make_lead_with_image("test-lead-images-a")
    resp = client.get("/leads/test-lead-images-a/images/photo_1.jpg")
    assert resp.status_code == 200
    assert resp.content == b"fake-jpeg-bytes"
    assert resp.headers["content-type"] == "image/jpeg"


def test_unknown_lead_returns_404():
    resp = client.get("/leads/does-not-exist-xyz/images/photo_1.jpg")
    assert resp.status_code == 404


def test_filename_not_in_leads_own_list_returns_404():
    _make_lead_with_image("test-lead-images-a")
    resp = client.get("/leads/test-lead-images-a/images/not_my_photo.jpg")
    assert resp.status_code == 404


def test_path_traversal_attempt_returns_404():
    _make_lead_with_image("test-lead-images-a")
    settings = get_settings()
    secret = settings.output_dir / "secret.txt"
    secret.write_text("do not leak")
    try:
        resp = client.get("/leads/test-lead-images-a/images/..%2Fsecret.txt")
        assert resp.status_code in (404, 400)
        assert b"do not leak" not in resp.content
    finally:
        secret.unlink(missing_ok=True)


def test_wrong_lead_cannot_access_another_leads_image():
    """Two leads with a file of the same generated name must never cross-serve."""
    _make_lead_with_image("test-lead-images-a", filename="photo_1.jpg", content=b"lead-a-photo")
    _make_lead_with_image("test-lead-images-b", filename="photo_1.jpg", content=b"lead-b-photo")

    resp_a = client.get("/leads/test-lead-images-a/images/photo_1.jpg")
    resp_b = client.get("/leads/test-lead-images-b/images/photo_1.jpg")
    assert resp_a.content == b"lead-a-photo"
    assert resp_b.content == b"lead-b-photo"


def test_missing_file_on_disk_returns_404_even_if_listed():
    lead = Lead(id="test-lead-images-ghost", company_name="Ghost Biz", industry="bakery",
                location="Singapore", status=LeadStatus.REDESIGN_GENERATED,
                local_image_paths=["ghost.jpg"])
    get_database().save_lead(lead)
    resp = client.get("/leads/test-lead-images-ghost/images/ghost.jpg")
    assert resp.status_code == 404
