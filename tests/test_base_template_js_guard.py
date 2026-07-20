"""Regression test for the uncaught JS error on pages using the compact header.

base.html's inline script previously called
document.getElementById('settings-toggle').addEventListener(...) unconditionally,
which threw on any page rendering _page_header.html (lead detail, logs,
settings) since that header has no #settings-toggle element. The fix null-guards
both the toggle lookup and the popup lookup inside the document-level click
handler. This is verified live via chrome-devtools-axi during mock-mode
browser validation; these are the fast, dependency-free regression checks.
"""

from pathlib import Path

BASE_HTML = (
    Path(__file__).resolve().parent.parent / "app" / "templates" / "base.html"
).read_text(encoding="utf-8")

PAGE_HEADER_HTML = (
    Path(__file__).resolve().parent.parent / "app" / "templates" / "_page_header.html"
).read_text(encoding="utf-8")


def test_settings_toggle_lookup_is_null_guarded():
    assert "var settingsToggle = document.getElementById('settings-toggle');" in BASE_HTML
    assert "if (settingsToggle) {" in BASE_HTML
    # The old unconditional call pattern must not remain anywhere in the file.
    assert "document.getElementById('settings-toggle').addEventListener" not in BASE_HTML


def test_document_click_handler_guards_popup_lookup():
    assert "if (popup && !e.target.closest('.settings-popup-wrapper'))" in BASE_HTML


def test_compact_header_has_no_settings_toggle_element():
    """Confirms the fix is necessary: the compact header genuinely lacks the
    element base.html's script looks up, on every page that uses it."""
    assert 'id="settings-toggle"' not in PAGE_HEADER_HTML
    assert 'id="settings-popup"' not in PAGE_HEADER_HTML
