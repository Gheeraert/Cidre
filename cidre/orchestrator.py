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
    build_pages, build_revues, build_upcoming_page, build_validation_report,
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
from .utils import as_str, compute_available_covers, months_ago, norm_bool, slugify

# -------------------------
# Orchestrator
# -------------------------

def build_site(excel_path: Path, out_dir: Path, covers_dir: Optional[Path],
               validate_only: bool = False, new_months: Optional[int] = None,
               progress_cb=None,
               publish: bool = False) -> None:
    wb = pd.ExcelFile(excel_path)

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

    # output dir reset (sélectif) :
    # - on conserve dist/assets/* (sauf les JSON régénérés)
    # - on conserve dist/covers/*
    # - on purge seulement les dossiers/pages générés
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Purger les dossiers générés (évite les pages orphelines)
    for dname in ("livres", "collections", "revues"):
        p = out_dir / dname
        if p.exists() and p.is_dir():
            shutil.rmtree(p)

    # 2) Purger les HTML générés à la racine (on les réécrit ensuite)
    root_html = {
        "index.html",
        "catalogue.html",
        "nouveautes.html",
        "a-paraitre.html",
        "actualites.html",
        "contact.html",
        "open-access.html",
        "open_access.html",
        "commander.html",
        "commandes.html",
        "presentation.html",
        "soumettre-un-manuscrit.html",
    }

    # + toutes les pages déclarées dans PAGES (sauf actualites/actus gérées ailleurs)
    if pages is not None and not pages.empty:
        for _, rr in pages.iterrows():
            slug = slugify(as_str(rr.get("slug"))) if as_str(rr.get("slug")) else ""
            if not slug or slug in {"actualites", "actus"}:
                continue
            root_html.add(f"{slug}.html")

    for fn in root_html:
        fp = out_dir / fn
        if fp.exists() and fp.is_file():
            fp.unlink()

    # 3) CSV générés
    val = out_dir / "validation.csv"
    if val.exists() and val.is_file():
        val.unlink()

    # 4) Assets : on garde tout, sauf les JSON régénérés
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    for json_name in ("catalogue.json", "actualites.json"):
        jp = assets_dir / json_name
        if jp.exists() and jp.is_file():
            jp.unlink()

    # 5) Covers : conservées
    (out_dir / "covers").mkdir(parents=True, exist_ok=True)

    # covers (copie d'abord pour savoir ce qui existe vraiment)
    if covers_dir:
        copy_covers(covers_dir, out_dir)

    # inventaire des covers réellement présentes dans dist/covers
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
    build_validation_report(books, out_dir)
    if validate_only:
        return

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

    if publish:
        publish_ftp(cfg, out_dir, progress_cb=progress_cb)


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
    ap.add_argument("--out", default="dist", help="Dossier de sortie")
    ap.add_argument("--covers-dir", default="", help="Dossier contenant les couvertures (images)")
    ap.add_argument("--validate-only", action="store_true", help="Ne génère que validation.csv + catalogue.json")
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
    out_dir.mkdir(parents=True, exist_ok=True)

    covers_dir = Path(args.covers_dir).expanduser().resolve() if args.covers_dir else None

    # 1) build du site (sans publish ici)
    build_site(
        excel_path=excel_path,
        out_dir=out_dir,
        covers_dir=covers_dir,
        validate_only=args.validate_only,
        new_months=args.new_months,
        publish=False,  # IMPORTANT
    )

    # 2) export ONIX (ICI)
    if args.export_onix:
        from export_onix_py import export_onix_from_excel  # même module que la GUI

        onix_out = args.onix_out or str(out_dir / "onix" / "purh_onix.xml")
        report = args.onix_report or str(out_dir / "onix" / "purh_onix_QA.csv")
        os.makedirs(str(Path(onix_out).parent), exist_ok=True)

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
    print(f"- catalogue.json : {out_dir / 'assets' / 'catalogue.json'}")

    # 3) publication FTP (après ONIX)
    if args.publish_ftp:
        wb = pd.ExcelFile(excel_path)
        cfg = load_config(wb, "CONFIG")
        if args.new_months is not None:
            cfg.new_months = int(args.new_months)
        publish_ftp(cfg, out_dir)
        print("FTP : publication terminée (si aucun message d'erreur).")


