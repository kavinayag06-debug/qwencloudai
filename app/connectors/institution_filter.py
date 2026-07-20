"""Shared non-commercial-institution exclusion for discovery connectors.

Target leads are small commercial brick-and-mortar businesses. Schools,
hospitals, government offices, and similar public/civic institutions are
never a fit, even though some (e.g. Google's "school" place type) overlap
with legitimate commercial categories we do want (e.g. private tuition
centres). Structured type evidence (Google Places `primaryType`) is
authoritative and checked first; connectors without structured type data
fall back to a conservative name/domain heuristic that intentionally does
not touch words like "clinic", "dental", or "tuition" so legitimate small
businesses are never rejected.
"""

import re
from urllib.parse import urlsplit

# Google Places API (New) primaryType values that indicate a non-commercial
# institution rather than a small business, even when the search query that
# found them targeted a legitimate business category (e.g. "tuition" ->
# "school" has no dedicated Google type for private tuition centres).
GOOGLE_INSTITUTION_TYPES = {
    "school", "primary_school", "secondary_school", "university",
    "hospital",
    "local_government_office", "government_office", "city_hall", "courthouse", "embassy",
    "community_center",
    "place_of_worship", "church", "mosque", "synagogue", "hindu_temple",
    "library", "post_office", "fire_station", "police",
}

# Conservative name substrings for connectors with no structured type data
# (Exa, web-directory). Deliberately narrow and specific — general words like
# "clinic", "dental", "medical", "tuition", or "care" are never included,
# since those are legitimate small-business categories this app targets.
_INSTITUTION_NAME_HINTS = (
    "primary school", "secondary school", "high school", "international school",
    "university", "polytechnic",
    "ministry of", "town council", "city council", "municipal council",
    "public hospital", "general hospital", "polyclinic",
    "community centre", "community center", "community club",
    "place of worship", "church", "mosque", "synagogue", "hindu temple", "buddhist temple",
    "public library", "national library",
    "fire station", "police station", "courthouse", "embassy of",
)

_INSTITUTION_DOMAIN_LABELS = {"gov", "edu", "mil"}


def is_institution_place_type(primary_type: str) -> bool:
    """True if a Google Places `primaryType` is a non-commercial institution.

    Only acts on an actual structured type value — an empty/unknown type is
    never treated as an institution, since we prefer structured evidence over
    guessing.
    """
    return bool(primary_type) and primary_type.lower().strip() in GOOGLE_INSTITUTION_TYPES


def is_institution_name_or_domain(name: str, url: str = "") -> bool:
    """Conservative name/domain heuristic for connectors with no place-type data.

    Intentionally narrow: only matches specific institutional phrases, never
    generic words that legitimate commercial tuition centres or private
    clinics would also use.
    """
    lowered_name = (name or "").lower()
    parsed_url = urlsplit(url if "://" in (url or "") else f"//{url or ''}")
    hostname_labels = (parsed_url.hostname or "").lower().rstrip(".").split(".")
    domain_suffix = (
        hostname_labels[-2:]
        if hostname_labels and len(hostname_labels[-1]) == 2
        else hostname_labels[-1:]
    )
    if any(label in _INSTITUTION_DOMAIN_LABELS for label in domain_suffix):
        return True
    if any(
        re.search(rf"(?<!\w){re.escape(hint)}(?!\w)", lowered_name)
        for hint in _INSTITUTION_NAME_HINTS
    ):
        return True
    return False
