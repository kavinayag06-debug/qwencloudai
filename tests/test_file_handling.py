"""Tests for Windows-friendly file handling."""

import os
import pytest
from pathlib import Path


def test_pathlib_handles_windows_paths():
    """Pathlib normalizes paths correctly on Windows."""
    p = Path("data") / "output" / "test.html"
    assert "data" in str(p)
    assert "output" in str(p)
    # Path separators handled by pathlib
    assert p.name == "test.html"
    assert p.suffix == ".html"


def test_output_dir_creation(tmp_path):
    """Output directories can be created."""
    output = tmp_path / "output" / "lead-123"
    output.mkdir(parents=True, exist_ok=True)
    assert output.exists()
    assert output.is_dir()


def test_html_file_write_and_read(tmp_path):
    """HTML files can be written and read with UTF-8."""
    html_content = "<!DOCTYPE html><html><head><title>Test</title></head><body>Hello</body></html>"
    html_path = tmp_path / "test.html"
    html_path.write_text(html_content, encoding="utf-8")

    read_back = html_path.read_text(encoding="utf-8")
    assert read_back == html_content


def test_zip_creation(tmp_path):
    """Zip files can be created and are valid."""
    import zipfile

    # Create test files
    (tmp_path / "index.html").write_text("<html>test</html>", encoding="utf-8")
    (tmp_path / "screenshot.png").write_bytes(b"fake png data")

    zip_path = tmp_path / "package.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(tmp_path / "index.html", "index.html")
        zf.write(tmp_path / "screenshot.png", "screenshots/screenshot.png")

    assert zip_path.exists()
    assert zip_path.stat().st_size > 0

    # Verify contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "index.html" in names
        assert "screenshots/screenshot.png" in names


def test_path_with_spaces(tmp_path):
    """Paths with spaces work correctly."""
    dir_with_spaces = tmp_path / "my project" / "output files"
    dir_with_spaces.mkdir(parents=True, exist_ok=True)
    test_file = dir_with_spaces / "test.html"
    test_file.write_text("test", encoding="utf-8")
    assert test_file.exists()


def test_data_directory_structure(tmp_path):
    """Required directory structure can be created."""
    dirs = [
        tmp_path / "data" / "design_screenshots",
        tmp_path / "data" / "output",
        tmp_path / "data" / "cache",
        tmp_path / "data" / "knowledge",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        assert d.exists()


def test_image_extensions_detection():
    """Image file extensions are detected correctly."""
    extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    test_files = ["design1.png", "mockup.jpg", "screenshot.jpeg", "anim.gif", "photo.webp"]

    for f in test_files:
        assert Path(f).suffix.lower() in extensions
