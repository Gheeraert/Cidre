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
from .excel_data import render_social_strip, resolve_social_icon_source
from .html_templates import (
    book_order_block, book_retailers_block, order_pdf_rel, page_shell,
)
from .utils import (
    as_str, clean_json_value, e, fmt_display_date, md_to_html, norm_bool,
    render_contacts_block, resolve_asset_source, slugify, toc_to_html,
    write_file,
)

# -------------------------
# Build site
# -------------------------

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
    Copie les assets déclarés dans CONFIG vers dist/assets.
    Règle :
      - on ne supprime jamais dist/assets/*
      - on ne remplace un fichier existant que si la source semble "plus récente" ou différente
        (même logique que copy_covers).
    """
    excel_dir = excel_path.parent
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)

    declared = [cfg.logo_left, cfg.logo_right, cfg.favicon, cfg.footer_logo]
    if cfg.order_mode == "pdf" and cfg.order_pdf_filename:
        # Toujours sous dist/assets/, pour correspondre au lien ../assets/<rel>
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

def build_catalogue_json(books: pd.DataFrame, out_dir: Path) -> None:
    recs = []
    for _, r in books.iterrows():
        # Année: garantir une valeur lisible (éviter '2025.0')
        y = r.get("year")
        year_str = ""
        if y is not None and not pd.isna(y):
            try:
                year_str = str(int(float(y)))
            except Exception:
                year_str = str(y).strip()

        # ✅ COVER: ne publier que si le fichier existe vraiment dans dist/covers
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

    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    (out_dir / "assets" / "catalogue.json").write_text(
        json.dumps(recs, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8"
    )



def _book_card_html(r: pd.Series, rel_prefix: str, cfg: SiteConfig) -> str:
    cover = as_str(r.get("cover_file")).strip()

    if cover:
        cover = cover.replace("\\", "/").split("/")[-1]  # basename sûr
        cover_url = f"{rel_prefix}/covers/{e(cover)}"  # PAS de replace()

        cover_html = (
            f"<a href='#' class='cover-zoom' data-lightbox-src='{cover_url}'>"
            f"<img class='cover' style='width:180px;height:auto' src='{cover_url}' alt='' "
            f"onerror=\"this.style.display='none'\">"
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

    return f"""
<div class="card">
  {cover_html}
  <div class="meta">
    <a href="{rel_prefix}/livres/{e(r.get('slug'))}.html"><strong>{e(r.get('titre_norm'))}</strong></a>
    {subtitle_html}
    {credit_html}
    {badge_html}
    {date_html}
    {price_html}{avail_html}{physical_html}
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
<h2>Nouveautés</h2>
<p class="small">Nos parutions récentes</p>
<div class="grid">
{chr(10).join(cards)}
</div>
<p style="margin-top:16px">
  <a class="btn" href="./catalogue.html">Voir tout le catalogue</a>
  <a class="btn" href="./nouveautes.html">Voir les nouveautés</a>
</p>
"""
    write_file(out_dir / "index.html", page_shell(cfg, f"{cfg.site_title} — Accueil", "home", body, "."))

def build_catalogue_page(cfg: SiteConfig, out_dir: Path) -> None:
    body = f"""
<h2>{e(cfg.menu_label_catalogue)}</h2>
<p class="small">Recherche plein texte + filtres (collection / format / année).</p>

<div class="toolbar">
  <input id="q" type="search" placeholder="Rechercher (titre, contributeurs, ISBN, collection)…">
  <select id="f_collection"></select>
  <select id="f_format"></select>
  <select id="f_year"></select>
</div>

<p class="small"><span id="count"></span> résultat(s)</p>
<div id="out" class="grid"></div>
<p style="margin-top:12px">
  <a id="more" class="btn" href="#">Afficher plus</a>
</p>
<script>{DEFAULT_JS}</script>
"""
    write_file(out_dir / "catalogue.html",
               page_shell(cfg, f"{cfg.site_title} — {cfg.menu_label_catalogue}", "catalogue", body, "."))


def build_new_titles(cfg: SiteConfig, recent: pd.DataFrame, out_dir: Path, new_months: int) -> None:
    df = recent.copy()

    if df.empty:
        body = f"""
<h2>Nouveautés</h2>
<p class="small">Aucun titre paru dans les {int(new_months)} derniers mois.</p>
"""
        write_file(out_dir / "nouveautes.html",
                   page_shell(cfg, f"{cfg.site_title} — Nouveautés", "nouveautes", body, "."))
        return

    if "pub_date" in df.columns:
        df = df.sort_values("pub_date", ascending=False)

    df = df.head(cfg.new_titles_count)

    # Affichage en vignettes, comme l'accueil
    cards = [_book_card_html(r, ".", cfg) for _, r in df.iterrows()]
    body = f"""
<h2>Nouveautés</h2>
<p class="small">Titres parus dans les {int(new_months)} derniers mois.</p>
<div class="grid">
{chr(10).join(cards)}
</div>
"""
    write_file(out_dir / "nouveautes.html", page_shell(cfg, f"{cfg.site_title} — Nouveautés", "nouveautes", body, "."))


def build_upcoming_page(cfg: SiteConfig, upcoming: pd.DataFrame, out_dir: Path) -> None:
    title = cfg.menu_label_a_paraitre

    if upcoming.empty:
        body = f"""
<h2>{e(title)}</h2>
<p class="small">Aucun titre “à paraître” détecté.</p>
"""
        write_file(out_dir / "a-paraitre.html", page_shell(cfg, f"{cfg.site_title} — {title}", "a_paraitre", body, "."))
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
<h2>{e(title)}</h2>
<p class="small">Prochainement en librairie !</p>
<div class="grid">
{chr(10).join(cards)}
</div>
"""
    write_file(out_dir / "a-paraitre.html", page_shell(cfg, f"{cfg.site_title} — {title}", "a_paraitre", body, "."))


def build_book_pages(cfg: SiteConfig, books: pd.DataFrame, out_dir: Path,
                     revue_slugs: Optional[Dict[str, str]] = None,
                     collection_slugs: Optional[Dict[str, str]] = None) -> None:
    livres_dir = out_dir / "livres"
    livres_dir.mkdir(parents=True, exist_ok=True)

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

        cover_html = (
            f"<a href='#' class='cover-zoom' data-lightbox-src='../covers/{e(cover)}'>"
            f"<img class='cover' style='width:180px;height:auto' src='../covers/{e(cover)}' alt='' "
            f"onerror=\"this.style.display='none'\">"
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
                        f"<a class='badge' href='../revues/{e(rslug)}.html'>"
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
                        f"<a class='badge' href='../collections/{e(cslug)}.html'>"
                        f"{e(collection)}</a>"
                    )
                else:
                    # collection inactive ou identifiant inconnu : pas de page
                    # générée, badge sans lien plutôt qu'une URL 404
                    badges.append(f"<span class='badge'>{e(collection)}</span>")
            else:
                # appel historique sans mapping : lien fondé sur l'identifiant
                badges.append(
                    f"<a class='badge' href='../collections/{e(collection_id)}.html'>"
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

        desc_html = f"<h3>Présentation</h3>{md_to_html(desc)}" if desc else ""
        toc_block = toc_to_html(toc)
        toc_html = f"<h3>Table des matières</h3>{toc_block}" if toc_block else ""

        body = f"""
<div style="display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap">
  <div>{cover_html}</div>
  <div style="min-width:260px;flex:1">
    <h2>{e(title)}</h2>
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
        write_file(livres_dir / f"{as_str(r.get('slug'))}.html",
                   page_shell(cfg, f"{cfg.site_title} — {title}", "catalogue", body, ".."))


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
        lis.append(f'<li><a href="./{e(c.get("slug") or c.get("collection_id"))}.html">{e(c.get("name"))}</a></li>')
    body = f"""
<h2>{e(cfg.menu_label_collections)}</h2>
<p class="small">Nos collections.</p>
<ul>
{chr(10).join(lis)}
</ul>
"""
    write_file(base / "index.html", page_shell(cfg, f"{cfg.site_title} — Collections", "collections", body, ".."))

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
        <h2>{e(name)}</h2>
        {issn_line}
        {desc_block}
        {''.join(meta)}
        <h3>Ouvrages rattachés</h3>
        {cards_html}
        """
        slug = as_str(c.get("slug") or cid)
        write_file(base / f"{slug}.html", page_shell(cfg, f"{cfg.site_title} — {name}", "collections", body, ".."))

def build_revues(cfg: SiteConfig, books: pd.DataFrame, revues: pd.DataFrame, out_dir: Path) -> None:
    base = out_dir / "revues"
    base.mkdir(parents=True, exist_ok=True)
    if revues.empty:
        body = f"""
<h2>{e(cfg.menu_label_revues)}</h2>
<p class="small">Aucune revue renseignée dans l’onglet REVUES.</p>
"""
        write_file(base / "index.html", page_shell(cfg, f"{cfg.site_title} — Revues", "revues", body, ".."))
        return

    df = revues.copy()
    df["is_active"] = df.get("is_active", 1).apply(norm_bool)
    df = df[df["is_active"]].copy()
    df["title"] = df.get("title", "").apply(as_str)
    df["journal_id"] = df.get("journal_id", "").apply(as_str)
    df["slug"] = df.apply(
        lambda r: slugify(as_str(r.get("slug")) or as_str(r.get("title")) or as_str(r.get("journal_id")) or "revue"),
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
<h2>{e(cfg.menu_label_revues)}</h2>
<ul>
{chr(10).join(lis)}
</ul>
"""
    write_file(base / "index.html", page_shell(cfg, f"{cfg.site_title} — Revues", "revues", body, ".."))

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
<h2>{e(title)}</h2>
{''.join(meta)}
{desc if desc else ""}
<h3>Numéros parus</h3>
{cards_html}
"""
        write_file(base / f"{as_str(r.get('slug'))}.html",
                   page_shell(cfg, f"{cfg.site_title} — {title}", "revues", body, ".."))


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
        body = "<h2>Contact</h2><p class='small'>Aucun contact renseigné.</p>"
    else:
        body = f"<h2>Contact</h2><p class='small'>Planche de contacts (générée depuis l’Excel).</p><div class='grid'>{''.join(cards)}</div>"

    write_file(out_dir / "contact.html", page_shell(cfg, f"{cfg.site_title} — Contact", "contact", body, "."))


def build_pages(cfg: SiteConfig, pages: pd.DataFrame, contacts: pd.DataFrame, out_dir: Path) -> None:
    if pages.empty:
        for slug, title, key in [("open-access", cfg.menu_label_open_access, "open_access"),
                                 ("actualites", cfg.menu_label_actualites, "actualites")]:
            body = f"<h2>{e(title)}</h2><p class='small'>Page non renseignée dans l’onglet PAGES.</p>"
            write_file(out_dir / f"{slug}.html", page_shell(cfg, f"{cfg.site_title} — {title}", key, body, "."))
        return

    df = pages.copy()
    if "is_published" in df.columns:
        df["is_published"] = df["is_published"].apply(norm_bool)
        df = df[df["is_published"]].copy()

    for _, r in df.iterrows():
        slug = slugify(as_str(r.get("slug"))) if as_str(r.get("slug")) else ""
        if not slug:
            continue
        if slug in {"actualites", "actus"}:
            continue
        title = as_str(r.get("title") or slug)
        content = md_to_html(r.get("content_md") or "")
        empty = "<p class='small'>(contenu vide)</p>"
        body = f"<h2>{e(title)}</h2>{content if content else empty}"
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

        write_file(out_dir / f"{slug}.html", page_shell(cfg, f"{cfg.site_title} — {title}", key, body, "."))

    for slug, title, key in [("open-access", cfg.menu_label_open_access, "open_access")]:
        if not (out_dir / f"{slug}.html").exists():
            body = f"<h2>{e(title)}</h2><p class='small'>Page non renseignée dans l’onglet PAGES.</p>"
            write_file(out_dir / f"{slug}.html", page_shell(cfg, f"{cfg.site_title} — {title}", key, body, "."))

def build_validation_report(books: pd.DataFrame, out_dir: Path) -> None:
    problems = []
    for _, r in books.iterrows():
        issues = []
        if not r.get("id13"):
            issues.append("ISBN/GTIN manquant")
        if not as_str(r.get("titre_norm")):
            issues.append("Titre manquant")
        cover = as_str(r.get("cover_file"))
        if not cover:
            issues.append("Couverture manquante (cover_file)")
        else:
            cov = Path(cover.replace("\\", "/")).name
            if utils.AVAILABLE_COVERS and cov not in utils.AVAILABLE_COVERS:
                issues.append("Couverture introuvable dans dist/covers (nom incohérent ?)")
        if not as_str(r.get("Description courte")) and not as_str(r.get("Description longue")):
            issues.append("Résumé manquant")
        if issues:
            problems.append({
                "slug": as_str(r.get("slug")),
                "id13": as_str(r.get("id13")),
                "titre": as_str(r.get("titre_norm")),
                "issues": "; ".join(issues)
            })
    pd.DataFrame(problems).to_csv(out_dir / "validation.csv", index=False, encoding="utf-8")


