# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
"""Regles centralisees des chemins publics statiques."""

from __future__ import annotations

import re
from typing import Any

from .utils import as_str, ensure_unique_slug, norm_bool, slugify


ROOT_AUTOMATIC_TARGETS = {
    "index.html",
    "catalogue.html",
    "nouveautes.html",
    "a-paraitre.html",
    "actualites.html",
}

SECTION_INDEX_TARGETS = {
    "collections/index.html",
    "revues/index.html",
}

AUTOMATIC_TARGETS = ROOT_AUTOMATIC_TARGETS | SECTION_INDEX_TARGETS
GENERATED_ROOT_HTML = ROOT_AUTOMATIC_TARGETS | {
    "contact.html",
    "open-access.html",
    "open_access.html",
    "commander.html",
    "commandes.html",
    "presentation.html",
    "soumettre-un-manuscrit.html",
}

IGNORED_EDITORIAL_PAGE_SLUGS = {"actualites", "actus"}
_BOOK_ROUTE_SAFE_RE = re.compile(r"[a-z0-9-]+")


def book_slug_origin(explicit_slug: Any, id13: Any) -> str:
    if as_str(explicit_slug):
        return "explicit"
    if as_str(id13):
        return "fallback_title_isbn"
    return "fallback_title"


def explicit_book_slug(explicit_slug: Any) -> str:
    source_slug = as_str(explicit_slug)
    if not source_slug:
        return ""
    if _BOOK_ROUTE_SAFE_RE.fullmatch(source_slug):
        return source_slug
    return slugify(source_slug)


def book_slug_candidate(explicit_slug: Any, title: Any, id13: Any) -> str:
    """Slug livre avant unicisation, avec le meme fallback que load_books."""
    source_slug = as_str(explicit_slug)
    if source_slug:
        return explicit_book_slug(source_slug)
    base = slugify(as_str(title) or "ouvrage")
    norm_id13 = as_str(id13)
    if norm_id13:
        base = f"{base}-{norm_id13}"
    return base


def book_public_path(slug: Any) -> str:
    return f"livres/{as_str(slug)}.html"


def book_href(slug: Any, rel_prefix: str = ".") -> str:
    return f"{rel_prefix}/{book_public_path(slug)}"


def collection_public_slug(slug: Any, collection_id: Any) -> str:
    raw_slug = as_str(slug)
    if raw_slug:
        return slugify(raw_slug)
    raw_id = as_str(collection_id)
    return slugify(raw_id) if raw_id else ""


def collection_public_path(slug: Any, collection_id: Any = "") -> str:
    return f"collections/{collection_public_slug(slug, collection_id)}.html"


def collection_href(slug: Any, collection_id: Any = "", rel_prefix: str = "..") -> str:
    return f"{rel_prefix}/{collection_public_path(slug, collection_id)}"


def revue_public_slug(slug: Any, title: Any, journal_id: Any) -> str:
    return slugify(as_str(slug) or as_str(title) or as_str(journal_id) or "revue")


def revue_public_path(slug: Any, title: Any = "", journal_id: Any = "") -> str:
    return f"revues/{revue_public_slug(slug, title, journal_id)}.html"


def revue_href(slug: Any, title: Any = "", journal_id: Any = "", rel_prefix: str = "..") -> str:
    return f"{rel_prefix}/{revue_public_path(slug, title, journal_id)}"


def editorial_page_slug(slug: Any) -> str:
    return slugify(as_str(slug)) if as_str(slug) else ""


def editorial_page_is_published(value: Any, has_column: bool = True) -> bool:
    return norm_bool(value) if has_column else True


def is_generated_editorial_page_slug(slug: Any) -> bool:
    page_slug = editorial_page_slug(slug)
    return bool(page_slug) and page_slug not in IGNORED_EDITORIAL_PAGE_SLUGS


def editorial_page_public_path(slug: Any) -> str:
    return f"{editorial_page_slug(slug)}.html"


def actualite_anchor_candidate(title: Any) -> str:
    raw_title = as_str(title)
    candidate = slugify(raw_title)
    if candidate == "item" and not any(ch.isalnum() for ch in raw_title):
        return "actu"
    return candidate or "actu"


def actualite_anchor_id(title: Any, used_ids: set[str]) -> str:
    return ensure_unique_slug(actualite_anchor_candidate(title), used_ids)


def actualites_public_path() -> str:
    return "actualites.html"


def actualites_href(rel_prefix: str = ".") -> str:
    return f"{rel_prefix}/{actualites_public_path()}"


def actualite_book_href(slug: Any, rel_prefix: str = ".") -> str:
    return book_href(slug, rel_prefix=rel_prefix)
