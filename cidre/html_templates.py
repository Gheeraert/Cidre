# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
# Module extrait de build_site.py (découpage sans changement fonctionnel).

from __future__ import annotations

import re
from typing import Any, Dict

from .data_models import SiteConfig
from .default_assets import DEFAULT_CSS, LIGHTBOX_HTML, NEWS_CAROUSEL_JS
from .utils import as_str, e, footer_rich

# -------------------------
# HTML templates
# -------------------------

def page_shell(cfg: SiteConfig, title: str, active: str, body_html: str, rel: str = ".") -> str:
    def nav_link(href: str, label: str, key: str) -> str:
        cls = "active" if active == key else ""
        return f'<a class="{cls}" href="{href}">{e(label)}</a>'

    nav = "\n".join([
        nav_link(f"{rel}/index.html", "Nouveautés", "home"),
        nav_link(f"{rel}/presentation.html", cfg.menu_label_presentation, "presentation"),
        # nav_link(f"{rel}/soumettre-un-manuscrit.html", cfg.menu_label_soumettre, "soumettre"),
        nav_link(f"{rel}/catalogue.html", cfg.menu_label_catalogue, "catalogue"),
        nav_link(f"{rel}/a-paraitre.html", cfg.menu_label_a_paraitre, "a_paraitre"),
        nav_link(f"{rel}/collections/index.html", cfg.menu_label_collections, "collections"),
        nav_link(f"{rel}/revues/index.html", cfg.menu_label_revues, "revues"),
        # nav_link(f"{rel}/open-access.html", cfg.menu_label_open_access, "open_access"),
        nav_link(f"{rel}/commander.html", cfg.menu_label_commandes, "commandes/contacts"),
        nav_link(f"{rel}/actualites.html", cfg.menu_label_actualites, "actualites"),
        # nav_link(f"{rel}/contact.html", "Contact", "contact"),

        # 🔍 Loupe (à droite)
        # f'<a class="nav-search" href="{rel}/catalogue.html" title="Rechercher dans le catalogue" aria-label="Rechercher dans le catalogue">🔍</a>',
    ])

    def logo_img(path: str, alt: str) -> str:
        if not path:
            return ""
        img = f'<img src="{rel}/{e(path)}" alt="{e(alt)}">'
        return img

    left = logo_img(cfg.logo_left, "Logo")
    right = logo_img(cfg.logo_right, "Logo")

    def maybe_link(img_html: str, href: str) -> str:
        if img_html and href:
            return f'<a href="{e(href)}" target="_blank" rel="noopener">{img_html}</a>'
        return img_html

    left = maybe_link(left, cfg.logo_left_link)
    right = maybe_link(right, cfg.logo_right_link)

    favicon_html = f'<link rel="icon" href="{rel}/{e(cfg.favicon)}">' if cfg.favicon else ""

    css = DEFAULT_CSS
    css = css.replace("--accent: #005a9c", f"--accent: {cfg.accent_color}")
    css = css.replace("--header: #2e2a22", f"--header: {cfg.header_bg}")
    css = re.sub(r"\.brand-logos img \{[^}]*\}",
                 f".brand-logos img {{ display:block; height: {int(cfg.logo_height)}px; width: auto; }}", css)

    news_block = ""
    if active == "home":
        news_block = (
            f'\n<div id="newsbar"></div>\n'
            f'<script>{NEWS_CAROUSEL_JS}</script>\n'
        )

    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{e(title)}</title>
  {favicon_html}
  <style>{css}</style>
</head>
<body>
<header>
  <div class="wrap">
    <div class="brand">
      <div class="brand-left">
        <div class="brand-logos">{left}</div>

        <div class="brand-text">
          <div class="brand-title">{e(cfg.site_title)}</div>

          <div class="brand-sub">
            <div class="brand-subrow">
              <span class="brand-subtitle-text">{e(cfg.site_subtitle)}</span>
              <span class="brand-search-wrap">
                Rechercher :
                <a href="{rel}/catalogue.html" class="brand-search"
                   title="Rechercher dans le catalogue"
                   aria-label="Rechercher dans le catalogue">🔍</a>
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="brand-logos">{right}</div>
    </div>

    <nav class="nav">{nav}</nav>
  </div>
</header>

{news_block}
<main class="wrap">
{body_html}
</main>
<footer>
  <div class="wrap">
    <div class="footer-grid">
      <div class="footer-left">
        {f"<div>{footer_rich(cfg.footer_text, rel)}</div>" if cfg.footer_text else ""}
        {f"<div>{footer_rich(cfg.footer_conceptor, rel)}</div>" if cfg.footer_conceptor else ""}
        {f"<div>{footer_rich(cfg.footer_copyright, rel)}</div>" if cfg.footer_copyright else ""}
        {f"<div>{footer_rich(cfg.footer_legal, rel)}</div>" if cfg.footer_legal else ""}
      </div>
      <div class="footer-right">
        {(
        f"<a href='{e(cfg.footer_logo_href)}' target='_blank' rel='noopener'>"
        f"<img src='{rel}/{e(cfg.footer_logo)}' alt='{e(cfg.footer_logo_alt)}'>"
        f"</a>"
    ) if cfg.footer_logo and cfg.footer_logo_href else (
        f"<img src='{rel}/{e(cfg.footer_logo)}' alt='{e(cfg.footer_logo_alt)}'>"
    ) if cfg.footer_logo else ""}
      </div>
    </div>
  </div>
</footer>
{LIGHTBOX_HTML}
</body>
</html>
"""


def order_pdf_rel(value: str) -> str:
    """Chemin du bon de commande relatif à assets/ : 'fichier.pdf' ou 'docs/fichier.pdf'.

    La valeur CONFIG peut être un simple nom, 'docs/fichier.pdf' ou 'assets/docs/fichier.pdf' ;
    dans tous les cas le fichier est copié vers dist/assets/<rel> et lié en ../assets/<rel>.
    """
    rel = as_str(value).replace("\\", "/").strip().lstrip("/")
    if rel.startswith("assets/"):
        rel = rel[len("assets/"):]
    return rel


def book_order_block(cfg: SiteConfig, rec: Dict[str, Any]) -> str:
    title = rec.get("title", "")
    id13 = rec.get("id13", "")
    if cfg.order_mode == "pdf" and cfg.order_pdf_filename:
        return f'<p><a class="btn" href="../assets/{e(order_pdf_rel(cfg.order_pdf_filename))}">Commander (bon de commande)</a></p>'
    if cfg.order_mode == "url":
        url = rec.get("order_url") or ""
        if not url and cfg.order_url_template:
            url = cfg.order_url_template.replace("{id13}", str(id13))
        if url:
            return f'<p><a class="btn" href="{e(url)}" target="_blank" rel="noopener">Commander</a></p>'
    # mailto default
    if cfg.contact_email:
        subject = cfg.order_mail_subject
        body = cfg.order_mail_body.format(title=title, id13=id13)

        def enc(x: str) -> str:
            return (
                str(x)
                .replace("%", "%25")
                .replace("\n", "%0D%0A")
                .replace(" ", "%20")
            )

        return f'<p><a class="btn" href="mailto:{e(cfg.contact_email)}?subject={enc(subject)}&body={enc(body)}">Commander / contacter</a></p>'
    return ""


def book_retailers_block(id13: str, openedition_url: str = "") -> str:
    id13 = (id13 or "").strip()
    openedition_url = (openedition_url or "").strip()
    if not id13 and not openedition_url:
        return ""

    items = []

    # Lien OpenEdition en tête (si présent)
    if openedition_url:
        items.append(
            f"<li><a href='{e(openedition_url)}' target='_blank' rel='noopener'>"
            f"Lire en accès ouvert (OpenEdition)</a></li>"
        )

    # Libraires (si ISBN)
    if id13:
        retailers = [
            ("Decitre", f"https://www.decitre.fr/rechercher/result?q={id13}"),
            ("Fnac", f"https://www.fnac.com/SearchResult/ResultList.aspx?Search={id13}"),
            ("Place des Libraires", f"https://www.placedeslibraires.fr/listeliv.php?mots_recherche={id13}"),
            ("Cultura", f"https://www.cultura.com/catalogsearch/result/?q={id13}"),
            ("LCDPU (Comptoir des PU)", f"https://www.lcdpu.fr/livre/?isbn={id13}"),
        ]
        items.extend(
            f"<li><a href='{e(url)}' target='_blank' rel='noopener'>{e(label)}</a></li>"
            for label, url in retailers
        )

    links = "\n".join(items)

    return f"""
<details style="margin-top:8px">
  <summary class="small" style="cursor:pointer">Trouver ce livre chez des libraires en ligne ou en libre accès</summary>
  <ul style="margin:8px 0 0 18px">
    {links}
  </ul>
</details>
""".strip()


