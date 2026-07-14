from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .utils import as_str, normalize_id13
from .validation import SEVERITY_ALERT, ValidationIssue


PUBLISHED_SLUG_ALERT_CODES = {
    "BOOK_SLUG_CHANGED",
    "PUBLISHED_CATALOGUE_UNREADABLE",
    "PUBLISHED_CATALOGUE_AMBIGUOUS_ID13",
    "PUBLISHED_BOOK_SLUG_MISSING",
}


@dataclass(frozen=True)
class SlugChange:
    id13: str
    title: str
    published_slug: str
    current_slug: str
    recommended_slug: str


@dataclass(frozen=True)
class PublishedSlugProblem:
    code: str
    identifier: str
    message: str


@dataclass(frozen=True)
class PublishedSlugComparison:
    changes: list[SlugChange]
    problems: list[PublishedSlugProblem]


def _load_previous_catalogue(path: Path) -> tuple[list[dict], list[PublishedSlugProblem]]:
    if not path.exists():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], [PublishedSlugProblem(
            "PUBLISHED_CATALOGUE_UNREADABLE",
            as_str(path),
            "La stabilité des URL des livres n'a pas pu être vérifiée car "
            f"l'ancien catalogue.json est illisible : {exc}.",
        )]
    if not isinstance(data, list):
        return [], [PublishedSlugProblem(
            "PUBLISHED_CATALOGUE_UNREADABLE",
            as_str(path),
            "La stabilité des URL des livres n'a pas pu être vérifiée car "
            "l'ancien catalogue.json n'a pas la structure attendue.",
        )]
    records: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            return [], [PublishedSlugProblem(
                "PUBLISHED_CATALOGUE_UNREADABLE",
                as_str(path),
                "La stabilité des URL des livres n'a pas pu être vérifiée car "
                "l'ancien catalogue.json contient une entrée invalide.",
            )]
        records.append(item)
    return records, []


def compare_published_book_slugs(previous_catalogue_path: Path,
                                 books: pd.DataFrame) -> PublishedSlugComparison:
    records, problems = _load_previous_catalogue(previous_catalogue_path)
    if problems or not records or books is None or books.empty:
        return PublishedSlugComparison([], problems)

    previous: dict[str, set[str]] = {}
    for record in records:
        id13 = normalize_id13(record.get("id13"))
        if not id13:
            continue
        previous.setdefault(id13, set()).add(as_str(record.get("slug")))

    previous_unique: dict[str, str] = {}
    for id13, slugs in previous.items():
        nonempty = {slug for slug in slugs if slug}
        if len(nonempty) > 1:
            problems.append(PublishedSlugProblem(
                "PUBLISHED_CATALOGUE_AMBIGUOUS_ID13",
                id13,
                "L'ancien catalogue.json associe le même ISBN à plusieurs slugs : "
                f"{', '.join(sorted(nonempty))}.",
            ))
        elif not nonempty:
            problems.append(PublishedSlugProblem(
                "PUBLISHED_BOOK_SLUG_MISSING",
                id13,
                "L'ancien catalogue.json contient cet ISBN sans slug exploitable ; "
                "la stabilité de son URL ne peut pas être vérifiée.",
            ))
        else:
            previous_unique[id13] = next(iter(nonempty))

    changes: list[SlugChange] = []
    for _, row in books.iterrows():
        id13 = normalize_id13(row.get("id13"))
        if not id13 or id13 not in previous_unique:
            continue
        current_slug = as_str(row.get("slug"))
        published_slug = previous_unique[id13]
        if current_slug and current_slug != published_slug:
            changes.append(SlugChange(
                id13=id13,
                title=as_str(row.get("titre_norm")) or as_str(row.get("title")),
                published_slug=published_slug,
                current_slug=current_slug,
                recommended_slug=published_slug,
            ))
    return PublishedSlugComparison(changes, problems)


def published_slug_issues(comparison: PublishedSlugComparison) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for problem in comparison.problems:
        issues.append(ValidationIssue(
            severity=SEVERITY_ALERT,
            code=problem.code,
            entity="catalogue",
            identifier=problem.identifier,
            field="catalogue.json",
            message=problem.message,
        ))
    for change in comparison.changes:
        issues.append(ValidationIssue(
            severity=SEVERITY_ALERT,
            code="BOOK_SLUG_CHANGED",
            entity="book",
            identifier=change.id13,
            field="slug",
            message=(
                f"ISBN : {change.id13}\n"
                f"Titre : {change.title or '(titre absent)'}\n"
                f"Slug publié : {change.published_slug}\n"
                f"Slug demandé : {change.current_slug}\n"
                f"Slug recommandé : {change.recommended_slug}"
            ),
        ))
    return issues


def slug_correction_text(changes: list[SlugChange]) -> str:
    lines = ["ISBN\tslug recommandé"]
    lines.extend(f"{change.id13}\t{change.recommended_slug}" for change in changes)
    return "\n".join(lines)
