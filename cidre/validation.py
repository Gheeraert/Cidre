# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
"""Validation structuree des donnees CIDRE.

Ce module observe les donnees deja chargees et normalisees. Il ne modifie pas
les DataFrames et n'ecrit rien directement dans le site, sauf via la fonction
explicite d'export CSV.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from .data_models import SiteConfig
from .routes import (
    ROOT_AUTOMATIC_TARGETS,
    SECTION_INDEX_TARGETS,
    book_public_path,
    collection_public_path,
    editorial_page_public_path,
    editorial_page_slug,
    is_generated_editorial_page_slug,
    revue_public_path,
)
from .utils import (
    as_str,
    is_na,
    norm_bool,
    normalize_external_url,
    parse_pub_date,
    resolve_asset_source,
    slugify,
    to_float,
)


SEVERITY_BLOCKING = "blocking"
SEVERITY_ALERT = "alert"
SEVERITY_WARNING = "warning"

VALIDATION_COLUMNS = ["level", "code", "entity", "identifier", "field", "message"]

@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    entity: str
    identifier: str
    field: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue]

    @property
    def blocking_issues(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_BLOCKING]

    @property
    def alerts(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_ALERT]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_WARNING]

    @property
    def has_blocking_issues(self) -> bool:
        return bool(self.blocking_issues)

    @property
    def has_alerts(self) -> bool:
        return bool(self.alerts)


def format_validation_summary(report: ValidationReport) -> str:
    return (
        "Validation : "
        f"{len(report.blocking_issues)} blocage(s), "
        f"{len(report.alerts)} alerte(s), "
        f"{len(report.warnings)} avertissement(s)."
    )


class ValidationBlockingError(RuntimeError):
    def __init__(self, report: ValidationReport):
        self.report = report
        super().__init__(_summary(report.blocking_issues, "Blocage de validation"))


class ValidationAlertError(RuntimeError):
    def __init__(self, report: ValidationReport):
        self.report = report
        super().__init__(_summary(report.alerts, "Alertes de validation"))


def _summary(issues: Iterable[ValidationIssue], title: str) -> str:
    items = list(issues)
    if not items:
        return title
    first = items[0]
    suffix = f" (+ {len(items) - 1} autre(s))" if len(items) > 1 else ""
    return f"{title}: {first.code} - {first.message}{suffix}"


def _issue(severity: str, code: str, entity: str, identifier: str,
           field: str, message: str) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        code=code,
        entity=entity,
        identifier=identifier,
        field=field,
        message=message,
    )


def _row_identifier(row: pd.Series, fallback: str) -> str:
    for field in ("slug", "id13", "collection_id", "journal_id", "title", "titre_norm"):
        value = as_str(row.get(field))
        if value:
            return value
    return fallback


def _nonnull_values(values: Iterable[object]) -> list[str]:
    out: list[str] = []
    for v in values:
        s = as_str(v)
        if s:
            out.append(s)
    return out


def _duplicated_nonempty(df: pd.DataFrame, column: str) -> set[str]:
    if column not in df.columns:
        return set()
    vals = _nonnull_values(df[column].tolist())
    seen: set[str] = set()
    dup: set[str] = set()
    for v in vals:
        if v in seen:
            dup.add(v)
        seen.add(v)
    return dup


def _active_df(df: Optional[pd.DataFrame], active_col: str = "is_active") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if active_col not in df.columns:
        return df.copy()
    out = df.copy()
    out = out[out[active_col].apply(lambda v: True if is_na(v) else norm_bool(v))].copy()
    return out


def _target_duplicates(items: Iterable[tuple[str, str, str, str]],
                       entity: str) -> list[ValidationIssue]:
    seen: dict[str, tuple[str, str, str]] = {}
    reported: set[str] = set()
    issues: list[ValidationIssue] = []
    for item_entity, identifier, target, field in items:
        if not target:
            continue
        if target in seen:
            if target in reported:
                continue
            prev_entity, prev_identifier, _prev_field = seen[target]
            issues.append(_issue(
                SEVERITY_BLOCKING,
                "DUPLICATE_OUTPUT_TARGET",
                entity or item_entity,
                identifier,
                field,
                "Plusieurs entites visent le meme fichier de sortie : "
                f"{target} ({prev_entity}:{prev_identifier} et {item_entity}:{identifier}).",
            ))
            reported.add(target)
        else:
            seen[target] = (item_entity, identifier, field)
    return issues


def _cover_inventory(covers_dir: Optional[Path], out_dir: Optional[Path]) -> tuple[set[str], bool]:
    names: set[str] = set()
    known_location = False
    for base in (covers_dir, (out_dir / "covers") if out_dir else None):
        if not base or not base.exists() or not base.is_dir():
            continue
        known_location = True
        for p in base.iterdir():
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                names.add(p.name)
    return names, known_location


def validate_site_data(
    *,
    books: pd.DataFrame,
    cfg: Optional[SiteConfig] = None,
    pages: Optional[pd.DataFrame] = None,
    collections: Optional[pd.DataFrame] = None,
    revues: Optional[pd.DataFrame] = None,
    contacts: Optional[pd.DataFrame] = None,
    actualites: Optional[pd.DataFrame] = None,
    excel_path: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    covers_dir: Optional[Path] = None,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    cfg = cfg or SiteConfig()
    pages = pages if pages is not None else pd.DataFrame()
    collections = collections if collections is not None else pd.DataFrame()
    revues = revues if revues is not None else pd.DataFrame()
    actualites = actualites if actualites is not None else pd.DataFrame()

    issues.extend(_validate_output_dir(out_dir))
    issues.extend(_validate_books(books, collections, revues, covers_dir, out_dir))
    issues.extend(_validate_output_targets(pages, collections, revues))
    issues.extend(_validate_actualites(actualites))
    issues.extend(_validate_declared_assets(cfg, excel_path))

    return ValidationReport(issues)


def _validate_output_dir(out_dir: Optional[Path]) -> list[ValidationIssue]:
    if out_dir is None:
        return []
    issues: list[ValidationIssue] = []
    if out_dir.exists() and not out_dir.is_dir():
        issues.append(_issue(
            SEVERITY_BLOCKING,
            "OUTPUT_PATH_NOT_DIRECTORY",
            "site",
            as_str(out_dir),
            "out_dir",
            "Le chemin de sortie existe mais n'est pas un dossier.",
        ))
        return issues

    existing = out_dir
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent

    if existing.exists() and not existing.is_dir():
        issues.append(_issue(
            SEVERITY_BLOCKING,
            "OUTPUT_PARENT_NOT_DIRECTORY",
            "site",
            as_str(out_dir),
            "out_dir",
            "Un ancetre du chemin de sortie existe mais n'est pas un dossier.",
        ))
        return issues

    if existing.exists() and not os.access(existing, os.W_OK):
        issues.append(_issue(
            SEVERITY_BLOCKING,
            "OUTPUT_PARENT_NOT_WRITABLE",
            "site",
            as_str(out_dir),
            "out_dir",
            "Le dossier de sortie ou son parent n'est pas inscriptible.",
        ))
    return issues


def _validate_books(books: pd.DataFrame, collections: pd.DataFrame, revues: pd.DataFrame,
                    covers_dir: Optional[Path], out_dir: Optional[Path]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if books is None or books.empty:
        return issues

    slug_column = "_source_slug" if "_source_slug" in books.columns else "slug"
    for dup in sorted(_duplicated_nonempty(books, slug_column)):
        issues.append(_issue(
            SEVERITY_ALERT,
            "BOOK_SLUG_DUPLICATE",
            "book",
            dup,
            "slug",
            "Plusieurs livres portent le meme slug.",
        ))
    for dup in sorted(_duplicated_nonempty(books, "id13")):
        issues.append(_issue(
            SEVERITY_ALERT,
            "BOOK_ID13_DUPLICATE",
            "book",
            dup,
            "id13",
            "Plusieurs livres portent le meme ISBN/GTIN.",
        ))

    issues.extend(_target_duplicates(
        (
            ("book", _row_identifier(r, f"row-{idx + 2}"), book_public_path(r.get("slug")), "slug")
            for idx, r in books.iterrows()
        ),
        "book",
    ))

    cover_names, cover_location_known = _cover_inventory(covers_dir, out_dir)
    known_collections = _known_ids(collections, "collection_id")
    known_revues = _known_ids(revues, "journal_id")
    has_collection_reference = not collections.empty and bool(known_collections)
    has_revue_reference = not revues.empty and bool(known_revues)

    for idx, r in books.iterrows():
        ident = _row_identifier(r, f"row-{idx + 2}")
        title = as_str(r.get("titre_norm"))
        if not title:
            issues.append(_issue(
                SEVERITY_ALERT,
                "BOOK_TITLE_MISSING",
                "book",
                ident,
                "titre_norm",
                "Le titre du livre est absent.",
            ))

        id13 = as_str(r.get("id13"))
        if not id13:
            issues.append(_issue(
                SEVERITY_WARNING,
                "BOOK_ID13_MISSING",
                "book",
                ident,
                "id13",
                "ISBN/GTIN absent.",
            ))

        cover = Path(as_str(r.get("cover_file")).replace("\\", "/")).name
        if not cover:
            issues.append(_issue(
                SEVERITY_WARNING,
                "BOOK_COVER_MISSING",
                "book",
                ident,
                "cover_file",
                "Couverture absente.",
            ))
        elif cover_location_known and cover not in cover_names:
            issues.append(_issue(
                SEVERITY_WARNING,
                "BOOK_COVER_NOT_FOUND",
                "book",
                ident,
                "cover_file",
                f"Couverture declaree introuvable : {cover}.",
            ))

        if not as_str(r.get("Description courte")) and not as_str(r.get("Description longue")):
            issues.append(_issue(
                SEVERITY_WARNING,
                "BOOK_DESCRIPTION_MISSING",
                "book",
                ident,
                "Description courte",
                "Resume absent.",
            ))

        raw_date = as_str(r.get("date_parution_norm"))
        if raw_date and parse_pub_date(raw_date) is None:
            issues.append(_issue(
                SEVERITY_WARNING,
                "BOOK_DATE_INVALID",
                "book",
                ident,
                "date_parution_norm",
                "Date de parution non reconnue.",
            ))

        for field in ("order_url", "openedition_url"):
            raw_url = as_str(r.get(field))
            if raw_url and not normalize_external_url(raw_url):
                issues.append(_issue(
                    SEVERITY_WARNING,
                    "BOOK_URL_INVALID",
                    "book",
                    ident,
                    field,
                    f"URL externe invalide dans {field}.",
                ))

        price_raw = r.get("price")
        if not as_str(price_raw):
            price_raw = r.get("prix_ttc")
        if as_str(price_raw) and to_float(price_raw) is None:
            issues.append(_issue(
                SEVERITY_WARNING,
                "BOOK_PRICE_INVALID",
                "book",
                ident,
                "price",
                "Prix non numerique ou incoherent.",
            ))

        cid = slugify(as_str(r.get("collection_id"))) if as_str(r.get("collection_id")) else ""
        if cid and has_collection_reference and cid not in known_collections and cid not in known_revues:
            issues.append(_issue(
                SEVERITY_ALERT,
                "BOOK_COLLECTION_UNKNOWN",
                "book",
                ident,
                "collection_id",
                f"Livre rattache a une collection inconnue : {cid}.",
            ))
        if cid and has_revue_reference and _looks_like_revue(r) and cid not in known_revues:
            issues.append(_issue(
                SEVERITY_ALERT,
                "BOOK_REVUE_UNKNOWN",
                "book",
                ident,
                "collection_id",
                f"Numero de revue rattache a une revue inconnue : {cid}.",
            ))

    return issues


def _known_ids(df: pd.DataFrame, column: str) -> set[str]:
    if df is None or df.empty or column not in df.columns:
        return set()
    return {slugify(as_str(v)) for v in df[column].tolist() if as_str(v)}


def _looks_like_revue(row: pd.Series) -> bool:
    text = " ".join([
        as_str(row.get("collection")),
        as_str(row.get("collection_id")),
        as_str(row.get("titre_norm")),
    ]).lower()
    return "revue" in text or "n°" in text or "numero" in text or "numéro" in text


def _published_pages(pages: Optional[pd.DataFrame]) -> pd.DataFrame:
    if pages is None or pages.empty:
        return pd.DataFrame()
    df = pages.copy()
    if "is_published" in df.columns:
        df["is_published"] = df["is_published"].apply(norm_bool)
        df = df[df["is_published"]].copy()

    slugs = df["slug"].apply(editorial_page_slug) \
        if "slug" in df.columns else pd.Series([""] * len(df), index=df.index)
    df = df[slugs.astype(str).str.strip().ne("")].copy()
    df["_validation_slug"] = slugs.loc[df.index]
    df = df[df["_validation_slug"].apply(is_generated_editorial_page_slug)].copy()
    return df


def _validate_pages(pages: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    df = _published_pages(pages)
    if df.empty:
        return issues
    rows = []
    for idx, r in df.iterrows():
        slug = as_str(r.get("_validation_slug"))
        rows.append(("page", _row_identifier(r, f"row-{idx + 2}"), editorial_page_public_path(slug), "slug"))
    issues.extend(_target_duplicates(rows, "page"))
    return issues


def _validate_collections(collections: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if collections is None or collections.empty:
        return issues
    active = _active_df(collections)
    rows = []
    for idx, r in active.iterrows():
        ident = as_str(r.get("collection_id")) or as_str(r.get("slug")) or f"row-{idx + 2}"
        rows.append(("collection", ident, collection_public_path(r.get("slug"), r.get("collection_id")), "slug"))
    issues.extend(_target_duplicates(rows, "collection"))
    return issues


def _validate_revues(revues: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if revues is None or revues.empty:
        return issues
    active = _active_df(revues)
    rows = []
    for idx, r in active.iterrows():
        ident = as_str(r.get("journal_id")) or as_str(r.get("slug")) or f"row-{idx + 2}"
        rows.append(("revue", ident, revue_public_path(r.get("slug"), r.get("title"), r.get("journal_id")), "slug"))
    issues.extend(_target_duplicates(rows, "revue"))
    return issues


def _validate_output_targets(pages: pd.DataFrame, collections: pd.DataFrame,
                             revues: pd.DataFrame) -> list[ValidationIssue]:
    rows: list[tuple[str, str, str, str]] = []

    for target in sorted(ROOT_AUTOMATIC_TARGETS | SECTION_INDEX_TARGETS):
        rows.append(("automatic", target, target, "output"))

    published_pages = _published_pages(pages)
    if not published_pages.empty:
        for idx, r in published_pages.iterrows():
            slug = as_str(r.get("_validation_slug"))
            rows.append(("page", _row_identifier(r, f"row-{idx + 2}"), editorial_page_public_path(slug), "slug"))

    active_collections = _active_df(collections)
    if not active_collections.empty:
        for idx, r in active_collections.iterrows():
            ident = as_str(r.get("collection_id")) or as_str(r.get("slug")) or f"row-{idx + 2}"
            target = collection_public_path(r.get("slug"), r.get("collection_id"))
            if target != "collections/.html":
                rows.append(("collection", ident, target, "slug"))

    active_revues = _active_df(revues)
    if not active_revues.empty:
        for idx, r in active_revues.iterrows():
            ident = as_str(r.get("journal_id")) or as_str(r.get("slug")) or f"row-{idx + 2}"
            target = revue_public_path(r.get("slug"), r.get("title"), r.get("journal_id"))
            if target:
                rows.append(("revue", ident, target, "slug"))

    return _target_duplicates(rows, "site")


def _validate_actualites(actualites: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if actualites is None or actualites.empty:
        return issues
    for idx, r in actualites.iterrows():
        ident = as_str(r.get("title")) or as_str(r.get("id13")) or f"row-{idx + 2}"
        if not as_str(r.get("title")):
            issues.append(_issue(
                SEVERITY_ALERT,
                "ACTUALITE_TITLE_MISSING",
                "actualite",
                ident,
                "title",
                "Actualite active sans titre.",
            ))
        raw_url = as_str(r.get("link"))
        if raw_url and not normalize_external_url(raw_url):
            issues.append(_issue(
                SEVERITY_WARNING,
                "ACTUALITE_URL_INVALID",
                "actualite",
                ident,
                "link",
                "URL externe invalide dans une actualite.",
            ))
    return issues


def _validate_declared_assets(cfg: SiteConfig, excel_path: Optional[Path]) -> list[ValidationIssue]:
    if excel_path is None:
        return []
    excel_dir = excel_path.parent
    issues: list[ValidationIssue] = []
    declared = [
        ("logo_left", cfg.logo_left),
        ("logo_right", cfg.logo_right),
        ("favicon", cfg.favicon),
        ("footer_logo", cfg.footer_logo),
    ]
    if cfg.order_mode == "pdf" and cfg.order_pdf_filename:
        rel = as_str(cfg.order_pdf_filename).replace("\\", "/").strip().lstrip("/")
        if rel.startswith("assets/"):
            rel = rel[len("assets/"):]
        declared.append(("order_pdf_filename", f"assets/{rel}"))
    for field, rel in declared:
        rel_s = as_str(rel)
        if rel_s and not resolve_asset_source(excel_dir, rel_s):
            issues.append(_issue(
                SEVERITY_WARNING,
                "DECLARED_ASSET_NOT_FOUND",
                "asset",
                rel_s,
                field,
                "Asset declare introuvable.",
            ))
    return issues


def write_validation_csv(report: ValidationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=VALIDATION_COLUMNS)
        writer.writeheader()
        for issue in report.issues:
            writer.writerow({
                "level": issue.severity,
                "code": issue.code,
                "entity": issue.entity,
                "identifier": issue.identifier,
                "field": issue.field,
                "message": issue.message,
            })
