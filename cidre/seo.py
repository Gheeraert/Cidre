"""Helpers SEO purs pour les pages statiques CIDRE."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from .data_models import SiteConfig
from .utils import as_str, html_to_text, normalize_external_url, parse_pub_date


_SCRIPT_UNSAFE = {
    "<": "\\u003c",
    ">": "\\u003e",
    "&": "\\u0026",
    "\u2028": "\\u2028",
    "\u2029": "\\u2029",
}


@dataclass(frozen=True)
class PageSeo:
    """Métadonnées d'une page publique, déjà ramenées à ses données fiables."""

    description: str = ""
    public_path: str = ""
    og_type: str = "website"
    image_url: str = ""
    image_alt: str = ""
    json_ld: list[dict[str, Any]] = field(default_factory=list)


def normalize_site_url(value: Any) -> str:
    """Retourne une URL HTTP(S) publiable sans slash final, ou une chaîne vide."""
    raw = as_str(value)
    if not raw or any(ch.isspace() for ch in raw):
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.query or parsed.fragment:
        return ""
    path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def absolute_http_url(value: Any) -> str:
    """Valide une URL HTTP(S) complète sans imposer les règles propres au site."""
    raw = as_str(value)
    if not raw or any(ch.isspace() for ch in raw):
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return raw


def absolute_public_url(site_url: Any, public_path: Any = "") -> str:
    """Construit une URL publiée en préservant un éventuel sous-chemin du site."""
    base = normalize_site_url(site_url)
    if not base:
        return ""
    path = str(public_path or "").replace("\\", "/").strip().lstrip("/")
    if not path or path == "index.html":
        return base
    return f"{base}/{path}"


def public_image_path(value: Any) -> str:
    """Normalise une image CONFIG relative au site, sans accepter de chemin parent."""
    raw = as_str(value).replace("\\", "/").lstrip("/")
    if not raw:
        return ""
    if absolute_http_url(raw):
        return raw
    path = PurePosixPath(raw)
    if ".." in path.parts:
        return ""
    if len(path.parts) == 1:
        return f"assets/{path.name}"
    return str(path)


def available_social_image_url(cfg: SiteConfig, out_dir: Any) -> str:
    """URL sociale exploitable : absolue déclarée ou fichier réellement publié."""
    path = public_image_path(cfg.social_image)
    if not path:
        return ""
    if absolute_http_url(path):
        return path
    try:
        if (out_dir / path).is_file():
            return absolute_public_url(cfg.site_url, path)
    except TypeError:
        return ""
    return ""


def clean_description(value: Any, limit: int = 180) -> str:
    """Réduit Markdown/HTML à une phrase de description propre et raisonnable."""
    text = as_str(value)
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", text)
    text = html_to_text(text)
    text = re.sub(r"[`*_#>|]", " ", text)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(text) <= limit:
        return text
    shortened = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return (shortened or text[: limit - 1].rstrip()) + "…"


def bibliographic_description(book: Any) -> str:
    parts = [
        as_str(book.get("titre_norm")),
        as_str(book.get("sous_titre_norm")),
        as_str(book.get("credit_ligne")),
    ]
    text = " — ".join(part for part in parts if part)
    details = []
    if as_str(book.get("collection")):
        details.append(f"Collection {as_str(book.get('collection'))}")
    if as_str(book.get("id13")):
        details.append(f"ISBN {as_str(book.get('id13'))}")
    if details:
        text = f"{text}. {' ; '.join(details)}" if text else " ; ".join(details)
    return clean_description(text)


def book_description(book: Any) -> str:
    return clean_description(
        as_str(book.get("Description courte"))
        or as_str(book.get("Description longue"))
        or bibliographic_description(book)
    )


def site_description(cfg: SiteConfig) -> str:
    explicit = clean_description(cfg.site_description)
    if explicit:
        return explicit
    return clean_description(" — ".join(part for part in (cfg.site_title, cfg.site_subtitle) if as_str(part)))


def page_title(cfg: SiteConfig, distinctive: Any = "", *, home: bool = False) -> str:
    if home or not as_str(distinctive):
        return as_str(cfg.site_title)
    return f"{as_str(distinctive)} — {as_str(cfg.site_title)}"


def json_ld_script(data: dict[str, Any] | list[dict[str, Any]]) -> str:
    """Sérialise du JSON-LD sans laisser une donnée fermer le script HTML."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for source, replacement in _SCRIPT_UNSAFE.items():
        payload = payload.replace(source, replacement)
    return f'<script type="application/ld+json">{payload}</script>'


def seo_head_html(cfg: SiteConfig, title: str, seo: PageSeo | None) -> str:
    if seo is None:
        return ""
    description = clean_description(seo.description)
    canonical = absolute_public_url(cfg.site_url, seo.public_path)
    image = as_str(seo.image_url)
    image_alt = as_str(seo.image_alt)
    tags: list[str] = []
    if description:
        tags.append(f'<meta name="description" content="{html.escape(description, quote=True)}">')
    if canonical:
        tags.append(f'<link rel="canonical" href="{html.escape(canonical, quote=True)}">')
    if description:
        tags.extend([
            f'<meta property="og:title" content="{html.escape(title, quote=True)}">',
            f'<meta property="og:description" content="{html.escape(description, quote=True)}">',
            f'<meta property="og:type" content="{html.escape(seo.og_type, quote=True)}">',
            f'<meta property="og:site_name" content="{html.escape(as_str(cfg.site_title), quote=True)}">',
            '<meta property="og:locale" content="fr_FR">',
        ])
        if canonical:
            tags.append(f'<meta property="og:url" content="{html.escape(canonical, quote=True)}">')
    if image:
        tags.append(f'<meta property="og:image" content="{html.escape(image, quote=True)}">')
        if image_alt:
            tags.append(f'<meta property="og:image:alt" content="{html.escape(image_alt, quote=True)}">')
    if description:
        tags.extend([
            f'<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}">',
            f'<meta name="twitter:title" content="{html.escape(title, quote=True)}">',
            f'<meta name="twitter:description" content="{html.escape(description, quote=True)}">',
        ])
        if image:
            tags.append(f'<meta name="twitter:image" content="{html.escape(image, quote=True)}">')
            if image_alt:
                tags.append(f'<meta name="twitter:image:alt" content="{html.escape(image_alt, quote=True)}">')
    tags.extend(json_ld_script(item) for item in seo.json_ld)
    return "\n  ".join(tags)


def organization_json_ld(cfg: SiteConfig, *, logo_url: str = "", social_urls: Iterable[str] = ()) -> dict[str, Any]:
    site = normalize_site_url(cfg.site_url)
    organization: dict[str, Any] = {"@context": "https://schema.org", "@type": "Organization", "name": as_str(cfg.site_title)}
    if site:
        organization["@id"] = f"{site}#organization"
        organization["url"] = site
    if logo_url:
        organization["logo"] = logo_url
    same_as = [url for url in social_urls if absolute_http_url(url)]
    if same_as:
        organization["sameAs"] = same_as
    return organization


def website_json_ld(cfg: SiteConfig, organization: dict[str, Any]) -> dict[str, Any]:
    site = normalize_site_url(cfg.site_url)
    website: dict[str, Any] = {"@context": "https://schema.org", "@type": "WebSite", "name": as_str(cfg.site_title)}
    if site:
        website["@id"] = f"{site}#website"
        website["url"] = site
        website["publisher"] = {"@id": f"{site}#organization"}
    else:
        website["publisher"] = {"@type": "Organization", "name": organization.get("name", "")}
    return website


def book_json_ld(cfg: SiteConfig, book: Any, *, public_path: str, description: str,
                 image_url: str = "", part_of: dict[str, Any] | None = None) -> dict[str, Any]:
    url = absolute_public_url(cfg.site_url, public_path)
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Book",
        "inLanguage": "fr",
        "publisher": ({"@id": f"{normalize_site_url(cfg.site_url)}#organization"}
                      if normalize_site_url(cfg.site_url)
                      else {"@type": "Organization", "name": as_str(cfg.site_title)}),
    }
    name = as_str(book.get("titre_norm"))
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    if url:
        data["@id"] = url
        data["url"] = url
    subtitle = as_str(book.get("sous_titre_norm"))
    if subtitle:
        data["alternateName"] = subtitle
    isbn = as_str(book.get("id13"))
    if isbn:
        data["isbn"] = isbn
    parsed_date = parse_pub_date(book.get("date_parution_norm"))
    if parsed_date:
        data["datePublished"] = parsed_date.isoformat()
    if image_url:
        data["image"] = image_url
    fmt = as_str(book.get("format_site"))
    if fmt:
        data["bookFormat"] = fmt
    if part_of:
        data["isPartOf"] = part_of
    openedition = normalize_external_url(book.get("openedition_url"))
    if openedition:
        data["sameAs"] = openedition
    return data


def sitemap_xml(site_url: Any, html_paths: Iterable[str]) -> str:
    urls = sorted({absolute_public_url(site_url, path) for path in html_paths if absolute_public_url(site_url, path)})
    rows = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>", '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    rows.extend(f"  <url><loc>{html.escape(url)}</loc></url>" for url in urls)
    rows.append("</urlset>")
    return "\n".join(rows) + "\n"


def robots_txt(site_url: Any) -> str:
    sitemap = absolute_public_url(site_url, "sitemap.xml")
    content = "User-agent: *\nAllow: /\n"
    if sitemap:
        content += f"\nSitemap: {sitemap}\n"
    return content
