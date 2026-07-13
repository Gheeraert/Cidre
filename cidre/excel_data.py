# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
# Module extrait de build_site.py (découpage sans changement fonctionnel).

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .data_models import SiteConfig
from .html_templates import page_shell
from .routes import (
    actualite_anchor_id, actualite_book_href, actualites_href,
    book_slug_candidate, book_slug_origin, collection_public_slug,
    revue_public_slug,
)
from .utils import (
    as_str, e, ensure_unique_slug, fmt_cm_guess, fmt_display_date, fmt_eur,
    fmt_int, format_credit_line, html_to_text, is_na, md_to_html, norm_bool,
    normalize_editorial_columns, normalize_excel_text, normalize_external_url,
    normalize_id13, parse_pub_date, parse_year, resolve_asset_source,
    sanitize_actu_html, slugify, write_file,
)

# -------------------------
# Load Excel data
# -------------------------

def detect_books_sheet(wb: pd.ExcelFile, preferred: str = "") -> str:
    if preferred and preferred in wb.sheet_names:
        return preferred

    candidates = []
    for sh in wb.sheet_names:
        try:
            df0 = wb.parse(sheet_name=sh, nrows=1)
        except Exception:
            continue
        cols = {str(c).strip().lower() for c in df0.columns}
        score = 0
        if "titre_norm" in cols or "titre" in cols:
            score += 2
        if "id13" in cols or "isbn-13" in cols or "gtin/ean-13" in cols:
            score += 2
        if "actif pour site" in cols or "active_site" in cols:
            score += 1
        if score >= 3:
            candidates.append((score, sh))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]

    return wb.sheet_names[0]


def load_pages(wb: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    if sheet not in wb.sheet_names:
        return pd.DataFrame()
    df = wb.parse(sheet_name=sheet)
    for c in ["slug", "title", "nav_label", "nav_order", "content_md", "is_published", "template"]:
        if c not in df.columns:
            df[c] = None
    normalize_editorial_columns(df, ["title", "nav_label", "content_md"])
    return df


def load_collections(wb: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    if sheet not in wb.sheet_names:
        return pd.DataFrame()
    df = wb.parse(sheet_name=sheet)
    df.columns = [str(c).strip() for c in df.columns]  # ✅ important
    for c in [
        "collection_id", "name", "slug", "description_md",
        "directeurs", "comite_scientifique",
        "issn_print", "issn_online",
        "is_active"
    ]:
        if c not in df.columns:
            df[c] = None
    normalize_editorial_columns(df, ["name", "description_md", "directeurs", "comite_scientifique"])
    return df


def detect_revues_sheet(wb: pd.ExcelFile, preferred: str = "") -> str:
    """Retourne l'onglet des revues, avec tolérance REVUE/REVUES et variantes proches."""
    preferred = as_str(preferred)
    if preferred and preferred in wb.sheet_names:
        return preferred

    wanted = {"revue", "revues", "journal", "journals"}
    for sh in wb.sheet_names:
        if slugify(sh) in wanted:
            return sh

    # Dernière chance : on repère un onglet contenant au moins quelques colonnes typiques
    typical = {"revue_id", "journal_id", "name", "title", "website_url", "url", "issn_print", "issn_online"}
    for sh in wb.sheet_names:
        try:
            probe = wb.parse(sheet_name=sh, nrows=3)
            cols = {slugify(str(c)) for c in probe.columns}
            if len(cols & typical) >= 3:
                return sh
        except Exception:
            pass
    return ""


def load_revues(wb: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    sh = detect_revues_sheet(wb, sheet)
    if not sh:
        return pd.DataFrame()

    df = wb.parse(sheet_name=sh)
    df.columns = [str(c).strip() for c in df.columns]

    # En-têtes acceptés pour l'identifiant de revue (formes slugifiées).
    # L'alias générique « id » est conservé pour les anciens classeurs, mais
    # sa présence à côté d'un alias explicite est traitée comme une collision.
    id_aliases = {"journal-id", "revue-id", "review-id", "id"}
    id_headers = [c for c in df.columns if slugify(str(c)) in id_aliases]
    if len(id_headers) > 1:
        # Sans ce contrôle, le renommage produirait deux colonnes homonymes
        # « journal_id » et un traceback pandas incompréhensible.
        concurrents = " et ".join(f"« {h} »" for h in id_headers)
        raise ValueError(
            f"La feuille « {sh} » contient plusieurs colonnes servant "
            f"d'identifiant de revue : {concurrents}. "
            "Conservez une seule de ces colonnes."
        )

    colmap = {}
    for c in df.columns:
        lc = slugify(str(c))
        if lc in id_aliases:
            colmap[c] = "journal_id"
        elif lc in {"title", "titre", "name", "nom"}:
            colmap[c] = "title"
        elif lc in {"slug", "handle"}:
            colmap[c] = "slug"
        elif lc in {"url", "website", "website-url", "website_url", "site", "site-web", "site_web", "link", "lien"}:
            colmap[c] = "url"
        elif lc in {"issn-print", "issn_print", "issn papier", "issn-papier"}:
            colmap[c] = "issn_print"
        elif lc in {"issn-online", "issn_online", "eissn", "e-issn", "issn-en-ligne", "issn_en_ligne"}:
            colmap[c] = "issn_online"
        elif lc in {"description", "description-md", "description_md", "content", "contenu", "texte"}:
            colmap[c] = "description_md"
        elif lc in {"direction", "directeur", "directeurs", "editor", "editors"}:
            colmap[c] = "direction"
        elif lc in {"comite-scientifique", "comite_scientifique", "scientific-board", "scientific_board"}:
            colmap[c] = "comite_scientifique"
        elif lc in {"contact", "contact-email", "contact_email", "email", "mail"}:
            colmap[c] = "contact_email"
        elif lc in {"is-active", "is_active", "active", "actif", "published"}:
            colmap[c] = "is_active"
        elif lc in {"order", "ordre", "position", "sort-order", "sort_order"}:
            colmap[c] = "order"

    df = df.rename(columns=colmap)

    for c in ["journal_id", "title", "slug", "url", "issn_print", "issn_online", "description_md", "direction",
              "comite_scientifique", "contact_email", "is_active", "order"]:
        if c not in df.columns:
            df[c] = None

    df["journal_id"] = df["journal_id"].apply(as_str)
    df["title"] = df["title"].apply(as_str)
    df["slug"] = df["slug"].apply(as_str)
    df["url"] = df["url"].apply(as_str)
    df["issn_print"] = df["issn_print"].apply(as_str)
    df["issn_online"] = df["issn_online"].apply(as_str)
    df["description_md"] = df["description_md"].apply(lambda x: normalize_excel_text(x) if not is_na(x) else "")
    df["direction"] = df["direction"].apply(normalize_excel_text)
    df["comite_scientifique"] = df["comite_scientifique"].apply(normalize_excel_text)
    df["contact_email"] = df["contact_email"].apply(as_str)
    df["is_active"] = df["is_active"].apply(lambda x: True if is_na(x) else norm_bool(x))
    df["order"] = pd.to_numeric(df["order"], errors="coerce")

    # Fallbacks utiles
    df["title"] = df.apply(lambda r: as_str(r.get("title")) or as_str(r.get("journal_id")), axis=1)
    df["slug"] = df.apply(
        lambda r: revue_public_slug(r.get("slug"), r.get("title"), r.get("journal_id")),
        axis=1
    )

    return df


def build_revue_slug_map(revues: pd.DataFrame) -> Dict[str, str]:
    """Table journal_id (slugifié) -> slug public de la page revues/<slug>.html.

    Les livres du catalogue rattachés à une revue portent le journal_id de
    celle-ci en collection_id (slugifié par load_books) ; cette table permet
    à build_book_pages de pointer le badge vers la page de revue réellement
    générée par build_revues, et non vers collections/<journal_id>.html.

    Une revue inactive (aucune page générée) est présente avec la valeur ""
    pour que le badge soit rendu sans lien plutôt qu'en URL 404.
    """
    out: Dict[str, str] = {}
    if revues is None or revues.empty:
        return out
    for _, r in revues.iterrows():
        jid = slugify(as_str(r.get("journal_id")))
        if not jid:
            continue
        if norm_bool(r.get("is_active")):
            # même calcul de slug que build_revues
            out[jid] = revue_public_slug(r.get("slug"), r.get("title"), r.get("journal_id"))
        else:
            out.setdefault(jid, "")
    return out


def build_collection_slug_map(collections: pd.DataFrame,
                              books: Optional[pd.DataFrame] = None) -> Dict[str, str]:
    """Table collection_id (slugifié) -> slug public de collections/<slug>.html.

    Reproduit exactement la règle de nommage de build_collections (slug de la
    feuille, sinon collection_id) pour que le badge des fiches livres pointe
    vers la page réellement écrite, même quand collection_id diffère du slug
    (ex. col-classiques -> classiques.html).

    Une collection inactive (aucune page générée) est présente avec la valeur
    "" pour que le badge soit rendu sans lien plutôt qu'en URL 404.
    """
    out: Dict[str, str] = {}
    if collections is None or collections.empty:
        # même dérivation que build_collections : sans feuille COLLECTIONS,
        # les pages sont créées depuis les noms de collection du catalogue.
        if books is not None and not books.empty and "collection" in books.columns:
            for n in {as_str(x) for x in books["collection"].dropna().tolist() if as_str(x)}:
                cid = slugify(n)
                out[cid] = cid
        return out
    for _, c in collections.iterrows():
        raw_cid = as_str(c.get("collection_id"))
        raw_slug = as_str(c.get("slug"))
        cid = slugify(raw_cid) if raw_cid else (slugify(raw_slug) if raw_slug else "")
        if not cid:
            continue
        if norm_bool(c.get("is_active")):
            target = collection_public_slug(raw_slug, cid)
        else:
            target = ""
        if cid in out and out[cid] and target and out[cid] != target:
            raise ValueError(
                f"La feuille COLLECTIONS contient plusieurs lignes actives avec "
                f"l'identifiant « {raw_cid or raw_slug} » menant à des pages "
                f"différentes (« {out[cid]}.html » et « {target}.html »). "
                "Conservez une seule de ces lignes."
            )
        if target or cid not in out:
            out[cid] = target
    return out


def load_contacts(wb: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    if sheet not in wb.sheet_names:
        return pd.DataFrame()
    df = wb.parse(sheet_name=sheet)
    for c in ["label", "name", "role", "email", "phone", "address", "order", "is_active"]:
        if c not in df.columns:
            df[c] = None
    normalize_editorial_columns(df, ["label", "name", "role", "address"])
    return df

def detect_actualites_sheet(wb: pd.ExcelFile) -> str:
    # tolérance accents/variantes
    wanted = {"actualites", "actualités", "actus", "news"}
    for sh in wb.sheet_names:
        if slugify(sh) in wanted:
            return sh
    return ""  # pas d'onglet actus

def load_actualites(wb: pd.ExcelFile) -> pd.DataFrame:
    sh = detect_actualites_sheet(wb)
    if not sh:
        return pd.DataFrame()

    df = wb.parse(sheet_name=sh)
    df.columns = [str(c).strip() for c in df.columns]

    colmap = {}
    for c in df.columns:
        lc = slugify(str(c))
        if lc in {"title", "titre"}:
            colmap[c] = "title"
        elif lc in {"image", "visuel", "image-file", "image_file", "cover-file", "cover_file"}:
            colmap[c] = "image"
        elif lc in {"date", "date-publication", "date_publication", "datepub"}:
            colmap[c] = "date"
        elif lc in {"is-active", "is_active", "is_published", "actif", "active"}:
            colmap[c] = "is_active"
        elif lc in {"texte", "text", "contenu", "content", "resume", "résumé", "description"}:
            colmap[c] = "text"
        elif lc in {"id13", "isbn", "isbn13", "book_id13", "gtin", "ean13", "ean-13", "isbn-13"}:
            colmap[c] = "id13"
        elif lc in {"lien", "link", "url", "lien_externe", "lien-externe"}:
            colmap[c] = "link"

    df = df.rename(columns=colmap)

    for c in ["title", "image", "date", "text", "is_active", "id13", "link"]:
        if c not in df.columns:
            df[c] = None

    df["title"] = df["title"].apply(normalize_excel_text)
    df["image"] = df["image"].apply(as_str)
    df["date"] = df["date"].apply(as_str)
    df["text"] = df["text"].apply(normalize_excel_text)
    df["is_active"] = df["is_active"].apply(lambda x: True if is_na(x) else norm_bool(x))
    df["id13"] = df["id13"].apply(normalize_id13)
    df["link"] = df["link"].apply(as_str)

    df = df[df["is_active"]].copy()

    # garde si au moins un champ est renseigné (titre OU texte OU image)
    df = df[
        df["title"].astype(str).str.strip().ne("")
        | df["text"].astype(str).str.strip().ne("")
        | df["image"].astype(str).str.strip().ne("")
    ].copy()

    def _ds(s: str) -> datetime:
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return datetime.min

    if df["date"].notna().any():
        df["_ds"] = df["date"].apply(_ds)
        df = df.sort_values("_ds", ascending=False).drop(columns=["_ds"])

    return df


def resolve_actu_image_source(excel_dir: Path, img: str) -> Optional[Path]:
    """Retrouve une image d'actu (comme resolve_asset_source mais orienté images)."""
    if not img:
        return None
    rel = img.replace("\\", "/").strip()
    candidates = [
        # dossier source canonique : <dossier du classeur>/assets/actu/
        excel_dir / "assets" / "actu" / rel,
        excel_dir / "assets" / "actu" / Path(rel).name,
        # anciens emplacements acceptés pour compatibilité
        excel_dir / rel,
        excel_dir / "assets" / rel,
        excel_dir / "actu" / rel,
        excel_dir / "images" / rel,
        excel_dir / Path(rel).name,
        excel_dir / "assets" / Path(rel).name,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None

def copy_actualites_images(excel_path: Path, out_dir: Path, actualites: pd.DataFrame) -> None:
    excel_dir = excel_path.parent
    dest = out_dir / "assets" / "actu"
    dest.mkdir(parents=True, exist_ok=True)

    for img in actualites.get("image", pd.Series(dtype=str)).tolist():
        img = as_str(img)
        if not img:
            continue
        src = resolve_actu_image_source(excel_dir, img)
        if not src:
            continue

        dst = dest / src.name

        if dst.exists():
            try:
                same_size = dst.stat().st_size == src.stat().st_size
                dst_newer_or_equal = dst.stat().st_mtime >= src.stat().st_mtime
                if same_size and dst_newer_or_equal:
                    continue
            except Exception:
                pass

        shutil.copy2(src, dst)


def build_actualites_json(actualites: pd.DataFrame, out_dir: Path, books: Optional[pd.DataFrame] = None, max_items: int = 10) -> None:
    recs = []

    id13_to_slug = {}
    if books is not None and not books.empty and "id13" in books.columns and "slug" in books.columns:
        for _, b in books.iterrows():
            i = as_str(b.get("id13"))
            s = as_str(b.get("slug"))
            if i and s:
                id13_to_slug[i] = s

    if actualites is None or actualites.empty:
        (out_dir / "assets" / "actualites.json").write_text("[]", encoding="utf-8")
        return

    def _excerpt(s: str, n: int = 200) -> str:
        s = (s or "").strip()
        if len(s) <= n:
            return s
        return s[: n - 1].rstrip() + "…"

    used_ids: set[str] = set()

    for _, r in actualites.head(int(max_items)).iterrows():
        img = as_str(r.get("image"))
        img_url = f"assets/actu/{Path(img).name}" if img else ""

        text_md = as_str(r.get("text"))
        text_html = ""
        excerpt = ""

        actu_id = actualite_anchor_id(r.get("title"), used_ids)

        book_id13 = as_str(r.get("id13"))
        href = actualites_href(".")
        if book_id13 and book_id13 in id13_to_slug:
            href = actualite_book_href(id13_to_slug[book_id13], ".")

        ext_link = normalize_external_url(r.get("link"))

        if text_md:
            # Markdown -> HTML (comme le reste du site)
            text_html = md_to_html(text_md)
            text_html = sanitize_actu_html(text_html)

            # Extrait texte (pour carrousel)
            excerpt = _excerpt(html_to_text(text_html), 220)

        recs.append({
            "title": as_str(r.get("title")),
            "date": fmt_display_date(r.get("date")),
            "image": img_url,
            "html": text_html,      # pour la page actualites.html
            "excerpt": excerpt,     # pour le carrousel
            "href": href,
            "id": actu_id,
            "link": ext_link,
        })

    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    (out_dir / "assets" / "actualites.json").write_text(
        json.dumps(recs, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8"
    )

def get_social_links(cfg: SiteConfig) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    for i in range(1, 7):
        name = as_str(getattr(cfg, f"social_{i}_name", ""))
        url = normalize_external_url(getattr(cfg, f"social_{i}_url", ""))
        icon = as_str(getattr(cfg, f"social_{i}_icon", ""))
        if name and url:
            links.append({"name": name, "url": url, "icon": icon})
    return links


def resolve_social_icon_source(excel_dir: Path, icon_spec: str) -> Optional[Path]:
    """Résout une icône sociale depuis un identifiant logique (instagram) ou un chemin/fichier explicite."""
    icon_spec = as_str(icon_spec).replace("\\", "/")
    if not icon_spec:
        return None

    explicit_exts = (".svg", ".png", ".webp", ".jpg", ".jpeg")
    lowered = icon_spec.lower()
    if "/" in icon_spec or lowered.endswith(explicit_exts):
        rel = f"assets/social/{icon_spec}" if "/" not in icon_spec else icon_spec
        return resolve_asset_source(excel_dir, rel)

    key = slugify(icon_spec)
    if not key:
        return None

    for ext in explicit_exts:
        for cand in (
            excel_dir / "assets" / "social" / f"{key}{ext}",
            excel_dir / "social" / f"{key}{ext}",
            excel_dir / f"{key}{ext}",
        ):
            if cand.exists() and cand.is_file():
                return cand
    return None


def find_social_icon_public_path(out_dir: Path, icon_spec: str) -> str:
    icon_spec = as_str(icon_spec).replace("\\", "/")
    if not icon_spec:
        return ""

    explicit_exts = (".svg", ".png", ".webp", ".jpg", ".jpeg")
    lowered = icon_spec.lower()
    if "/" in icon_spec or lowered.endswith(explicit_exts):
        basename = Path(icon_spec).name
        rel = f"assets/social/{basename}"
        if (out_dir / rel).exists():
            return rel
        if "/" in icon_spec and (out_dir / icon_spec).exists():
            return icon_spec
        return ""

    key = slugify(icon_spec)
    if not key:
        return ""

    for ext in explicit_exts:
        rel = f"assets/social/{key}{ext}"
        if (out_dir / rel).exists():
            return rel
    return ""


def render_social_strip(cfg: SiteConfig, out_dir: Path) -> str:
    links = get_social_links(cfg)
    if not links:
        return ""

    intro = e(as_str(cfg.social_intro) or "Suivez les PURH")
    badges = []
    for item in links:
        name = item["name"]
        url = item["url"]
        icon_rel = find_social_icon_public_path(out_dir, item.get("icon", ""))
        icon_html = f"<img src='./{e(icon_rel)}' alt='' loading='lazy' decoding='async'>" if icon_rel else ""
        badges.append(
            f"<a class='social-badge' href='{e(url)}' target='_blank' rel='noopener'>{icon_html}<span>{e(name)}</span></a>"
        )

    return (
        "<div class='social-strip'>"
        f"<div class='social-strip-title'>{intro}</div>"
        f"<div class='social-links'>{''.join(badges)}</div>"
        "</div>"
    )


def build_actualites_page(cfg: SiteConfig, out_dir: Path) -> None:
    social_html = render_social_strip(cfg, out_dir)
    p = out_dir / "assets" / "actualites.json"
    if not p.exists():
        body = f"<h2>{e(cfg.menu_label_actualites)}</h2>{social_html}<p class='small'>Aucune actualité.</p>"
        write_file(out_dir / "actualites.html", page_shell(cfg, f"{cfg.site_title} — Actualités", "actualites", body, "."))
        return

    data = json.loads(p.read_text(encoding="utf-8"))
    if not data:
        body = f"<h2>{e(cfg.menu_label_actualites)}</h2>{social_html}<p class='small'>Aucune actualité.</p>"
        write_file(out_dir / "actualites.html", page_shell(cfg, f"{cfg.site_title} — Actualités", "actualites", body, "."))
        return

    items = []
    for r in data:
        title = e(r.get("title", ""))
        date_ = e(r.get("date", ""))
        img = as_str(r.get("image"))
        html_frag = r.get("html", "") or ""
        href = as_str(r.get("href")) or "./actualites.html"
        actu_id = as_str(r.get("id"))
        ext_link = as_str(r.get("link"))
        link_block = ""
        if ext_link:
            link_block = (
                "<div class='small' style='margin-top:12px'>"
                "<strong>Lien :</strong> "
                f"<a href='{e(ext_link)}' target='_blank' rel='noopener'>{e(ext_link)}</a>"
                "</div>"
            )
        title_html = f"<a href='{e(href)}' style='color:inherit;text-decoration:none'>" \
                     f"<div style='font-weight:750;font-size:1.15rem;line-height:1.2'>{title}</div></a>"
        # html_frag est déjà “sanitized” au build_json (mais on peut re-sécuriser)
        html_frag = sanitize_actu_html(as_str(html_frag))

        img_html = (
            f"<a href='{e(href)}' style='display:block'>"
            f"<img class='news-img' src='./{e(img)}' alt='' loading='lazy' decoding='async'>"
            f"</a>"
        ) if img else ""
        items.append(f"""
        <article id="actu-{e(actu_id)}" class="card news-card" style="flex-direction:column">
          {img_html}
          <div class="meta">
            {title_html}
            {f"<div class='small' style='margin-top:6px'>{date_}</div>" if date_ else ""}
            {f"<div style='margin-top:10px'>{html_frag}</div>" if html_frag else ""}
            {link_block}
          </div>
        </article>
        """.strip())

    body = f"""
<h2>{e(cfg.menu_label_actualites)}</h2>
{social_html}
<div class="grid">
{chr(10).join(items)}
</div>
""".strip()

    write_file(out_dir / "actualites.html", page_shell(cfg, f"{cfg.site_title} — Actualités", "actualites", body, "."))

def load_books(wb: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    df = wb.parse(sheet_name=sheet)
    df.columns = [str(c).strip() for c in df.columns]

    expected = [
        "id13", "slug", "titre_norm", "sous_titre_norm", "credit_ligne",
        "collection", "collection_id", "date_parution_norm", "format_site",
        "price", "availability",
        "prix_ttc", "devise", "availability_label",
        "cover_file", "Description courte", "Description longue", "Table des matières",
        "order_url", "openedition_url", "home_featured",
        "Largeur", "Hauteur", "Epaisseur", "Poids",
        "Nombre de pages (pages totales imprimées)", "Nombre de pages",
        "Actif pour site",
    ]
    for c in expected:
        if c not in df.columns:
            df[c] = None

    # Nettoyage des contenus éditoriaux (retours chariot OOXML "_x000D_", etc.)
    normalize_editorial_columns(df, [
        "titre_norm", "sous_titre_norm",
        "Description courte", "Description longue", "Table des matières",
    ])

    df["credit_ligne"] = df["credit_ligne"].fillna("").apply(format_credit_line)
    df["id13"] = df["id13"].apply(normalize_id13)
    df["openedition_url"] = df["openedition_url"].fillna("").apply(as_str)
    # Normaliser cover_file : on garde juste le basename (évite "covers/xxx.jpg" vs "xxx.jpg")
    df["cover_file"] = df["cover_file"].apply(
        lambda v: Path(as_str(v).replace("\\", "/")).name if as_str(v) else ""
    )
    # --- COLLECTION_ID : garantir un identifiant exploitable
    df["collection_id"] = df["collection_id"].apply(lambda x: slugify(as_str(x)) if as_str(x) else None)
    missing_cid = df["collection_id"].isna() | (df["collection_id"].astype(str).str.strip() == "")
    df.loc[missing_cid, "collection_id"] = df.loc[missing_cid, "collection"].apply(
        lambda x: slugify(as_str(x)) if as_str(x) else None)

    df["year"] = df["date_parution_norm"].apply(parse_year)
    df["pub_date"] = df["date_parution_norm"].apply(parse_pub_date)

    # Build slugs
    df["_source_slug"] = df["slug"].apply(lambda x: slugify(as_str(x)) if as_str(x) else "")
    used: set[str] = set()
    out_slugs: List[str] = []
    origins: List[str] = []
    candidates: List[str] = []
    was_uniquified: List[bool] = []
    for _, r in df.iterrows():
        title = as_str(r.get("titre_norm") or r.get("Titre") or "ouvrage")
        candidate = book_slug_candidate(r.get("slug"), title, r.get("id13"))
        final_slug = ensure_unique_slug(candidate, used)
        origins.append(book_slug_origin(r.get("slug"), r.get("id13")))
        candidates.append(candidate)
        was_uniquified.append(final_slug != candidate)
        out_slugs.append(final_slug)
    df["_slug_origin"] = origins
    df["_slug_candidate"] = candidates
    df["_slug_was_uniquified"] = pd.Series(was_uniquified, index=df.index, dtype=object)
    df["slug"] = out_slugs

    # Excerpt
    def excerpt(r: pd.Series) -> str:
        txt = r.get("Description courte") or r.get("Description longue") or ""
        s = as_str(txt).replace("\n", " ")
        if len(s) > 180:
            s = s[:177].rstrip() + "…"
        return s

    df["excerpt"] = df.apply(excerpt, axis=1)

    # Disponibilité
    if df["availability"].notna().any():
        df["availability_label"] = df["availability"].apply(as_str)
    else:
        df["availability_label"] = df["availability_label"].apply(as_str)

    # Prix
    def pick_price(r: pd.Series) -> Any:
        v = r.get("price")
        if not as_str(v):
            v = r.get("prix_ttc")
        return v

    df["price_str"] = df.apply(lambda r: fmt_eur(pick_price(r)), axis=1)
    df["currency_str"] = ""

    def physical_line(r: pd.Series) -> str:
        w = fmt_cm_guess(r.get("Largeur"))
        h = fmt_cm_guess(r.get("Hauteur"))
        ep = fmt_int(r.get("Epaisseur"))
        poids = fmt_int(r.get("Poids"))
        pages = fmt_int(r.get("Nombre de pages (pages totales imprimées)") or r.get("Nombre de pages"))

        parts = []
        if w and h:
            parts.append(f"{w} × {h} cm")
        elif w:
            parts.append(f"Largeur {w} cm")
        elif h:
            parts.append(f"Hauteur {h} cm")

        if pages:
            parts.append(f"{pages} p.")
        if ep:
            parts.append(f"ép. {ep} cm")
        if poids:
            parts.append(f"{poids} g")

        return " — ".join(parts)

    df["physical_str"] = df.apply(physical_line, axis=1)

    # Actif pour site
    # --- Alias colonne d’activation (templates GitHub vs master historique)
    if "active_site" in df.columns:
        if "Actif pour site" not in df.columns:
            df["Actif pour site"] = df["active_site"]
        else:
            mask = df["Actif pour site"].isna() | (df["Actif pour site"].astype(str).str.strip() == "")
            df.loc[mask, "Actif pour site"] = df.loc[mask, "active_site"]

    # Filtrage : on ne filtre que si on a au moins une valeur explicite
    if "Actif pour site" in df.columns and df["Actif pour site"].notna().any():
        df = df[df["Actif pour site"].apply(norm_bool)].copy()

    return df


