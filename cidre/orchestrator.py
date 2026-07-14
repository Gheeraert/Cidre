# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
# Module extrait de build_site.py (découpage sans changement fonctionnel).

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from . import utils
from .build import (
    build_book_pages, build_catalogue_json, build_catalogue_page,
    build_collections, build_home, build_new_titles,
    build_pages, build_revues, build_upcoming_page,
    copy_covers, copy_declared_assets,
)
from .data_models import load_config
from .excel_data import (
    build_actualites_json, build_actualites_page, build_collection_slug_map,
    build_revue_slug_map, copy_actualites_images, detect_books_sheet,
    load_actualites, load_books, load_collections,
    load_contacts, load_pages, load_revues,
)
from .ftp_publish import publish_ftp
from .output_transaction import staged_output
from .published_slugs import compare_published_book_slugs, published_slug_issues
from .utils import compute_available_covers, months_ago, norm_bool
from .validation import (
    ValidationAlertError, ValidationBlockingError,
    format_validation_summary, validate_site_data, write_validation_csv,
)

# -------------------------
# Orchestrator
# -------------------------

RESERVED_ASSET_ROOT_JSON = {"catalogue.json", "actualites.json"}
PUBLISHED_SLUG_ALERT_CODES = {
    "BOOK_SLUG_CHANGED",
    "PUBLISHED_CATALOGUE_UNREADABLE",
    "PUBLISHED_CATALOGUE_AMBIGUOUS_ID13",
    "PUBLISHED_BOOK_SLUG_MISSING",
}


class AssetSourceError(ValueError):
    """Configuration invalide du dossier source des assets."""


def build_site(excel_path: Path, out_dir: Path, covers_dir: Optional[Path],
               validate_only: bool = False, new_months: Optional[int] = None,
               progress_cb=None,
               publish: bool = False,
               force_alerts: bool = True,
               assets_dir: Optional[Path] = None):
    wb = pd.ExcelFile(excel_path)
    assets_dir = validate_assets_source(assets_dir, out_dir) if assets_dir else None

    cfg = load_config(wb, "CONFIG")
    if new_months is not None:
        cfg.new_months = int(new_months)

    books_sheet = detect_books_sheet(wb, cfg.books_sheet)
    books = load_books(wb, books_sheet)

    pages = load_pages(wb, cfg.pages_sheet)
    collections = load_collections(wb, cfg.collections_sheet)
    revues = load_revues(wb, cfg.revues_sheet)
    contacts = load_contacts(wb, cfg.contacts_sheet)
    actualites = load_actualites(wb)

    report = validate_site_data(
        books=books,
        cfg=cfg,
        pages=pages,
        collections=collections,
        revues=revues,
        contacts=contacts,
        actualites=actualites,
        excel_path=excel_path,
        out_dir=out_dir,
        covers_dir=covers_dir,
    )
    if report.has_blocking_issues:
        raise ValidationBlockingError(report)

    published_comparison = compare_published_book_slugs(out_dir / "catalogue.json", books)
    report.issues.extend(published_slug_issues(published_comparison))

    if report.has_alerts and not force_alerts:
        if any(issue.code in PUBLISHED_SLUG_ALERT_CODES for issue in report.alerts):
            raise ValidationAlertError(report)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_validation_csv(report, out_dir / "validation.csv")
        raise ValidationAlertError(report)

    if validate_only:
        out_dir.mkdir(parents=True, exist_ok=True)
        utils.AVAILABLE_COVERS = compute_available_covers(out_dir)
        remove_legacy_asset_json(out_dir)
        build_catalogue_json(books, out_dir)
        write_validation_csv(report, out_dir / "validation.csv")
        return report

    with staged_output(out_dir) as tx:
        _generate_site_into(
            target_dir=tx.staging_dir,
            excel_path=excel_path,
            cfg=cfg,
            books=books,
            pages=pages,
            collections=collections,
            revues=revues,
            contacts=contacts,
            actualites=actualites,
            covers_dir=covers_dir,
            assets_dir=assets_dir,
            report=report,
        )
        tx.commit()

    if publish:
        publish_ftp(cfg, out_dir, progress_cb=progress_cb)

    return report


def _generate_site_into(target_dir: Path, excel_path: Path, cfg, books: pd.DataFrame,
                        pages: pd.DataFrame, collections: pd.DataFrame,
                        revues: pd.DataFrame, contacts: pd.DataFrame,
                        actualites: pd.DataFrame, covers_dir: Optional[Path],
                        assets_dir: Optional[Path],
                        report) -> None:
    out_dir = target_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_generated_output(out_dir)

    if assets_dir:
        copy_assets_tree(assets_dir, out_dir)

    # covers (copie d'abord pour savoir ce qui existe vraiment)
    if covers_dir:
        copy_covers(covers_dir, out_dir)

    # inventaire des covers réellement présentes dans le dossier de sortie
    utils.AVAILABLE_COVERS = compute_available_covers(out_dir)

    # catalogue.json (ne listera que les covers existantes)
    build_catalogue_json(books, out_dir)

    # copy logos/favicon/pdf if declared
    copy_declared_assets(excel_path, out_dir, cfg)

    # Actualités (carrousel)
    if actualites is not None and not actualites.empty:
        copy_actualites_images(excel_path, out_dir, actualites)
    build_actualites_json(actualites, out_dir, books=books, max_items=10)
    build_actualites_page(cfg, out_dir)

    # validation report always produced
    write_validation_csv(report, out_dir / "validation.csv")

    today = date.today()
    cutoff = months_ago(today, cfg.new_months)

    upcoming = books[books["pub_date"].isna() | (books["pub_date"] > today)].copy()
    recent = books[
        books["pub_date"].notna() &
        (books["pub_date"] <= today) &
        (books["pub_date"] >= cutoff)
        ].copy()

    featured = books[
        books["home_featured"].apply(norm_bool)].copy() if "home_featured" in books.columns else books.iloc[0:0].copy()
    home_books = pd.concat([recent, featured], ignore_index=True).drop_duplicates(subset=["slug"])

    # Build pages
    build_pages(cfg, pages, contacts, out_dir)
    build_home(cfg, home_books, out_dir)
    build_catalogue_page(cfg, out_dir)
    build_new_titles(cfg, recent, out_dir, cfg.new_months)
    build_upcoming_page(cfg, upcoming, out_dir)
    # build_actualites_page(cfg, out_dir)
    # build_contacts(cfg, contacts, out_dir)

    build_book_pages(cfg, books, out_dir,
                     revue_slugs=build_revue_slug_map(revues),
                     collection_slugs=build_collection_slug_map(collections, books))
    build_collections(cfg, books, collections, out_dir)
    build_revues(cfg, books, revues, out_dir)


def remove_legacy_asset_json(out_dir: Path) -> None:
    """Supprime les anciennes copies générées sous assets/ sans toucher aux autres assets."""
    assets_dir = out_dir / "assets"
    if not assets_dir.exists():
        return
    if not assets_dir.is_dir():
        raise RuntimeError(
            f"Le chemin {assets_dir} existe mais n'est pas un dossier. "
            "Impossible de préparer le dossier de sortie."
        )
    for json_name in ("catalogue.json", "actualites.json"):
        legacy = assets_dir / json_name
        if legacy.exists():
            if legacy.is_dir():
                raise RuntimeError(
                    f"Le chemin {legacy} existe mais n'est pas un fichier. "
                    "Impossible de supprimer l'ancien JSON généré."
                )
            legacy.unlink()


def clean_generated_output(target_dir: Path) -> None:
    """Prépare le staging : seuls assets/ et covers/ persistent entre générations."""
    for persistent in ("assets", "covers"):
        path = target_dir / persistent
        if path.exists() and not path.is_dir():
            raise RuntimeError(
                f"Le chemin {path} existe mais n'est pas un dossier. "
                "Impossible de préparer le dossier de sortie."
            )

    for child in list(target_dir.iterdir()):
        if child.name in {"assets", "covers"} and child.is_dir():
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()

    (target_dir / "assets").mkdir(parents=True, exist_ok=True)
    (target_dir / "covers").mkdir(parents=True, exist_ok=True)
    remove_legacy_asset_json(target_dir)


def _resolve_path(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_assets_source(assets_dir: Optional[Path], out_dir: Path) -> Optional[Path]:
    if not assets_dir:
        return None

    src = _resolve_path(assets_dir)
    dst = _resolve_path(out_dir)
    if not src.exists():
        raise AssetSourceError(f"Dossier des assets introuvable : {src}")
    if not src.is_dir():
        raise AssetSourceError(f"Le chemin des assets n'est pas un dossier : {src}")
    try:
        next(src.iterdir(), None)
    except PermissionError as exc:
        raise AssetSourceError(f"Dossier des assets illisible : {src}") from exc

    if src == dst:
        raise AssetSourceError("Le dossier source des assets ne peut pas être le dossier de sortie.")
    if src == dst / "assets":
        raise AssetSourceError("Le dossier source des assets ne peut pas être le dossier assets/ de sortie.")
    if _is_relative_to(src, dst):
        raise AssetSourceError("Le dossier source des assets ne peut pas être situé dans le dossier de sortie.")
    if _is_relative_to(dst, src):
        raise AssetSourceError("Le dossier de sortie ne peut pas être situé dans le dossier source des assets.")
    return src


def ignored_reserved_asset_json(assets_dir: Optional[Path]) -> list[Path]:
    if not assets_dir:
        return []
    src = _resolve_path(assets_dir)
    return [src / name for name in sorted(RESERVED_ASSET_ROOT_JSON) if (src / name).is_file()]


def copy_assets_tree(assets_dir: Path, out_dir: Path) -> None:
    src_root = _resolve_path(assets_dir)
    dest_root = out_dir / "assets"
    dest_root.mkdir(parents=True, exist_ok=True)

    for src in src_root.rglob("*"):
        rel = src.relative_to(src_root)
        if rel.parts and rel.parts[0] == "assets":
            continue
        if len(rel.parts) == 1 and rel.name in RESERVED_ASSET_ROOT_JSON:
            continue
        dest = dest_root / rel
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        elif src.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def make_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()

    # options ONIX
    ap.add_argument("--export-onix", action="store_true", help="Générer un export ONIX 3.0")
    ap.add_argument("--onix-out", default=None, help="Chemin du fichier ONIX XML de sortie")
    ap.add_argument("--onix-report", default=None, help="Chemin du CSV de contrôle (erreurs/alertes)")
    ap.add_argument("--onix-strict", action="store_true", help="Mode strict (échec si champs requis manquants)")

    # --tableur : ancien nom de l'option, conservé comme alias ; les deux
    # formes alimentent la même destination args.excel.
    ap.add_argument("--excel", "--tableur", dest="excel", required=True,
                    help="Chemin du classeur Excel (--tableur est un ancien alias accepté)")
    ap.add_argument("--out", required=True, help="Dossier de sortie")
    ap.add_argument("--covers-dir", default="", help="Dossier contenant les couvertures (images)")
    ap.add_argument("--assets-dir", default="", help="Dossier source des assets à copier dans assets/")
    ap.add_argument("--validate-only", action="store_true", help="Ne génère que validation.csv + catalogue.json")
    ap.add_argument("--force", action="store_true",
                    help="Continuer la génération malgré les alertes de validation contournables")
    ap.add_argument("--new-months", type=int, default=None,
                    help="Fenêtre (en mois) pour les nouveautés (par défaut : valeur CONFIG.new_months)")

    ap.add_argument("--publish-ftp", action="store_true",
                    help="Publier le dossier de sortie en FTP/FTPS (selon CONFIG)")
    return ap


def main():
    args = make_arg_parser().parse_args()

    excel_path = Path(args.excel).expanduser().resolve()
    if not excel_path.exists():
        print(f"Fichier Excel introuvable : {excel_path}", file=sys.stderr)
        sys.exit(2)

    out_dir = Path(args.out).expanduser().resolve()

    covers_dir = Path(args.covers_dir).expanduser().resolve() if args.covers_dir else None
    assets_dir = Path(args.assets_dir).expanduser().resolve() if args.assets_dir else None

    # 1) build du site (sans publish ici)
    try:
        if assets_dir:
            for ignored in ignored_reserved_asset_json(assets_dir):
                print(
                    f"Avertissement : {ignored} est ignoré ; "
                    "catalogue.json et actualites.json sont générés à la racine du site.",
                    file=sys.stderr,
                )
        validation_report = build_site(
            excel_path=excel_path,
            out_dir=out_dir,
            covers_dir=covers_dir,
            assets_dir=assets_dir,
            validate_only=args.validate_only,
            new_months=args.new_months,
            publish=False,  # IMPORTANT
            force_alerts=args.force,
        )
        print(format_validation_summary(validation_report))
    except ValidationBlockingError as exc:
        print(format_validation_summary(exc.report), file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print("Génération interrompue : blocage technique non contournable.", file=sys.stderr)
        sys.exit(3)
    except ValidationAlertError as exc:
        print(format_validation_summary(exc.report), file=sys.stderr)
        for issue in exc.report.alerts:
            print("", file=sys.stderr)
            print(issue.code, file=sys.stderr)
            print(issue.message, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        report_path = out_dir / "validation.csv"
        if report_path.exists():
            print(f"Rapport écrit : {report_path}", file=sys.stderr)
        print("Relancez avec --force pour générer malgré ces alertes.", file=sys.stderr)
        sys.exit(4)
    except AssetSourceError as exc:
        print(f"Dossier des assets invalide : {exc}", file=sys.stderr)
        sys.exit(3)

    # 2) export ONIX (ICI)
    if args.export_onix:
        from export_onix_py import export_onix_from_excel  # même module que la GUI

        onix_out = args.onix_out or str(out_dir / "onix" / "purh_onix.xml")
        report = args.onix_report or str(out_dir / "onix" / "purh_onix_QA.csv")
        Path(onix_out).parent.mkdir(parents=True, exist_ok=True)
        Path(report).parent.mkdir(parents=True, exist_ok=True)

        export_onix_from_excel(
            excel_path=str(excel_path),
            out_xml_path=onix_out,
            strict=args.onix_strict,
            report_csv_path=report,
        )
        print(f"ONIX écrit : {onix_out}")
        print(f"QA écrit   : {report}")

    print(f"OK -> {out_dir}")
    print(f"- validation.csv : {out_dir / 'validation.csv'}")
    print(f"- catalogue.json : {out_dir / 'catalogue.json'}")

    # 3) publication FTP (après ONIX)
    if args.publish_ftp:
        wb = pd.ExcelFile(excel_path)
        cfg = load_config(wb, "CONFIG")
        if args.new_months is not None:
            cfg.new_months = int(args.new_months)
        publish_ftp(cfg, out_dir)
        print("FTP : publication terminée (si aucun message d'erreur).")


