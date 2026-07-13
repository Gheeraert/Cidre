# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
"""Inventaire facultatif des URL publiques calculees depuis l'Excel courant."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import pandas as pd

from .data_models import load_config
from .excel_data import (
    detect_books_sheet,
    load_actualites,
    load_books,
    load_collections,
    load_pages,
    load_revues,
)
from .routes import (
    AUTOMATIC_TARGETS,
    actualite_anchor_candidate,
    actualite_anchor_id,
    actualite_book_href,
    book_public_path,
    collection_public_path,
    collection_public_slug,
    editorial_page_public_path,
    editorial_page_slug,
    is_generated_editorial_page_slug,
    revue_public_path,
)
from .utils import as_str, norm_bool, slugify


INVENTORY_COLUMNS = [
    "entity_type",
    "excel_row",
    "identifier",
    "title",
    "active",
    "explicit_slug",
    "slug_origin",
    "slug_candidate",
    "final_slug",
    "auto_uniquified",
    "public_path",
    "notes",
]


def _row(
    entity_type: str,
    public_path: str,
    *,
    excel_row: Any = "",
    identifier: Any = "",
    title: Any = "",
    active: Any = "",
    explicit_slug: Any = "",
    slug_origin: Any = "",
    slug_candidate: Any = "",
    final_slug: Any = "",
    auto_uniquified: Any = "",
    notes: Any = "",
) -> dict[str, str]:
    return {
        "entity_type": as_str(entity_type),
        "excel_row": as_str(excel_row),
        "identifier": as_str(identifier),
        "title": as_str(title),
        "active": as_str(active),
        "explicit_slug": as_str(explicit_slug),
        "slug_origin": as_str(slug_origin),
        "slug_candidate": as_str(slug_candidate),
        "final_slug": as_str(final_slug),
        "auto_uniquified": as_str(auto_uniquified),
        "public_path": as_str(public_path),
        "notes": as_str(notes),
    }


def _excel_row(index: Any) -> str:
    try:
        return str(int(index) + 2)
    except Exception:
        return ""


def _load_site_frames(excel_path: Path):
    with pd.ExcelFile(excel_path) as wb:
        cfg = load_config(wb, "CONFIG")
        books_sheet = detect_books_sheet(wb, cfg.books_sheet)
        books = load_books(wb, books_sheet)
        pages = load_pages(wb, cfg.pages_sheet)
        collections = load_collections(wb, cfg.collections_sheet)
        revues = load_revues(wb, cfg.revues_sheet)
        actualites = load_actualites(wb)
    return books, pages, collections, revues, actualites


def collect_url_inventory(excel_path: Path) -> list[dict[str, str]]:
    """Retourne l'inventaire calcule uniquement depuis le classeur courant."""
    books, pages, collections, revues, actualites = _load_site_frames(Path(excel_path))
    rows: list[dict[str, str]] = []

    for target in sorted(AUTOMATIC_TARGETS):
        rows.append(_row("automatic_page", target, active=True, final_slug=target.removesuffix(".html")))

    id13_to_slug: dict[str, str] = {}
    for idx, r in books.iterrows():
        id13 = as_str(r.get("id13"))
        final_slug = as_str(r.get("slug"))
        if id13 and final_slug:
            id13_to_slug[id13] = final_slug
        identifier = id13 or f"{as_str(r.get('titre_norm'))} row-{_excel_row(idx)}"
        rows.append(_row(
            "book",
            book_public_path(final_slug),
            excel_row=_excel_row(idx),
            identifier=identifier,
            title=r.get("titre_norm"),
            active=True,
            explicit_slug=r.get("_source_slug"),
            slug_origin=r.get("_slug_origin"),
            slug_candidate=r.get("_slug_candidate"),
            final_slug=final_slug,
            auto_uniquified=bool(r.get("_slug_was_uniquified")),
        ))

    if collections is None or collections.empty:
        names = sorted({as_str(x) for x in books["collection"].dropna().tolist() if as_str(x)}) \
            if "collection" in books.columns else []
        for name in names:
            slug = slugify(name)
            rows.append(_row(
                "collection",
                collection_public_path(slug, slug),
                identifier=slug,
                title=name,
                active=True,
                slug_origin="derived_from_books",
                slug_candidate=slug,
                final_slug=slug,
                notes="COLLECTIONS absent ou vide",
            ))
    else:
        active_collections = collections[collections.get("is_active", 1).apply(norm_bool)].copy()
        for idx, c in active_collections.iterrows():
            final_slug = collection_public_slug(c.get("slug"), c.get("collection_id"))
            rows.append(_row(
                "collection",
                collection_public_path(c.get("slug"), c.get("collection_id")),
                excel_row=_excel_row(idx),
                identifier=c.get("collection_id"),
                title=c.get("name"),
                active=True,
                explicit_slug=c.get("slug"),
                slug_origin="explicit" if as_str(c.get("slug")) else "fallback_collection_id",
                slug_candidate=final_slug,
                final_slug=final_slug,
            ))

    if revues is not None and not revues.empty:
        active_revues = revues[revues.get("is_active", 1).apply(norm_bool)].copy()
        for idx, r in active_revues.iterrows():
            final_slug = as_str(r.get("slug"))
            rows.append(_row(
                "revue",
                revue_public_path(r.get("slug"), r.get("title"), r.get("journal_id")),
                excel_row=_excel_row(idx),
                identifier=r.get("journal_id"),
                title=r.get("title"),
                active=True,
                explicit_slug=r.get("_source_slug"),
                slug_origin=r.get("_slug_origin"),
                slug_candidate=r.get("_slug_candidate"),
                final_slug=final_slug,
            ))

    has_open_access_page = False
    if pages is not None and not pages.empty:
        pages_df = pages.copy()
        has_published_column = "is_published" in pages_df.columns
        if has_published_column:
            pages_df["is_published"] = pages_df["is_published"].apply(norm_bool)
            pages_df = pages_df[pages_df["is_published"]].copy()
        for idx, p in pages_df.iterrows():
            slug = editorial_page_slug(p.get("slug"))
            if not is_generated_editorial_page_slug(slug):
                continue
            if slug == "open-access":
                has_open_access_page = True
            rows.append(_row(
                "editorial_page",
                editorial_page_public_path(slug),
                excel_row=_excel_row(idx),
                identifier=slug,
                title=p.get("title"),
                active=True,
                explicit_slug=slug,
                slug_origin="explicit",
                slug_candidate=slug,
                final_slug=slug,
            ))
    if not has_open_access_page:
        rows.append(_row(
            "fallback_page",
            "open-access.html",
            identifier="open-access",
            active=True,
            slug_origin="generated_fallback",
            slug_candidate="open-access",
            final_slug="open-access",
            notes="Page de secours garantie par build_pages",
        ))

    used_actualite_ids: set[str] = set()
    if actualites is not None and not actualites.empty:
        for idx, a in actualites.iterrows():
            candidate = actualite_anchor_candidate(a.get("title"))
            anchor_id = actualite_anchor_id(a.get("title"), used_actualite_ids)
            identifier = as_str(a.get("title")) or as_str(a.get("id13")) or f"row-{_excel_row(idx)}"
            rows.append(_row(
                "actualite_anchor",
                f"actualites.html#actu-{anchor_id}",
                excel_row=_excel_row(idx),
                identifier=identifier,
                title=a.get("title"),
                active=True,
                slug_origin="fallback_title" if as_str(a.get("title")) else "fallback_actu",
                slug_candidate=candidate,
                final_slug=anchor_id,
                auto_uniquified=anchor_id != candidate,
            ))
            id13 = as_str(a.get("id13"))
            if id13 and id13 in id13_to_slug:
                rows.append(_row(
                    "actualite_book_link",
                    actualite_book_href(id13_to_slug[id13], ".").removeprefix("./"),
                    excel_row=_excel_row(idx),
                    identifier=id13,
                    title=a.get("title"),
                    active=True,
                    final_slug=id13_to_slug[id13],
                    notes="Lien interne derive de id13",
                ))

    return rows


def write_url_inventory_csv(rows: list[dict[str, str]], csv_path: Path) -> None:
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INVENTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def make_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inventaire facultatif des URL publiques CIDRE.")
    parser.add_argument("--excel", required=True, help="Chemin du classeur Excel CIDRE")
    parser.add_argument("--csv", required=True, help="Chemin du CSV d'inventaire a ecrire")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_arg_parser().parse_args(argv)
    rows = collect_url_inventory(Path(args.excel))
    write_url_inventory_csv(rows, Path(args.csv))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
