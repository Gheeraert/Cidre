# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
# Module extrait de build_site.py (découpage sans changement fonctionnel).

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from . import utils
from .data_models import SiteConfig
from .default_assets import CARD_PAGE_SIZE, DEFAULT_JS, PROGRESSIVE_CARDS_JS
from .excel_data import get_social_links, render_social_strip, resolve_social_icon_source
from .html_templates import (
    book_order_block, book_retailers_block, order_pdf_rel, page_shell,
)
from .routes import (
    book_href, book_public_path, collection_href, collection_public_slug,
    editorial_page_public_path, editorial_page_slug, is_generated_editorial_page_slug,
    revue_href, revue_public_slug,
)
from .seo import (
    PageSeo, absolute_public_url, available_social_image_url, book_description,
    book_json_ld, clean_description, organization_json_ld, page_title,
    public_image_path, sitemap_xml, robots_txt, site_description, website_json_ld,
    normalize_site_url,
)
from .utils import (
    as_str, clean_json_value, e, fmt_display_date, md_to_html, norm_bool,
    render_contacts_block, resolve_asset_source, slugify, toc_to_html,
    write_file,
)
from .validation import validate_site_data, write_validation_csv

# -------------------------
# Build site
# -------------------------


def _generic_page_seo(cfg: SiteConfig, out_dir: Path, public_path: str,
                      description: str) -> PageSeo:
    image_url = available_social_image_url(cfg, out_dir)
    return PageSeo(
        description=clean_description(description),
        public_path=public_path,
        image_url=image_url,
        image_alt=f"Image de partage de {as_str(cfg.site_title)}" if image_url else "",
    )


def _home_page_seo(cfg: SiteConfig, out_dir: Path) -> PageSeo:
    logo_path = public_image_path(cfg.logo_left)
    logo_url = (
        absolute_public_url(cfg.site_url, logo_path)
        if logo_path and not logo_path.startswith(("http://", "https://")) and (out_dir / logo_path).is_file()
        else logo_path if logo_path.startswith(("http://", "https://")) else ""
    )
    organization = organization_json_ld(
        cfg,
        logo_url=logo_url,
        social_urls=[item["url"] for item in get_social_links(cfg)],
    )
    return PageSeo(
        description=site_description(cfg),
        public_path="index.html",
        image_url=available_social_image_url(cfg, out_dir),
        image_alt=f"Image de partage de {as_str(cfg.site_title)}",
        json_ld=[organization, website_json_ld(cfg, organization)],
    )


def build_seo_files(cfg: SiteConfig, out_dir: Path) -> None:
    """Écrit les fichiers SEO issus des pages réellement construites dans le staging."""
    site_url = normalize_site_url(cfg.site_url)
    sitemap_path = out_dir / "sitemap.xml"
    if site_url:
        html_paths = []
        for page in out_dir.rglob("*.html"):
            rel = page.relative_to(out_dir)
            if rel.parts and rel.parts[0] in {"assets", "covers"}:
                continue
            html_paths.append(rel.as_posix())
        write_file(sitemap_path, sitemap_xml(site_url, html_paths))
    elif sitemap_path.exists():
        sitemap_path.unlink()
    write_file(out_dir / "robots.txt", robots_txt(site_url))

def copy_covers(covers_dir: Path, out_dir: Path) -> None:
    if not covers_dir.exists():
        return

    dest_dir = out_dir / "covers"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for src in covers_dir.iterdir():
        if not (src.is_file() and src.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}):
            continue

        dst = dest_dir / src.name

        # ✅ Skip si déjà présent et pas plus récent / pas différent
        if dst.exists():
            try:
                same_size = dst.stat().st_size == src.stat().st_size
                dst_newer_or_equal = dst.stat().st_mtime >= src.stat().st_mtime
                if same_size and dst_newer_or_equal:
                    continue
            except Exception:
                pass

        shutil.copy2(src, dst)


def copy_declared_assets(excel_path: Path, out_dir: Path, cfg: SiteConfig) -> None:
    """
    Copie les assets déclarés dans CONFIG vers assets/.
    Règle :
      - on ne supprime jamais assets/*
      - on ne remplace un fichier existant que si la source semble "plus récente" ou différente
        (même logique que copy_covers).
    """
    excel_dir = excel_path.parent
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)

    declared = [cfg.logo_left, cfg.logo_right, cfg.favicon, cfg.footer_logo]
    social_image = public_image_path(cfg.social_image)
    if social_image and not social_image.startswith(("http://", "https://")):
        declared.append(social_image)
    if cfg.order_mode == "pdf" and cfg.order_pdf_filename:
        # Toujours sous assets/, pour correspondre au lien ../assets/<rel>
        declared.append(f"assets/{order_pdf_rel(cfg.order_pdf_filename)}")

    for rel in declared:
        rel = as_str(rel)
        if not rel:
            continue

        src = resolve_asset_source(excel_dir, rel)
        if not src:
            continue

        dest = out_dir / rel.replace("\\", "/")
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            try:
                same_size = dest.stat().st_size == src.stat().st_size
                dest_newer_or_equal = dest.stat().st_mtime >= src.stat().st_mtime
                if same_size and dest_newer_or_equal:
                    continue
            except Exception:
                pass

        shutil.copy2(src, dest)

    # Icônes des réseaux / liens institutionnels (assets/social/*.svg, etc.)
    for i in range(1, 7):
        icon_spec = as_str(getattr(cfg, f"social_{i}_icon", ""))
        if not icon_spec:
            continue

        src = resolve_social_icon_source(excel_dir, icon_spec)
        if not src:
            continue

        dest = out_dir / "assets" / "social" / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            try:
                same_size = dest.stat().st_size == src.stat().st_size
                dest_newer_or_equal = dest.stat().st_mtime >= src.stat().st_mtime
                if same_size and dest_newer_or_equal:
                    continue
            except Exception:
                pass

        shutil.copy2(src, dest)

def _catalogue_year_value(value: Any) -> str:
    """Valeur d'année commune au JSON et aux filtres du catalogue."""
    if value is None or pd.isna(value):
        return ""
    try:
        return str(int(float(value)))
    except Exception:
        return str(value).strip()


def build_catalogue_json(books: pd.DataFrame, out_dir: Path) -> None:
    recs = []
    for _, r in books.iterrows():
        # Année: garantir une valeur lisible (éviter '2025.0')
        year_str = _catalogue_year_value(r.get("year"))

        # COVER: ne publier que si le fichier existe vraiment dans covers/
        cover = as_str(r.get("cover_file"))
        cover = Path(cover.replace("\\", "/")).name if cover else ""
        if cover and cover not in utils.AVAILABLE_COVERS:
            cover = ""

        recs.append({
            "id13": clean_json_value(r.get("id13")) or "",
            "slug": clean_json_value(r.get("slug")) or "",
            "title": clean_json_value(r.get("titre_norm")) or "",
            "subtitle": clean_json_value(r.get("sous_titre_norm")) or "",
            "credit": clean_json_value(r.get("credit_ligne")) or "",
            "collection": clean_json_value(r.get("collection")) or "",
            "collection_id": clean_json_value(r.get("collection_id")) or "",
            "format": clean_json_value(r.get("format_site")) or "",
            "year": year_str,
            "price": clean_json_value(r.get("price_str")) or "",
            "currency": clean_json_value(r.get("currency_str")) or "",
            "availability": clean_json_value(r.get("availability_label")) or "",
            "physical": clean_json_value(r.get("physical_str")) or "",
            "cover": cover,  # ✅ ici
            "excerpt": clean_json_value(r.get("excerpt")) or "",
            "order_url": clean_json_value(r.get("order_url")) or "",
            "openedition_url": clean_json_value(r.get("openedition_url")) or "",
        })

    (out_dir / "catalogue.json").write_text(
        json.dumps(recs, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8"
    )



def _book_card_html(r: pd.Series, rel_prefix: str, cfg: SiteConfig,
                    extra_classes: str = "",
                    data_attributes: Optional[Dict[str, str]] = None,
                    lazy_cover: bool = False,
                    show_excerpt: bool = False,
                    available_covers: Optional[set[str]] = None) -> str:
    cover = as_str(r.get("cover_file")).strip()

    if cover:
        cover = cover.replace("\\", "/").split("/")[-1]  # basename sûr
        if available_covers is not None and cover not in available_covers:
            cover = ""

    if cover:
        cover_url = f"{rel_prefix}/covers/{e(cover)}"  # PAS de replace()

        image_loading = ' loading="lazy" decoding="async"' if lazy_cover else ""
        cover_html = (
            f"<a href='#' class='cover-zoom' data-lightbox-src='{cover_url}'>"
            f"<img class='cover' style='width:180px;height:auto' src='{cover_url}' alt=''"
            f"{image_loading} onerror=\"this.style.display='none'\">"
            f"</a>"
        )
    else:
        cover_html = ""

    subtitle = as_str(r.get("sous_titre_norm"))
    credit = as_str(r.get("credit_ligne"))
    collection = as_str(r.get("collection"))
    fmt = as_str(r.get("format_site"))
    year = as_str(r.get("year"))

    price = as_str(r.get("price_str"))
    avail = as_str(r.get("availability_label"))
    physical = as_str(r.get("physical_str"))
    datep = fmt_display_date(r.get("date_parution_norm"))
    oe_url = as_str(r.get("openedition_url"))
    subtitle_html = f"<div class='book-subtitle'>{e(subtitle)}</div>" if subtitle else ""
    credit_html = f'<div class="book-credit">{e(credit)}</div>' if credit else ""

    date_html = f'<div class="small">Parution : {e(datep)}</div>' if datep else ""

    badges = []
    if collection:
        badges.append(f'<span class="badge">{e(collection)}</span>')
    if fmt:
        badges.append(f'<span class="badge">{e(fmt)}</span>')
    if oe_url:
        badges.append(
            f"<a class='badge badge-oa' href='{e(oe_url)}' target='_blank' rel='noopener'>Accès ouvert</a>"
        )
    # if year:
    #     badges.append(f'<span class="badge">{e(year)}</span>')
    badge_html = f'<div class="badges">{"".join(badges)}</div>' if badges else ""

    price_html = f'<div class="small">Prix : {e(price)}</div>' if (cfg.show_price and price) else ""
    avail_html = f'<div class="small">{e(avail)}</div>' if (cfg.show_availability and avail) else ""
    physical_html = f'<div class="small">{e(physical)}</div>' if physical else ""
    excerpt = as_str(r.get("excerpt"))
    excerpt_html = f'<div class="small">{e(excerpt)}</div>' if (show_excerpt and excerpt) else ""

    classes = "card"
    if extra_classes:
        classes = f"{classes} {extra_classes}"
    attrs = "".join(
        f' {name}="{e(value)}"'
        for name, value in (data_attributes or {}).items()
    )

    return f"""
<div class="{e(classes)}"{attrs}>
  {cover_html}
  <div class="meta">
    <a href="{e(book_href(r.get('slug'), rel_prefix))}"><strong>{e(r.get('titre_norm'))}</strong></a>
    {subtitle_html}
    {credit_html}
    {badge_html}
    {date_html}
    {price_html}{avail_html}{physical_html}{excerpt_html}
  </div>
</div>
""".strip()


def _progressive_cards_html(cards: List[str], empty_message: str) -> str:
    """Grille de cartes avec révélation progressive par lots de CARD_PAGE_SIZE.

    Toutes les cartes sont présentes dans le HTML (lisibles sans JS) ; le
    script ne fait que masquer celles au-delà du premier lot et révéler les
    suivantes via le bouton « Afficher plus ». Jusqu'à CARD_PAGE_SIZE cartes,
    ni bouton ni script ne sont émis.
    """
    if not cards:
        return f"<p class='small'>{e(empty_message)}</p>"
    grid = f"<div class='grid progressive-card-grid'>{chr(10).join(cards)}</div>"
    if len(cards) <= CARD_PAGE_SIZE:
        return grid
    return (
        f"{grid}\n"
        "<p class='progressive-card-actions'>"
        "<button type='button' class='btn progressive-card-more' hidden>Afficher plus</button>"
        "</p>\n"
        f"<script>{PROGRESSIVE_CARDS_JS}</script>"
    )


def build_home(cfg: SiteConfig, books: pd.DataFrame, out_dir: Path) -> None:
    df = books.copy()
    social_html = render_social_strip(cfg, out_dir)

    def date_sort_key(x: Any) -> datetime:
        s = as_str(x)
        if not s:
            return datetime.min
        try:
            return datetime.fromisoformat(s)
        except Exception:
            m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", s)
            if m:
                y = int(m.group(1))
                mo = int(m.group(2) or 1)
                d = int(m.group(3) or 1)
                return datetime(y, mo, d)
            return datetime.min

    df["_ds"] = df["date_parution_norm"].apply(date_sort_key)
    df["_feat"] = df["home_featured"].apply(norm_bool) if "home_featured" in df.columns else False
    df = df.sort_values(["_feat", "_ds"], ascending=[False, False]).head(cfg.home_feature_count)

    cards = [_book_card_html(r, ".", cfg) for _, r in df.iterrows()]
    body = f"""
{social_html}
    <h1>Nouveautés</h1>
<p class="small">Nos parutions récentes</p>
<div class="grid">
{chr(10).join(cards)}
</div>
<p style="margin-top:16px">
  <a class="btn" href="./catalogue.html">Voir tout le catalogue</a>
  <a class="btn" href="./nouveautes.html">Voir les nouveautés</a>
</p>
"""
    write_file(out_dir / "index.html", page_shell(
        cfg, page_title(cfg, home=True), "home", body, ".", seo=_home_page_seo(cfg, out_dir)))

def _catalogue_options(values: List[str], placeholder: str) -> str:
    options = [f'<option value="">{e(placeholder)}</option>']
    options.extend(f'<option value="{e(value)}">{e(value)}</option>' for value in values)
    return "\n  ".join(options)


def _catalogue_card_data(row: pd.Series) -> Dict[str, str]:
    collection = as_str(row.get("collection"))
    fmt = as_str(row.get("format_site"))
    year = _catalogue_year_value(row.get("year"))
    search_text = " ".join([
        as_str(row.get("titre_norm")),
        as_str(row.get("sous_titre_norm")),
        as_str(row.get("credit_ligne")),
        as_str(row.get("id13")),
        collection,
        fmt,
    ])
    return {
        "data-collection": collection,
        "data-format": fmt,
        "data-year": year,
        "data-search": search_text,
    }


def _catalogue_year_sort_key(year: str) -> tuple[int, Any]:
    try:
        return (1, int(year))
    except (TypeError, ValueError):
        return (0, year.casefold())


def build_catalogue_page(cfg: SiteConfig, books: pd.DataFrame, out_dir: Path) -> None:
    available_covers = utils.compute_available_covers(out_dir)
    cards = [
        _book_card_html(
            row, ".", cfg,
            extra_classes="catalogue-card",
            data_attributes=_catalogue_card_data(row),
            lazy_cover=True,
            show_excerpt=True,
            available_covers=available_covers,
        )
        for _, row in books.iterrows()
    ]
    collections = sorted(
        {as_str(row.get("collection")) for _, row in books.iterrows() if as_str(row.get("collection"))},
        key=str.casefold,
    )
    formats = sorted(
        {as_str(row.get("format_site")) for _, row in books.iterrows() if as_str(row.get("format_site"))},
        key=str.casefold,
    )
    years = sorted(
        {_catalogue_year_value(row.get("year")) for _, row in books.iterrows() if _catalogue_year_value(row.get("year"))},
        key=_catalogue_year_sort_key,
        reverse=True,
    )
    empty_hidden = " hidden" if cards else ""
    body = f"""
<h1>{e(cfg.menu_label_catalogue)}</h1>
<p class="small">Recherche par titre, auteur, ISBN, collection ou format, avec filtres par collection, format et année.</p>

<div id="catalogue-toolbar" class="toolbar" hidden>
  <input id="q" type="search" placeholder="Rechercher par titre, auteur, ISBN, collection ou format…">
  <select id="f_collection">
  {_catalogue_options(collections, "Toutes les collections")}
  </select>
  <select id="f_format">
  {_catalogue_options(formats, "Tous les formats")}
  </select>
  <select id="f_year">
  {_catalogue_options(years, "Toutes les années")}
  </select>
</div>

<p class="small"><span id="count">{len(cards)}</span> résultat(s)</p>
<div id="out" class="grid">
{chr(10).join(cards)}
</div>
<p id="catalogue-empty" class="small"{empty_hidden}>Aucun résultat.</p>
<p style="margin-top:12px">
  <button type="button" id="more" class="btn" hidden>Afficher plus</button>
</p>
<script>{DEFAULT_JS}</script>
"""
    write_file(out_dir / "catalogue.html",
                page_shell(cfg, page_title(cfg, cfg.menu_label_catalogue), "catalogue", body, ".",
                           seo=_generic_page_seo(
                               cfg, out_dir, "catalogue.html",
                               "Catalogue des ouvrages publiés par " + as_str(cfg.site_title),
                           )))


def build_new_titles(cfg: SiteConfig, recent: pd.DataFrame, out_dir: Path, new_months: int) -> None:
    df = recent.copy()

    if df.empty:
        body = f"""
<h1>Nouveautés</h1>
<p class="small">Aucun titre paru dans les {int(new_months)} derniers mois.</p>
"""
        write_file(out_dir / "nouveautes.html",
                   page_shell(cfg, page_title(cfg, "Nouveautés"), "nouveautes", body, ".",
                              seo=_generic_page_seo(cfg, out_dir, "nouveautes.html", "Nouveautés de " + as_str(cfg.site_title))))
        return

    if "pub_date" in df.columns:
        df = df.sort_values("pub_date", ascending=False)

    df = df.head(cfg.new_titles_count)

    # Affichage en vignettes, comme l'accueil
    cards = [_book_card_html(r, ".", cfg) for _, r in df.iterrows()]
    body = f"""
<h1>Nouveautés</h1>
<p class="small">Titres parus dans les {int(new_months)} derniers mois.</p>
<div class="grid">
{chr(10).join(cards)}
</div>
"""
    write_file(out_dir / "nouveautes.html", page_shell(
        cfg, page_title(cfg, "Nouveautés"), "nouveautes", body, ".",
        seo=_generic_page_seo(cfg, out_dir, "nouveautes.html", "Nouveautés de " + as_str(cfg.site_title))))


def build_upcoming_page(cfg: SiteConfig, upcoming: pd.DataFrame, out_dir: Path) -> None:
    title = cfg.menu_label_a_paraitre

    if upcoming.empty:
        body = f"""
<h1>{e(title)}</h1>
<p class="small">Aucun titre “à paraître” détecté.</p>
"""
        write_file(out_dir / "a-paraitre.html", page_shell(
            cfg, page_title(cfg, title), "a_paraitre", body, ".",
            seo=_generic_page_seo(cfg, out_dir, "a-paraitre.html", "Ouvrages à paraître chez " + as_str(cfg.site_title))))
        return

    df = upcoming.copy()

    def sort_key(d):
        return d if isinstance(d, date) else date.max

    if "pub_date" in df.columns:
        df["_k"] = df["pub_date"].apply(sort_key)
        df = df.sort_values("_k", ascending=True)
    else:
        df = df.sort_values("date_parution_norm", ascending=True)

    cards = [_book_card_html(r, ".", cfg) for _, r in df.iterrows()]

    body = f"""
<h1>{e(title)}</h1>
<p class="small">Prochainement en librairie !</p>
<div class="grid">
{chr(10).join(cards)}
</div>
"""
    write_file(out_dir / "a-paraitre.html", page_shell(
        cfg, page_title(cfg, title), "a_paraitre", body, ".",
        seo=_generic_page_seo(cfg, out_dir, "a-paraitre.html", "Ouvrages à paraître chez " + as_str(cfg.site_title))))


def build_book_pages(cfg: SiteConfig, books: pd.DataFrame, out_dir: Path,
                     revue_slugs: Optional[Dict[str, str]] = None,
                     collection_slugs: Optional[Dict[str, str]] = None) -> None:
    livres_dir = out_dir / "livres"
    livres_dir.mkdir(parents=True, exist_ok=True)
    available_covers = utils.compute_available_covers(out_dir)

    for _, r in books.iterrows():
        title = as_str(r.get("titre_norm"))
        subtitle = as_str(r.get("sous_titre_norm"))
        credit = as_str(r.get("credit_ligne"))
        collection = as_str(r.get("collection"))
        fmt = as_str(r.get("format_site"))
        datep = fmt_display_date(r.get("date_parution_norm"))
        id13 = as_str(r.get("id13"))
        oe_url = as_str(r.get("openedition_url"))
        cover = as_str(r.get("cover_file"))
        price = as_str(r.get("price_str"))
        avail = as_str(r.get("availability_label"))
        physical = as_str(r.get("physical_str"))

        desc = as_str(r.get("Description longue") or r.get("Description courte"))
        toc = as_str(r.get("Table des matières"))

        cover = Path(cover.replace("\\", "/")).name if cover else ""
        if cover not in available_covers:
            cover = ""
        cover_html = (
            f"<a href='#' class='cover-zoom' data-lightbox-src='../covers/{e(cover)}'>"
            f"<img class='cover' style='width:180px;height:auto' src='../covers/{e(cover)}' "
            f"alt='{e(f'Couverture de {title}')}' loading='lazy' decoding='async'>"
            f"</a>"
        ) if cover else ""
        collection_id = as_str(r.get("collection_id"))
        badges = []

        # ✅ Collection cliquable (si on a collection_id)
        if collection and collection_id:
            if revue_slugs is not None and collection_id in revue_slugs:
                # Numéro de revue : la page est générée sous revues/<slug>.html
                rslug = revue_slugs[collection_id]
                if rslug:
                    badges.append(
                        f"<a class='badge' href='{e(revue_href(rslug, rel_prefix='..'))}'>"
                        f"{e(collection)}</a>"
                    )
                else:
                    # revue inactive : pas de page générée, badge sans lien
                    badges.append(f"<span class='badge'>{e(collection)}</span>")
            elif collection_slugs is not None:
                # Collection : lien vers la page réellement générée
                cslug = collection_slugs.get(collection_id)
                if cslug:
                    badges.append(
                        f"<a class='badge' href='{e(collection_href(cslug, rel_prefix='..'))}'>"
                        f"{e(collection)}</a>"
                    )
                else:
                    # collection inactive ou identifiant inconnu : pas de page
                    # générée, badge sans lien plutôt qu'une URL 404
                    badges.append(f"<span class='badge'>{e(collection)}</span>")
            else:
                # appel historique sans mapping : lien fondé sur l'identifiant
                badges.append(
                    f"<a class='badge' href='{e(collection_href(collection_id, rel_prefix='..'))}'>"
                    f"{e(collection)}</a>"
                )
        elif collection:
            badges.append(f"<span class='badge'>{e(collection)}</span>")

        if fmt:
            badges.append(f"<span class='badge'>{e(fmt)}</span>")

        # Badge OpenEdition cliquable (déjà OK chez toi)
        if oe_url:
            badges.append(
                f"<a class='badge badge-oa' href='{e(oe_url)}' target='_blank' rel='noopener'>Accès ouvert</a>"
            )

        badge_html = f"<div class='badges'>{''.join(badges)}</div>" if badges else ""

        # Bloc "métadonnées" (libellés en gras, valeurs normales)
        meta_lines = []
        if id13:
            meta_lines.append(f"<div class='meta-line'><span class='meta-label'>ISBN/GTIN :</span> {e(id13)}</div>")
        if datep:
            meta_lines.append(
                f"<div class='meta-line'><span class='meta-label'>Date de parution :</span> {e(datep)}</div>")
        if cfg.show_price and price:
            meta_lines.append(f"<div class='meta-line'><span class='meta-label'>Prix :</span> {e(price)}</div>")
        if cfg.show_availability and avail:
            meta_lines.append(
                f"<div class='meta-line'><span class='meta-label'>Disponibilité :</span> {e(avail)}</div>")
        if physical:
            meta_lines.append(
                f"<div class='meta-line'><span class='meta-label'>Description matérielle :</span> {e(physical)}</div>")

        meta_html = f"<div class='book-meta'>{''.join(meta_lines)}</div>" if meta_lines else ""

        retailers_html = book_retailers_block(id13, oe_url)

        order_block = book_order_block(cfg, {"title": title, "id13": id13, "order_url": as_str(r.get("order_url"))})

        desc_html = f"<h2 class='section-heading'>Présentation</h2>{md_to_html(desc)}" if desc else ""
        toc_block = toc_to_html(toc)
        toc_html = f"<h2 class='section-heading'>Table des matières</h2>{toc_block}" if toc_block else ""

        body = f"""
<div style="display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap">
  <div>{cover_html}</div>
  <div style="min-width:260px;flex:1">
    <h1>{e(title)}</h1>
    {f"<div class='book-subtitle'>{e(subtitle)}</div>" if subtitle else ""}
    {f"<div class='book-credit'>{e(credit)}</div>" if credit else ""}
    {badge_html}
    {meta_html}
    {retailers_html}
    {order_block}
  </div>
</div>
<hr>
{desc_html}
{toc_html}
"""
        public_path = book_public_path(r.get("slug"))
        image_url = absolute_public_url(cfg.site_url, f"covers/{cover}") if cover else ""
        part_of = None
        if collection and collection_id:
            if revue_slugs is not None and revue_slugs.get(collection_id):
                part_of = {"@type": "Periodical", "name": collection}
            elif collection_slugs is not None and collection_slugs.get(collection_id):
                part_of = {"@type": "CreativeWorkSeries", "name": collection}
        description = book_description(r)
        seo = PageSeo(
            description=description,
            public_path=public_path,
            og_type="book",
            image_url=image_url or available_social_image_url(cfg, out_dir),
            image_alt=(f"Couverture de {title}" if image_url else f"Image de partage de {as_str(cfg.site_title)}"),
            json_ld=[book_json_ld(cfg, r, public_path=public_path, description=description,
                                  image_url=image_url, part_of=part_of)],
        )
        write_file(out_dir / public_path,
                   page_shell(cfg, page_title(cfg, title), "catalogue", body, "..", seo=seo))


def build_collections(cfg: SiteConfig, books: pd.DataFrame, collections: pd.DataFrame, out_dir: Path) -> None:
    base = out_dir / "collections"
    base.mkdir(parents=True, exist_ok=True)

    if collections.empty:
        names = sorted({as_str(x) for x in books["collection"].dropna().tolist() if as_str(x)})
        rows = []
        for n in names:
            cid = slugify(n)
            rows.append({"collection_id": cid, "name": n, "slug": cid, "description_md": "", "directeurs": "",
                         "comite_scientifique": "", "is_active": 1})
        collections = pd.DataFrame(rows)

    collections = collections.copy()
    collections["is_active"] = collections.get("is_active", 1).apply(norm_bool)
    collections["collection_id"] = collections["collection_id"].apply(
        lambda x: slugify(as_str(x)) if as_str(x) else None)
    collections["slug"] = collections["slug"].apply(lambda x: slugify(as_str(x)) if as_str(x) else None)
    collections["name"] = collections["name"].apply(lambda x: as_str(x))

    collections = collections[collections["is_active"]].copy().sort_values("name")

    lis = []
    for _, c in collections.iterrows():
        public_slug = collection_public_slug(c.get("slug"), c.get("collection_id"))
        lis.append(f'<li><a href="./{e(public_slug)}.html">{e(c.get("name"))}</a></li>')
    body = f"""
<h1>{e(cfg.menu_label_collections)}</h1>
<p class="small">Nos collections.</p>
<ul>
{chr(10).join(lis)}
</ul>
"""
    write_file(base / "index.html", page_shell(
        cfg, page_title(cfg, "Collections"), "collections", body, "..",
        seo=_generic_page_seo(cfg, out_dir, "collections/index.html", "Collections de " + as_str(cfg.site_title))))

    for _, c in collections.iterrows():
        cid = as_str(c.get("collection_id") or c.get("slug"))
        name = as_str(c.get("name"))
        desc = md_to_html(c.get("description_md") or "")
        directeurs = as_str(c.get("directeurs"))
        comite = as_str(c.get("comite_scientifique"))
        issn_print = as_str(c.get("issn_print"))

        dfb = books.copy()
        if "collection_id" in dfb.columns and cid:
            dfb = dfb[dfb["collection_id"] == cid]
        else:
            dfb = dfb[dfb["collection"] == name]

        dfb = dfb.sort_values(["year", "titre_norm"], ascending=[False, True])

        cards = [_book_card_html(r, "..", cfg) for _, r in dfb.iterrows()]
        cards_html = _progressive_cards_html(
            cards, "Aucun ouvrage rattaché trouvé (vérifier collection_id dans le catalogue).")

        meta = []
        if issn_print:
            meta.append(f"<div class='kv'><div class='k'>ISSN</div><div>{e(issn_print)}</div></div>")
        if directeurs:
            meta.append(f"<div class='kv'><div class='k'>Direction</div><div>{e(directeurs)}</div></div>")
        if comite:
            meta.append(f"<div class='kv'><div class='k'>Comité scientifique</div><div>{e(comite)}</div></div>")

        # --- LOGIQUE DEPLIER / REPLIER ---
        issn_line = f"<div class='small collection-issn'>ISSN : {e(issn_print)}</div>" if issn_print else ""
        desc_block = ""
        if desc:
            # On compte la longueur brute du HTML pour décider si on coupe
            # Seuil à 600 caractères (ajustable selon tes préférences)
            is_long = len(desc) > 600

            css_cls = "collection-desc clamped" if is_long else "collection-desc"
            btn_html = ""

            if is_long:
                # Le script JS est directement dans l'attribut onclick pour éviter de charger du JS externe
                btn_html = """
                <button class="desc-toggle" onclick="
                  var d = this.previousElementSibling;
                  d.classList.toggle('clamped');
                  this.textContent = d.classList.contains('clamped') ? 'Lire la suite' : 'Replier';
                ">Lire la suite</button>
                """

            desc_block = f"<div class='{css_cls}'>{desc}</div>{btn_html}"
        # ---------------------------------

        body = f"""
        <h1>{e(name)}</h1>
        {issn_line}
        {desc_block}
        {''.join(meta)}
        <h2 class='section-heading'>Ouvrages rattachés</h2>
        {cards_html}
        """
        slug = collection_public_slug(c.get("slug"), cid)
        public_path = f"collections/{slug}.html"
        description = clean_description(c.get("description_md")) or clean_description(
            f"Collection {name} des {as_str(cfg.site_title)}")
        write_file(base / f"{slug}.html", page_shell(
            cfg, page_title(cfg, name), "collections", body, "..",
            seo=_generic_page_seo(cfg, out_dir, public_path, description)))

def build_revues(cfg: SiteConfig, books: pd.DataFrame, revues: pd.DataFrame, out_dir: Path) -> None:
    base = out_dir / "revues"
    base.mkdir(parents=True, exist_ok=True)
    if revues.empty:
        body = f"""
<h1>{e(cfg.menu_label_revues)}</h1>
<p class="small">Aucune revue renseignée dans l’onglet REVUES.</p>
"""
        write_file(base / "index.html", page_shell(
            cfg, page_title(cfg, "Revues"), "revues", body, "..",
            seo=_generic_page_seo(cfg, out_dir, "revues/index.html", "Revues de " + as_str(cfg.site_title))))
        return

    df = revues.copy()
    df["is_active"] = df.get("is_active", 1).apply(norm_bool)
    df = df[df["is_active"]].copy()
    df["title"] = df.get("title", "").apply(as_str)
    df["journal_id"] = df.get("journal_id", "").apply(as_str)
    df["slug"] = df.apply(
        lambda r: revue_public_slug(r.get("slug"), r.get("title"), r.get("journal_id")),
        axis=1
    )
    df["order"] = pd.to_numeric(df.get("order"), errors="coerce")
    df["_sort_title"] = df["title"].str.lower()
    df = df.sort_values(by=["order", "_sort_title"], na_position="last")

    lis = []
    for _, r in df.iterrows():
        title = as_str(r.get("title")) or as_str(r.get("journal_id")) or "Revue"
        lis.append(f'<li><a href="./{e(r.get("slug"))}.html">{e(title)}</a></li>')
    body = f"""
<h1>{e(cfg.menu_label_revues)}</h1>
<ul>
{chr(10).join(lis)}
</ul>
"""
    write_file(base / "index.html", page_shell(
        cfg, page_title(cfg, "Revues"), "revues", body, "..",
        seo=_generic_page_seo(cfg, out_dir, "revues/index.html", "Revues de " + as_str(cfg.site_title))))

    for _, r in df.iterrows():
        title = as_str(r.get("title")) or as_str(r.get("journal_id")) or "Revue"
        url = as_str(r.get("url"))
        issnp = as_str(r.get("issn_print"))
        issno = as_str(r.get("issn_online"))
        direction = as_str(r.get("direction"))
        comite = as_str(r.get("comite_scientifique"))
        mail = as_str(r.get("contact_email"))
        desc = md_to_html(r.get("description_md") or "")

        meta = []
        if url:
            meta.append(
                f"<div class='kv'><div class='k'>Site</div><div><a href='{e(url)}' target='_blank' rel='noopener'>{e(url)}</a></div></div>")
        if issnp:
            meta.append(f"<div class='kv'><div class='k'>ISSN (papier)</div><div>{e(issnp)}</div></div>")
        if issno:
            meta.append(f"<div class='kv'><div class='k'>ISSN (en ligne)</div><div>{e(issno)}</div></div>")
        if direction:
            meta.append(f"<div class='kv'><div class='k'>Direction</div><div>{e(direction)}</div></div>")
        if comite:
            meta.append(f"<div class='kv'><div class='k'>Comité scientifique</div><div>{e(comite)}</div></div>")
        if mail:
            meta.append(
                f"<div class='kv'><div class='k'>Contact</div><div><a href='mailto:{e(mail)}'>{e(mail)}</a></div></div>")

        # Numéros rattachés : même mécanisme que les badges des fiches livres
        # (collection_id du livre == journal_id slugifié de la revue).
        jid = slugify(as_str(r.get("journal_id")))
        if jid and "collection_id" in books.columns:
            dfb = books[books["collection_id"] == jid].copy()
        else:
            dfb = books.iloc[0:0].copy()
        dfb = dfb.sort_values(["year", "titre_norm"], ascending=[False, True])

        cards = [_book_card_html(b, "..", cfg) for _, b in dfb.iterrows()]
        cards_html = _progressive_cards_html(cards, "Aucun numéro rattaché trouvé.")

        body = f"""
<h1>{e(title)}</h1>
{''.join(meta)}
{desc if desc else ""}
<h2 class='section-heading'>Numéros parus</h2>
{cards_html}
"""
        slug = revue_public_slug(r.get('slug'), r.get('title'), r.get('journal_id'))
        public_path = f"revues/{slug}.html"
        description = clean_description(r.get("description_md")) or clean_description(
            f"Revue {title} des {as_str(cfg.site_title)}")
        write_file(base / f"{slug}.html", page_shell(
            cfg, page_title(cfg, title), "revues", body, "..",
            seo=_generic_page_seo(cfg, out_dir, public_path, description)))


def build_contacts(cfg: SiteConfig, contacts: pd.DataFrame, out_dir: Path) -> None:
    cards = []
    if not contacts.empty:
        df = contacts.copy()
        df["is_active"] = df.get("is_active", 1).apply(norm_bool)
        df = df[df["is_active"]].copy()
        if "order" in df.columns:
            df = df.sort_values("order")
        for _, r in df.iterrows():
            label = as_str(r.get("label"))
            name = as_str(r.get("name"))
            role = as_str(r.get("role"))
            email_ = as_str(r.get("email"))
            phone = as_str(r.get("phone"))
            addr = as_str(r.get("address"))
            lines = []
            if name:
                lines.append(f"<div><strong>{e(name)}</strong></div>")
            if role:
                lines.append(f"<div class='small'>{e(role)}</div>")
            if email_:
                lines.append(f"<div class='small'><a href='mailto:{e(email_)}'>{e(email_)}</a></div>")
            if phone:
                lines.append(f"<div class='small'>{e(phone)}</div>")
            if addr:
                lines.append(f"<div class='small'>{e(addr)}</div>")
            cards.append(
                f"<div class='card'><div class='meta'><div class='badge'>{e(label)}</div>{''.join(lines)}</div></div>")

    if not cards:
        body = "<h1>Contact</h1><p class='small'>Aucun contact renseigné.</p>"
    else:
        body = f"<h1>Contact</h1><p class='small'>Planche de contacts (générée depuis l’Excel).</p><div class='grid'>{''.join(cards)}</div>"

    write_file(out_dir / "contact.html", page_shell(
        cfg, page_title(cfg, "Contact"), "contact", body, ".",
        seo=_generic_page_seo(cfg, out_dir, "contact.html", "Contact de " + as_str(cfg.site_title))))


def build_pages(cfg: SiteConfig, pages: pd.DataFrame, contacts: pd.DataFrame, out_dir: Path) -> None:
    if pages.empty:
        for slug, title, key in [("open-access", cfg.menu_label_open_access, "open_access"),
                                 ("actualites", cfg.menu_label_actualites, "actualites")]:
            body = f"<h1>{e(title)}</h1><p class='small'>Page non renseignée dans l’onglet PAGES.</p>"
            write_file(out_dir / f"{slug}.html", page_shell(
                cfg, page_title(cfg, title), key, body, ".",
                seo=_generic_page_seo(cfg, out_dir, f"{slug}.html", title)))
        return

    df = pages.copy()
    if "is_published" in df.columns:
        df["is_published"] = df["is_published"].apply(norm_bool)
        df = df[df["is_published"]].copy()

    for _, r in df.iterrows():
        slug = editorial_page_slug(r.get("slug"))
        if not is_generated_editorial_page_slug(slug):
            continue
        title = as_str(r.get("title") or slug)
        content = md_to_html(r.get("content_md") or "")
        empty = "<p class='small'>(contenu vide)</p>"
        body = f"<h1>{e(title)}</h1>{content if content else empty}"
        KEY_BY_SLUG = {
            "presentation": "presentation",
            "soumettre-un-manuscrit": "soumettre",
            "open-access": "open_access",
            "open_access": "open_access",
            "commander": "commandes",
            "commandes": "commandes",
            "actualites": "actualites",
            "actus": "actualites",
        }

        key = KEY_BY_SLUG.get(slug, "home")

        if slug in {"commander", "commandes"}:
            body += "<hr>\n" + render_contacts_block(contacts, heading="Nous contacter")

        public_path = editorial_page_public_path(slug)
        description = clean_description(r.get("content_md")) or clean_description(title)
        write_file(out_dir / public_path, page_shell(
            cfg, page_title(cfg, title), key, body, ".",
            seo=_generic_page_seo(cfg, out_dir, public_path, description)))

    for slug, title, key in [("open-access", cfg.menu_label_open_access, "open_access")]:
        if not (out_dir / editorial_page_public_path(slug)).exists():
            body = f"<h1>{e(title)}</h1><p class='small'>Page non renseignée dans l’onglet PAGES.</p>"
            public_path = editorial_page_public_path(slug)
            write_file(out_dir / public_path, page_shell(
                cfg, page_title(cfg, title), key, body, ".",
                seo=_generic_page_seo(cfg, out_dir, public_path, title)))

def build_validation_report(books: pd.DataFrame, out_dir: Path) -> None:
    """Facade historique : ecrit validation.csv depuis le moteur structure."""
    report = validate_site_data(books=books, out_dir=out_dir)
    write_validation_csv(report, out_dir / "validation.csv")


