# Générateur de site statique de maison d'édition scientifique et / ou indépendante
# © 2025 Tony Gheeraert - Licence MIT (voir LICENSE)
# Crédits : PURH + Chaire d'excellence édition numérique de l'université de Rouen
# build_site = fichier principal du projet
#
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Générateur statique : Excel -> site HTML (sans backend)
- Lit : CONFIG, PAGES, COLLECTIONS, REVUES, CONTACTS + un onglet catalogue
- Génère : dist/index.html, dist/catalogue.html, dist/nouveautes.html,
           dist/a-paraitre.html, dist/collections/, dist/revues/, pages statiques, dist/assets/
- Recherche + filtres (collection / format / année) côté navigateur, via assets/catalogue.json

Usage:
  python build_site.py --excel purh_site_excel_template_v4.xlsx --out dist --covers-dir covers
  python build_site.py --excel purh_site_excel_template_v4.xlsx --out dist --publish-ftp

Notes:
- Les couvertures (images) sont attendues dans --covers-dir et copiées dans dist/covers
- Les assets déclarés dans CONFIG (logos, favicon, PDF bon de commande) sont copiés automatiquement vers dist/assets
- Le nom de l’onglet catalogue peut être donné par CONFIG.books_sheet (sinon auto-détection)
"""

from __future__ import annotations

import argparse
import dataclasses
import html
import json
import math
import os
import re
import shutil
import sys
import unicodedata
import calendar
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, Optional, List
from urllib.parse import unquote

import pandas as pd
try:
    import markdown as md  # python-markdown
except Exception:  # pragma: no cover
    md = None


# -------------------------
# Utils
# -------------------------
def render_contacts_block(contacts: pd.DataFrame, heading: str = "Nous contacter") -> str:
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

            badge = f"<div class='badge'>{e(label)}</div>" if label else ""
            cards.append(f"<div class='card'><div class='meta'>{badge}{''.join(lines)}</div></div>")

    if not cards:
        return f"<h3>{e(heading)}</h3><p class='small'>Aucun contact renseigné.</p>"

    return f"<h3>{e(heading)}</h3><div class='grid'>{''.join(cards)}</div>"

ALLOWED_COVER_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
AVAILABLE_COVERS: set[str] = set()

def compute_available_covers(out_dir: Path) -> set[str]:
    p = out_dir / "covers"
    if not p.exists():
        return set()
    return {
        f.name
        for f in p.iterdir()
        if f.is_file() and f.suffix.lower() in ALLOWED_COVER_EXTS
    }

def is_na(v: Any) -> bool:
    try:
        return v is None or pd.isna(v)
    except Exception:
        return v is None

def as_str(v: Any) -> str:
    if is_na(v):
        return ""
    return str(v).strip()

def parse_pub_date(v: Any) -> Optional[date]:
    """Parse date_parution_norm en date() si possible (YYYY, YYYY-MM, YYYY-MM-DD)."""
    s = as_str(v)
    if not s:
        return None

    # Essai ISO direct (YYYY-MM-DD)
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        pass

    # Accept YYYY, YYYY-MM, YYYY-MM-DD (même si fromisoformat échoue)
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", s)
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2) or 1)
    d = int(m.group(3) or 1)
    try:
        return date(y, mo, d)
    except Exception:
        return None

def months_ago(d: date, months: int) -> date:
    """d - N mois (calendrier), en conservant un jour valide."""
    y, m = d.year, d.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))

def pretty_person_name(s: str) -> str:
    # "Nom, Prénom" -> "Prénom Nom"
    s = (s or "").strip()
    if "," in s:
        parts = [p.strip() for p in s.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{parts[1]} {parts[0]}"
    return s

def format_credit_line(raw: Any) -> str:
    """
    Transforme une chaîne type:
      "Nom, Prénom, B15; Nom2, Prénom2, B15"
    en libellé lisible:
      "Sous la direction de Prénom Nom, Prénom2 Nom2"
    Heuristique:
      - si tous les rôles sont identiques et dans un set 'direction_like', on met "Sous la direction de"
      - sinon, on supprime juste les codes et on liste les noms.
    """
    s = as_str(raw)
    if not s:
        return ""

    chunks = [c.strip() for c in s.split(";") if c.strip()]
    people: List[str] = []
    roles: List[str] = []

    for ch in chunks:
        parts = [p.strip() for p in ch.split(",") if p.strip()]
        if len(parts) >= 2:
            nom = parts[0]
            prenom = parts[1]
            code = parts[2] if len(parts) >= 3 else ""
            people.append(pretty_person_name(f"{nom}, {prenom}"))
            roles.append(code.upper().strip())
        else:
            people.append(ch)
            roles.append("")

    # Codes "direction-like" : à ajuster selon ton export OnixSuite
    direction_like = {"B01", "B15"}

    people_str = ", ".join([p for p in people if p])

    # si tout le monde a un rôle direction_like (et qu'on a au moins un code)
    if people_str and all(r in direction_like for r in roles if r) and any(r for r in roles):
        return f"Sous la direction de {people_str}"

    return people_str

def clean_json_value(v: Any) -> Any:
    if is_na(v):
        return ""
    return v

def e(s: Any) -> str:
    return html.escape(as_str(s), quote=True)

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

def _href_with_rel(href: str, rel: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    # liens externes / mail / ancres : on ne touche pas
    if re.match(r"^(https?://|mailto:|#)", href):
        return href
    # lien relatif : on préfixe avec rel pour que ça marche depuis /collections/, /livres/, etc.
    rel = rel or "."
    return f"{rel}/{href}"

def footer_rich(s: Any, rel: str) -> str:
    s = as_str(s).strip()
    if not s:
        return ""
    out = []
    pos = 0
    for m in MD_LINK_RE.finditer(s):
        # texte avant le lien (échappé)
        out.append(html.escape(s[pos:m.start()], quote=False))
        label = html.escape(m.group(1), quote=False)
        href_raw = _href_with_rel(m.group(2), rel)
        href = html.escape(href_raw, quote=True)

        # target blank uniquement pour http(s)
        extra = " target='_blank' rel='noopener'" if href_raw.startswith("http") else ""
        out.append(f"<a href='{href}'{extra}>{label}</a>")
        pos = m.end()

    out.append(html.escape(s[pos:], quote=False))
    return "".join(out).replace("\n", "<br>")


def to_float(v: Any) -> Optional[float]:
    s = as_str(v)
    if not s:
        return None
    s = s.replace(",", ".")
    s = re.sub(r"[^\d\.]", "", s)
    try:
        return float(s)
    except Exception:
        return None

def fmt_eur(v: Any) -> str:
    f = to_float(v)
    if f is None:
        return ""
    s = f"{f:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{s} €"

def fmt_cm_guess(v: Any) -> str:
    """Interprète v en mm si > 100, sinon en cm (heuristique pratique)."""
    f = to_float(v)
    if f is None:
        return ""
    cm = (f / 10.0) if f > 100 else f
    s = f"{cm:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return s

def fmt_int(v: Any) -> str:
    f = to_float(v)
    if f is None:
        return ""
    try:
        return str(int(round(f)))
    except Exception:
        return ""

def slugify(s: str, max_len: int = 80) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s[:max_len] if s else "item"

def norm_bool(v: Any) -> bool:
    if is_na(v):
        return False
    if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
        return int(v) == 1
    s = str(v).strip().lower()
    return s in {"1", "true", "vrai", "oui", "x", "yes", "y"}

def normalize_id13(v: Any) -> Optional[str]:
    """Normalize ISBN/GTIN to 13 digits; else None."""
    s = as_str(v)
    if not s:
        return None
    # handle scientific notation from Excel
    if "e+" in s.lower():
        try:
            s = str(int(float(s)))
        except Exception:
            pass
    if s.endswith(".0"):
        s = s[:-2]
    s = re.sub(r"\D", "", s)
    return s if len(s) == 13 else None

def parse_year(date_str: Any) -> Optional[int]:
    s = as_str(date_str)
    if not s:
        return None
    m = re.match(r"^(\d{4})", s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None

def md_to_html(text: Any) -> str:
    s = as_str(text)
    if not s:
        return ""
    if md is None:
        # Fallback minimal : on échappe le HTML et on conserve les retours ligne.
        safe = e(s).replace("\n", "<br>")
        return f"<p>{safe}</p>"
    return md.markdown(s, extensions=["extra", "sane_lists"])

def toc_to_html(toc: Any) -> str:
    """Rend la table des matières.
    - Si elle contient déjà du HTML (<p>, <ul>, etc.), on l’insère telle quelle (avec mini-sanitization).
    - Sinon, on l’affiche en texte préformaté.
    """
    s = as_str(toc)
    if not s:
        return ""

    if re.search(r"</?(p|ul|ol|li|br|strong|em|h[1-6])\b", s, flags=re.I):
        s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", s)
        s = re.sub(r"(?i)\son\w+\s*=\s*\"[^\"]*\"", "", s)
        s = re.sub(r"(?i)\son\w+\s*=\s*'[^']*'", "", s)
        return f"<div class='toc'>{s}</div>"

    return f"<pre>{e(s)}</pre>"

def ensure_unique_slug(slug: str, used: set[str]) -> str:
    base = slug
    i = 2
    while slug in used:
        slug = f"{base}-{i}"
        i += 1
    used.add(slug)
    return slug

def looks_urlencoded(s: str) -> bool:
    return bool(re.search(r"%0d|%0a|%20", s, flags=re.I))


# -------------------------
# Default assets
# -------------------------

DEFAULT_CSS = """
:root { --max: 1120px; --accent: #005a9c; --header: #2e2a22; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; line-height: 1.45; color: #111; background: #fafafa; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
header { background: var(--header); color: #fff; position: sticky; top: 0; z-index: 10; }
.wrap { max-width: var(--max); margin: 0 auto; padding: 14px 16px; }
.brand { display:flex; align-items:center; justify-content: space-between; gap: 12px; }
.brand-left { display:flex; align-items:center; gap: 12px; min-width: 0; }
.brand-logos { display:flex; align-items:center; gap: 10px; }
.brand-logos img { display:block; height: 38px; width: auto; }
.brand-text { min-width: 0; }
.brand-title { font-weight: 760; font-size: 1.55rem; line-height: 1.12; }
.brand-sub { color: rgba(255,255,255,0.90); font-size: 1.10rem; font-style: italic; font-weight : 400; margin-top: 3px; }
.nav { display:flex; gap: 18px; margin-top: 10px; align-items:center; flex-wrap: wrap; border-top: 1px solid rgba(255,255,255,0.12); padding-top: 10px; }
.nav a { color: #fff; opacity: 0.92; font-weight: 520; }
.nav a.active { opacity: 1; text-decoration: underline; text-decoration-color: rgba(255,255,255,0.85); text-underline-offset: 3px; }
main.wrap { padding-top: 18px; padding-bottom: 26px; }
h1, h2, h3 { margin: 0.6rem 0 0.4rem; }
.small { color: #444; font-size: 0.95rem; }
.book-subtitle { font-size: 1.12rem; font-weight: 700; font-style: normal; margin-top: 4px; }
.book-credit { font-size: 1.10rem; font-weight: 450; margin-top: 8px; }
.book-meta { margin-top: 10px; }
.book-meta .meta-line { margin: 6px 0; }
.book-meta .meta-label { font-weight: 0; }
.grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; margin-top: 14px; }
.card { background:#fff; border: 1px solid #e6e6e6; border-radius: 12px; padding: 12px; display:flex; gap: 12px; box-shadow: 0 1px 0 rgba(0,0,0,0.02); }
.cover { width: 76px; height: 110px; flex: 0 0 76px; border-radius: 8px; border: 1px solid #eee; background: #f3f3f3; object-fit: cover; }
.meta { flex: 1; min-width: 0; }
.card .meta a { display: block; }
.card .meta a strong {
  font-size: 1.12rem;
  font-weight: 750;
  line-height: 1.2;
}
.card .book-subtitle {
  font-size: 0.98rem;
  font-weight: 650;
  margin-top: 4px;
}
.badges { margin-top: 6px; display:flex; gap: 6px; flex-wrap: wrap; }
.badge { display:inline-block; padding: 2px 8px; border-radius: 999px; border: 1px solid #e1e1e1; font-size: 0.82rem; color:#333; background:#fcfcfc; }
.badge-oa { border-color: var(--accent); font-weight: 650; }
.badges a.badge:hover { text-decoration: none; background:#f3f3f3; }
.toolbar { display:flex; gap: 10px; flex-wrap: wrap; align-items:center; margin: 12px 0; }
input[type="search"], select { padding: 10px 12px; border: 1px solid #cfcfcf; border-radius: 10px; font-size: 1rem; background: #fff; }
input[type="search"] { flex: 1; min-width: 240px; }
.btn { display:inline-block; padding: 10px 12px; border-radius: 10px; border: 1px solid #dedede; background: #fff; color:#111; }
.btn:hover { background:#f3f3f3; text-decoration:none; }
footer { border-top: 1px solid #e5e5e5; background: #fff; }
footer .wrap { color:#666; font-size: 0.9rem; padding-top: 18px; padding-bottom: 18px; }
.footer-grid { display:flex; gap: 18px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
.footer-left { min-width: 260px; }
.footer-left div { margin: 4px 0; }
.footer-right img { height: 56px; width: auto; }
.footer-right a { display:inline-block; }

/* Lightbox (cover) */
.lightbox{
  position: fixed;
  inset: 0;
  display: flex;                 /* ✅ toujours présent */
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 9999;

  opacity: 0;
  visibility: hidden;            /* ✅ caché mais animable */
  pointer-events: none;          /* ✅ pas cliquable quand fermé */
  background: rgba(0,0,0,0.0);

  transition: opacity 320ms ease, background 180ms ease, visibility 0s linear 180ms;
}

.lightbox.open{
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
  background: rgba(0,0,0,0.85);

  transition: opacity 320ms ease, background 180ms ease, visibility 0s;
}

.lightbox img{
  max-width: min(980px, 95vw);
  max-height: 92vh;
  width: auto;
  height: auto;
  border-radius: 12px;
  background: #fff;

  transform: scale(0.96);
  transition: transform 320ms ease;
}

.lightbox.open img{
  transform: scale(1);
}

.lightbox-close{
  position: absolute;
  top: 14px;
  right: 18px;
  font-size: 28px;
  line-height: 1;
  color: #fff;
  cursor: pointer;
  user-select: none;
}

.cover-zoom{ cursor: zoom-in; }

@media (prefers-reduced-motion: reduce){
  .lightbox, .lightbox img { transition: none; }
}

/* Loupe de recherche dans le menu */
.nav-search{
  margin-left: auto;       /* pousse la loupe à droite */
  font-size: 1.15rem;
  opacity: 0.9;
  line-height: 1;
}

.nav-search:hover{
  opacity: 1;
  text-decoration: none;
}

.brand-sub { 
  color: rgba(255,255,255,0.90);
  font-size: 1.10rem;
  font-style: italic;
  font-weight: 400;
  margin-top: 3px;
}

/* Ligne slogan + recherche */
.brand-subrow{
  display:flex;
  align-items:center;
  flex-wrap:wrap;
  gap:12px;
}

/* Le slogan occupe l'espace dispo */
.brand-subtitle-text{
  flex: 1 1 auto;
  min-width: 18ch;     /* évite l’écrasement sur certaines largeurs */
}

/* Le bloc "Rechercher : 🔍" part à droite */
.brand-search-wrap{
  margin-left: auto;   /* <-- la clé */
  padding-left: 24px;  /* <-- espace “respirant” après le slogan */
  white-space: nowrap; /* évite le retour à la ligne au milieu */
  font-style: normal;
}



/* Mobile : réduire le bandeau pour rendre le scroll confortable */
@media (max-width: 720px){
  header .wrap{ padding: 8px 12px; }
  .brand-title{ font-size: 1.15rem; }
  .brand-sub{ font-size: 0.95rem; margin-top: 2px; }
  .brand-logos img{ height: 28px !important; } /* override la hauteur config */

  /* Menu sur 1 ligne, scrollable horizontalement */
  .nav{
    flex-wrap: nowrap;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    gap: 12px;
    margin-top: 8px;
    padding-top: 8px;
  }

  /* Option : gagner encore + de place */
  /* .brand-subtitle-text{ display:none; } */
}


hr { border:0; border-top:1px solid #e6e6e6; margin: 18px 0; }
.kv { display:grid; grid-template-columns: 150px 1fr; gap: 10px 14px; margin: 14px 0; }
.k { color:#555; }
pre { white-space: pre-wrap; background:#fff; border:1px solid #eee; border-radius: 12px; padding: 12px; }
"""

DEFAULT_JS = r"""
const PAGE_SIZE = 60;
let limit = PAGE_SIZE;
let timer = null;

async function loadCatalogue() {
  const res = await fetch("./assets/catalogue.json");
  return await res.json();
}
function esc(s){return String(s||"")
  .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
  .replaceAll('"',"&quot;").replaceAll("'","&#039;");}
function normalize(s){return (s||"").toLowerCase().trim();}

function card(r){
  const cover = r.cover
    ? `<img class="cover"
        src="./covers/${esc(r.cover)}"
        alt=""
        loading="lazy"
        decoding="async"
        fetchpriority="low"
        onerror="this.style.display='none'">`
    : `<div class="cover"></div>`;

  const physical = r.physical ? `<div class="small">${esc(r.physical)}</div>` : "";
  const subtitle = r.subtitle ? `<div class="book-subtitle">${esc(r.subtitle)}</div>` : "";
  const credit = r.credit ? `<div class="book-credit">${esc(r.credit)}</div>` : "";
  const badges = [
    r.collection ? `<span class="badge">${esc(r.collection)}</span>` : "",
    r.format ? `<span class="badge">${esc(r.format)}</span>` : "",
    r.openedition_url ? `<span class="badge badge-oa">Open access</span>` : "",
  ].filter(Boolean).join("");
  const price = r.price ? `<div class="small">Prix : ${esc(r.price)}</div>` : "";
  const avail = r.availability ? `<div class="small">${esc(r.availability)}</div>` : "";
  const excerpt = r.excerpt ? `<div class="small">${esc(r.excerpt)}</div>` : "";

  return `<div class="card">
    ${cover}
    <div class="meta">
      <a href="./livres/${esc(r.slug)}.html"><strong>${esc(r.title)}</strong></a>
      ${subtitle}
      ${credit}
      <div class="badges">${badges}</div>
      ${price}${avail}${physical}
      ${excerpt}
    </div>
  </div>`;
}

function buildOptions(values, placeholder){
  const opts = [`<option value="">${esc(placeholder)}</option>`];
  for(const v of values){ opts.push(`<option value="${esc(v)}">${esc(v)}</option>`); }
  return opts.join("");
}
function uniqueSorted(arr){
  return Array.from(new Set(arr.filter(Boolean))).sort((a,b)=>String(a).localeCompare(String(b), "fr"));
}
function filterRecs(recs, q, col, fmt, year){
  const Q = normalize(q);
  return recs.filter(r=>{
    if(col && r.collection !== col) return false;
    if(fmt && r.format !== fmt) return false;
    if(year && String(r.year) !== String(year)) return false;
    if(!Q) return true;
    const hay = [r.title,r.subtitle,r.credit,r.collection,r.format,r.id13].map(x=>normalize(x)).join(" ");
    return hay.includes(Q);
  });
}

async function main(){
  const recs = await loadCatalogue();
  const q = document.getElementById("q");
  const out = document.getElementById("out");
  const count = document.getElementById("count");
  const selCol = document.getElementById("f_collection");
  const selFmt = document.getElementById("f_format");
  const selYear = document.getElementById("f_year");
  const more = document.getElementById("more");

  const cols = uniqueSorted(recs.map(r=>r.collection));
  const fmts = uniqueSorted(recs.map(r=>r.format));
  const years = uniqueSorted(recs.map(r=>r.year)).reverse();

  selCol.innerHTML = buildOptions(cols, "Toutes les collections");
  selFmt.innerHTML = buildOptions(fmts, "Tous les formats");
  selYear.innerHTML = buildOptions(years, "Toutes les années");

  function render(){
    const filtered = filterRecs(recs, q.value, selCol.value, selFmt.value, selYear.value);
    count.textContent = String(filtered.length);

    const shown = filtered.slice(0, limit);
    out.innerHTML = shown.map(card).join("");

    if(more){
      more.style.display = (filtered.length > limit) ? "inline-block" : "none";
    }
  }

  function scheduleRender(resetLimit){
    if(resetLimit) limit = PAGE_SIZE;
    if(timer) clearTimeout(timer);
    timer = setTimeout(()=>{ timer=null; render(); }, 140);
  }

  [q, selCol, selFmt, selYear].forEach(el=>el.addEventListener("input", ()=>scheduleRender(true)));

  if(more){
    more.addEventListener("click", (e)=>{
      e.preventDefault();
      limit += PAGE_SIZE;
      render();
    });
  }

  render();
}
main();
"""


LIGHTBOX_HTML = r"""
<div id="lightbox" class="lightbox" aria-hidden="true">
  <div class="lightbox-close" id="lightboxClose" title="Fermer">×</div>
  <img id="lightboxImg" alt="">
</div>

<script>
(function(){
  const lb = document.getElementById("lightbox");
  const lbImg = document.getElementById("lightboxImg");
  const lbClose = document.getElementById("lightboxClose");

  let closeTimer = null;
  
  function open(src){
    if(!src) return;
    if(closeTimer){ clearTimeout(closeTimer); closeTimer = null; }
    lbImg.src = src;
    lb.classList.add("open");
    document.body.style.overflow = "hidden";
  }
  function close(){
  lb.classList.remove("open");
  document.body.style.overflow = "";
  if(closeTimer) clearTimeout(closeTimer);
  closeTimer = setTimeout(()=>{
    lbImg.src = "";
    closeTimer = null;
  }, 330);
  }
  
  lb.addEventListener("click", (e)=>{ if(e.target === lb) close(); });
  lbClose.addEventListener("click", close);
  document.addEventListener("keydown", (e)=>{ if(e.key === "Escape") close(); });

  document.addEventListener("click", (e)=>{
    const a = e.target.closest("[data-lightbox-src]");
    if(!a) return;
    e.preventDefault();
    open(a.getAttribute("data-lightbox-src"));
  });
})();
</script>
"""

# -------------------------
# Data models
# -------------------------

@dataclasses.dataclass
class SiteConfig:
    # Branding
    site_title: str = "Presses universitaires"
    site_subtitle: str = "Catalogue"
    accent_color: str = "#005a9c"
    header_bg: str = "#2e2a22"

    # Logos / favicon (fichiers copiés vers dist/assets)
    logo_left: str = ""     # ex: assets/logo.png
    logo_right: str = ""    # ex: assets/partner.png
    logo_left_link: str = ""
    logo_right_link: str = ""
    logo_height: int = 38
    favicon: str = ""       # ex: assets/favicon.ico

    # Contact / footer
    contact_email: str = ""
    footer_text: str = "Site généré automatiquement."
    footer_copyright: str = ""
    footer_conceptor: str = ""  # ex: "Conception : …"
    footer_legal: str = ""  # ex: "Mentions légales : …" ou URL
    footer_logo: str = ""  # ex: assets/logo-univ.png (copié dans dist/assets)
    footer_logo_alt: str = ""
    footer_logo_href: str = ""  # lien éventuel vers l’université

    # Excel settings
    books_sheet: str = ""    # name of catalogue sheet; if empty auto-detect
    pages_sheet: str = "PAGES"
    collections_sheet: str = "COLLECTIONS"
    revues_sheet: str = "REVUES"
    contacts_sheet: str = "CONTACTS"
    config_sheet: str = "CONFIG"

    # Home / Nouveautés
    home_feature_count: int = 12
    new_titles_count: int = 25
    new_months: int = 6

    # Display toggles
    show_price: bool = True
    show_availability: bool = True

    # Order button mode
    order_mode: str = "mailto"      # mailto | url | pdf
    order_pdf_filename: str = ""    # if pdf
    order_url_template: str = ""    # if url template, can use {id13}
    order_mail_subject: str = "Commande"
    order_mail_body: str = "Bonjour,\n\nJe souhaite commander : {title} ({id13}).\n\nMerci."

    # Menu - plusieurs actuellement inactifs mais utilisables
    menu_label_presentation: str = "Présentation"
    menu_label_soumettre: str = "Soumettre un manuscrit"
    menu_label_a_paraitre: str = "À paraître"
    menu_label_catalogue: str = "Catalogue"
    menu_label_revues: str = "Revues"
    menu_label_collections: str = "Collections"
    menu_label_open_access: str = "Open Access"
    menu_label_commandes: str = "Commandes/contacts"
    menu_label_actualites: str = "Actualités"

    # FTP publish (optionnel)
    ftp_host: str = ""
    ftp_user: str = ""
    ftp_password: str = ""
    ftp_remote_dir: str = ""     # ex: /www/site/
    ftp_port: int = 21
    ftp_tls: bool = False
    ftp_passive: bool = True
    ftp_clean: bool = False


def load_config(wb: pd.ExcelFile, sheet_name: str) -> SiteConfig:
    cfg = SiteConfig()
    if sheet_name not in wb.sheet_names:
        return cfg

    df = wb.parse(sheet_name=sheet_name)

    # accept columns: key/value or Clé/Valeur
    cols = [str(c).lower().strip() for c in df.columns]
    key_col = None
    val_col = None
    for i, c in enumerate(cols):
        if c in {"key", "cle", "clé"}:
            key_col = df.columns[i]
        if c in {"value", "valeur"}:
            val_col = df.columns[i]
    if key_col is None or val_col is None:
        if len(df.columns) >= 2:
            key_col, val_col = df.columns[0], df.columns[1]
        else:
            return cfg

    kv: Dict[str, Any] = {}
    for _, r in df.iterrows():
        k = r.get(key_col)
        v = r.get(val_col)
        k = as_str(k)
        if not k:
            continue
        kv[k] = "" if is_na(v) else v

    # Aliases (compat templates)
    # - priorité aux clés explicites "logo_file_left/right"
    # - compat pour les anciens noms de clés
    alias = {
        "brand_accent_color": "accent_color",
        "favicon_file": "favicon",
        "contact_email_default": "contact_email",
        "order_mode_default": "order_mode",
    }
    for k, v in list(kv.items()):
        if k in alias and alias[k] not in kv:
            kv[alias[k]] = v

    # Logos : priorité à logo_file_left/right, puis fallback à logo_file
    if as_str(kv.get("logo_file_left")):
        kv["logo_left"] = kv.get("logo_file_left")
    elif as_str(kv.get("logo_file")) and not as_str(kv.get("logo_left")):
        kv["logo_left"] = kv.get("logo_file")

    if as_str(kv.get("logo_file_right")):
        kv["logo_right"] = kv.get("logo_file_right")
    # Map keys to dataclass fields when possible
    for field in dataclasses.fields(cfg):
        if field.name not in kv:
            continue
        raw = kv[field.name]

        # bool
        if field.type == bool or str(field.type) in {"bool", "<class 'bool'>"}:
            setattr(cfg, field.name, norm_bool(raw))
            continue

        # int
        if field.type == int or str(field.type) in {"int", "<class 'int'>"}:
            try:
                setattr(cfg, field.name, int(float(raw)))
            except Exception:
                pass
            continue

        # str
        setattr(cfg, field.name, as_str(raw))

    # Unquote mail body if template stored URL-encoded
    if cfg.order_mail_body and looks_urlencoded(cfg.order_mail_body):
        try:
            cfg.order_mail_body = unquote(cfg.order_mail_body)
        except Exception:
            pass

    # Normalize logo paths: if value is just a filename -> assets/<filename>
    for attr in ("logo_left", "logo_right", "favicon", "footer_logo"):
        val = getattr(cfg, attr)
        if val and "/" not in val and "\\" not in val:
            setattr(cfg, attr, f"assets/{val}")

    return cfg


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
    css = re.sub(r"\.brand-logos img \{[^}]*\}", f".brand-logos img {{ display:block; height: {int(cfg.logo_height)}px; width: auto; }}", css)

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

def book_order_block(cfg: SiteConfig, rec: Dict[str, Any]) -> str:
    title = rec.get("title", "")
    id13 = rec.get("id13", "")
    if cfg.order_mode == "pdf" and cfg.order_pdf_filename:
        return f'<p><a class="btn" href="../assets/{e(cfg.order_pdf_filename)}">Commander (bon de commande)</a></p>'
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
    return df

def load_collections(wb: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    if sheet not in wb.sheet_names:
        return pd.DataFrame()
    df = wb.parse(sheet_name=sheet)
    for c in ["collection_id", "name", "slug", "description_md", "directeurs", "comite_scientifique", "is_active"]:
        if c not in df.columns:
            df[c] = None
    return df

def load_revues(wb: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    if sheet not in wb.sheet_names:
        return pd.DataFrame()
    df = wb.parse(sheet_name=sheet)
    for c in ["journal_id", "title", "slug", "url", "issn_print", "issn_online", "description_md", "direction", "contact_email", "is_active"]:
        if c not in df.columns:
            df[c] = None
    return df

def load_contacts(wb: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    if sheet not in wb.sheet_names:
        return pd.DataFrame()
    df = wb.parse(sheet_name=sheet)
    for c in ["label", "name", "role", "email", "phone", "address", "order", "is_active"]:
        if c not in df.columns:
            df[c] = None
    return df

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

    df["credit_ligne"] = df["credit_ligne"].fillna("").apply(format_credit_line)
    df["id13"] = df["id13"].apply(normalize_id13)
    df["openedition_url"] = df["openedition_url"].fillna("").apply(as_str)

    # --- COLLECTION_ID : garantir un identifiant exploitable
    df["collection_id"] = df["collection_id"].apply(lambda x: slugify(as_str(x)) if as_str(x) else None)
    missing_cid = df["collection_id"].isna() | (df["collection_id"].astype(str).str.strip() == "")
    df.loc[missing_cid, "collection_id"] = df.loc[missing_cid, "collection"].apply(lambda x: slugify(as_str(x)) if as_str(x) else None)

    df["year"] = df["date_parution_norm"].apply(parse_year)
    df["pub_date"] = df["date_parution_norm"].apply(parse_pub_date)

    # Build slugs
    used: set[str] = set()
    out_slugs: List[str] = []
    for _, r in df.iterrows():
        s = as_str(r.get("slug"))
        if not s:
            t = as_str(r.get("titre_norm") or r.get("Titre") or "ouvrage")
            base = slugify(t)
            if r.get("id13"):
                base = f"{base}-{r.get('id13')}"
            s = base
        s = ensure_unique_slug(slugify(str(s)), used)
        out_slugs.append(s)
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


# -------------------------
# Build site
# -------------------------

def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def copy_covers(covers_dir: Path, out_dir: Path) -> None:
    if not covers_dir.exists():
        return
    dest = out_dir / "covers"
    dest.mkdir(parents=True, exist_ok=True)

    for src in covers_dir.iterdir():
        if not (src.is_file() and src.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}):
            continue

        dst = dest / src.name

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

def resolve_asset_source(excel_dir: Path, asset_rel: str) -> Optional[Path]:
    """Retrouve un fichier déclaré dans CONFIG (logo/favicon/pdf) à partir du dossier du classeur."""
    if not asset_rel:
        return None
    rel = asset_rel.replace("\\", "/")
    # si on a "assets/foo.png", on testera excel_dir/assets/foo.png et excel_dir/foo.png
    candidates = [
        excel_dir / rel,
        excel_dir / Path(rel).name,
        excel_dir / "assets" / Path(rel).name,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None

def copy_declared_assets(excel_path: Path, out_dir: Path, cfg: SiteConfig) -> None:
    excel_dir = excel_path.parent
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)

    declared = [cfg.logo_left, cfg.logo_right, cfg.favicon, cfg.footer_logo]
    if cfg.order_mode == "pdf" and cfg.order_pdf_filename:
        declared.append(f"assets/{cfg.order_pdf_filename}" if "/" not in cfg.order_pdf_filename else cfg.order_pdf_filename)

    for rel in declared:
        rel = as_str(rel)
        if not rel:
            continue
        src = resolve_asset_source(excel_dir, rel)
        if not src:
            continue
        dest = out_dir / rel.replace("\\", "/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

def build_catalogue_json(books: pd.DataFrame, out_dir: Path) -> None:
    recs = []
    for _, r in books.iterrows():
        # Année: garantir une valeur lisible (éviter '2025.0')
        y = r.get('year')
        year_str = ""
        if y is not None and not pd.isna(y):
            try:
                year_str = str(int(float(y)))
            except Exception:
                year_str = str(y).strip()
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
            "cover": clean_json_value(r.get("cover_file")) or "",
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
    datep = as_str(r.get("date_parution_norm"))
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

def build_home(cfg: SiteConfig, books: pd.DataFrame, out_dir: Path) -> None:
    df = books.copy()

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
    write_file(out_dir / "catalogue.html", page_shell(cfg, f"{cfg.site_title} — {cfg.menu_label_catalogue}", "catalogue", body, "."))

def build_new_titles(cfg: SiteConfig, recent: pd.DataFrame, out_dir: Path, new_months: int) -> None:
    df = recent.copy()

    if df.empty:
        body = f"""
<h2>Nouveautés</h2>
<p class="small">Aucun titre paru dans les {int(new_months)} derniers mois.</p>
"""
        write_file(out_dir / "nouveautes.html", page_shell(cfg, f"{cfg.site_title} — Nouveautés", "nouveautes", body, "."))
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

def build_book_pages(cfg: SiteConfig, books: pd.DataFrame, out_dir: Path) -> None:
    livres_dir = out_dir / "livres"
    livres_dir.mkdir(parents=True, exist_ok=True)

    for _, r in books.iterrows():
        title = as_str(r.get("titre_norm"))
        subtitle = as_str(r.get("sous_titre_norm"))
        credit = as_str(r.get("credit_ligne"))
        collection = as_str(r.get("collection"))
        fmt = as_str(r.get("format_site"))
        datep = as_str(r.get("date_parution_norm"))
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
        write_file(livres_dir / f"{as_str(r.get('slug'))}.html", page_shell(cfg, f"{cfg.site_title} — {title}", "catalogue", body, ".."))

def build_collections(cfg: SiteConfig, books: pd.DataFrame, collections: pd.DataFrame, out_dir: Path) -> None:
    base = out_dir / "collections"
    base.mkdir(parents=True, exist_ok=True)

    if collections.empty:
        names = sorted({as_str(x) for x in books["collection"].dropna().tolist() if as_str(x)})
        rows = []
        for n in names:
            cid = slugify(n)
            rows.append({"collection_id": cid, "name": n, "slug": cid, "description_md": "", "directeurs": "", "comite_scientifique": "", "is_active": 1})
        collections = pd.DataFrame(rows)

    collections = collections.copy()
    collections["is_active"] = collections.get("is_active", 1).apply(norm_bool)
    collections["collection_id"] = collections["collection_id"].apply(lambda x: slugify(as_str(x)) if as_str(x) else None)
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

        dfb = books.copy()
        if "collection_id" in dfb.columns and cid:
            dfb = dfb[dfb["collection_id"] == cid]
        else:
            dfb = dfb[dfb["collection"] == name]

        dfb = dfb.sort_values(["year", "titre_norm"], ascending=[False, True])

        cards = [_book_card_html(r, "..", cfg) for _, r in dfb.iterrows()]
        cards_html = f"<div class='grid'>{chr(10).join(cards)}</div>" if cards else "<p class='small'>Aucun ouvrage rattaché trouvé (vérifier collection_id dans le catalogue).</p>"

        meta = []
        if directeurs:
            meta.append(f"<div class='kv'><div class='k'>Direction</div><div>{e(directeurs)}</div></div>")
        if comite:
            meta.append(f"<div class='kv'><div class='k'>Comité scientifique</div><div>{e(comite)}</div></div>")

        body = f"""
<h2>{e(name)}</h2>
{''.join(meta)}
{desc if desc else ""}
<h3>Ouvrages rattachés</h3>
{cards_html}
"""
        slug = as_str(c.get("slug") or cid)
        write_file(base / f"{slug}.html", page_shell(cfg, f"{cfg.site_title} — {name}", "collections", body, ".."))

def build_revues(cfg: SiteConfig, revues: pd.DataFrame, out_dir: Path) -> None:
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
    df["slug"] = df["slug"].apply(lambda x: slugify(as_str(x)) if as_str(x) else slugify(as_str(x or "revue")))
    df["title"] = df["title"].apply(as_str)
    df = df.sort_values("title")

    lis = []
    for _, r in df.iterrows():
        lis.append(f'<li><a href="./{e(r.get("slug"))}.html">{e(r.get("title"))}</a></li>')
    body = f"""
<h2>{e(cfg.menu_label_revues)}</h2>
<ul>
{chr(10).join(lis)}
</ul>
"""
    write_file(base / "index.html", page_shell(cfg, f"{cfg.site_title} — Revues", "revues", body, ".."))

    for _, r in df.iterrows():
        title = as_str(r.get("title"))
        url = as_str(r.get("url"))
        issnp = as_str(r.get("issn_print"))
        issno = as_str(r.get("issn_online"))
        direction = as_str(r.get("direction"))
        mail = as_str(r.get("contact_email"))
        desc = md_to_html(r.get("description_md") or "")

        meta = []
        if url:
            meta.append(f"<div class='kv'><div class='k'>Site</div><div><a href='{e(url)}' target='_blank' rel='noopener'>{e(url)}</a></div></div>")
        if issnp:
            meta.append(f"<div class='kv'><div class='k'>ISSN (papier)</div><div>{e(issnp)}</div></div>")
        if issno:
            meta.append(f"<div class='kv'><div class='k'>ISSN (en ligne)</div><div>{e(issno)}</div></div>")
        if direction:
            meta.append(f"<div class='kv'><div class='k'>Direction</div><div>{e(direction)}</div></div>")
        if mail:
            meta.append(f"<div class='kv'><div class='k'>Contact</div><div><a href='mailto:{e(mail)}'>{e(mail)}</a></div></div>")

        body = f"""
<h2>{e(title)}</h2>
{''.join(meta)}
{desc if desc else ""}
"""
        write_file(base / f"{as_str(r.get('slug'))}.html", page_shell(cfg, f"{cfg.site_title} — {title}", "revues", body, ".."))

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
            cards.append(f"<div class='card'><div class='meta'><div class='badge'>{e(label)}</div>{''.join(lines)}</div></div>")

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

    for slug, title, key in [("open-access", cfg.menu_label_open_access, "open_access"),
                            ("actualites", cfg.menu_label_actualites, "actualites")]:
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
        if not as_str(r.get("cover_file")):
            issues.append("Couverture manquante (cover_file)")
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


# -------------------------
# FTP publish (optionnel)
# -------------------------

def publish_ftp(cfg: SiteConfig, local_dir: Path, progress_cb=None) -> None:
    """Publie local_dir en FTP/FTPS, en créant les dossiers distants si besoin.
       progress_cb(event: dict) optionnel, appelé pendant le transfert.
    """
    import ftplib
    import time

    def emit(**evt):
        if progress_cb:
            try:
                progress_cb(evt)
            except Exception:
                pass

    host = as_str(cfg.ftp_host)
    user = as_str(cfg.ftp_user)
    password = as_str(cfg.ftp_password)
    remote_dir = as_str(cfg.ftp_remote_dir)
    port = int(cfg.ftp_port or 21)

    if not host or not user or not password or not remote_dir:
        raise ValueError("FTP incomplet : renseigner ftp_host / ftp_user / ftp_password / ftp_remote_dir dans CONFIG.")

    ftp = ftplib.FTP_TLS() if cfg.ftp_tls else ftplib.FTP()
    ftp.connect(host=host, port=port, timeout=30)
    ftp.login(user=user, passwd=password, secure=False)
    ftp.set_pasv(bool(cfg.ftp_passive))

    def cwd_mkdir(path: str) -> None:
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        if path.startswith("/"):
            ftp.cwd("/")
        for p in parts:
            try:
                ftp.cwd(p)
            except Exception:
                ftp.mkd(p)
                ftp.cwd(p)

    # --- Préparer la liste des fichiers à transférer (pour un vrai % global)
    local_dir = local_dir.resolve()
    files = []
    total_bytes = 0

    for root, dirs, fns in os.walk(local_dir):
        root_p = Path(root)
        for fn in fns:
            if fn.lower().endswith(".log"):
                continue
            lp = root_p / fn
            if not lp.is_file():
                continue
            sz = lp.stat().st_size
            rel_dir = root_p.relative_to(local_dir).as_posix()
            files.append((lp, rel_dir, fn, sz))
            total_bytes += sz

    emit(type="ftp_start", remote_dir=remote_dir, total_files=len(files), total_bytes=total_bytes)

    # --- Aller dans la racine distante une fois
    cwd_mkdir(remote_dir)

    uploaded = 0
    skipped = 0
    errors = 0
    sent_total = 0

    # Throttle UI (évite 10 000 updates/seconde)
    last_emit = 0.0
    def maybe_emit_progress(file_sent, file_size, idx, relpath):
        nonlocal last_emit
        now = time.time()
        if now - last_emit >= 0.08:  # 80ms
            last_emit = now
            emit(
                type="progress",
                i=idx, n=len(files),
                relpath=relpath,
                file_sent=file_sent, file_size=file_size,
                sent_total=sent_total, total_bytes=total_bytes
            )

    for idx, (lp, rel_dir, fn, sz) in enumerate(files, start=1):
        # Se positionner dans le bon sous-dossier distant
        if rel_dir and rel_dir != ".":
            cwd_mkdir(remote_dir.rstrip("/") + "/" + rel_dir)
        else:
            cwd_mkdir(remote_dir)

        relpath = f"{rel_dir}/{fn}" if rel_dir and rel_dir != "." else fn
        emit(type="file_start", i=idx, n=len(files), relpath=relpath, file_size=sz)

        # Skip si même taille distante (si SIZE disponible)
        try:
            rsize = ftp.size(fn)
            if rsize is not None and int(rsize) == sz:
                skipped += 1
                # on retire ce poids du total pour garder un % global exact
                total_bytes -= sz
                emit(type="file_skip", i=idx, n=len(files), relpath=relpath, file_size=sz,
                     sent_total=sent_total, total_bytes=total_bytes)
                continue
        except Exception:
            pass

        file_sent = 0

        def cb(block: bytes):
            nonlocal file_sent, sent_total
            nbytes = len(block)
            file_sent += nbytes
            sent_total += nbytes
            maybe_emit_progress(file_sent, sz, idx, relpath)

        try:
            with open(lp, "rb") as f:
                ftp.storbinary(f"STOR {fn}", f, blocksize=64 * 1024, callback=cb)
            uploaded += 1
            emit(type="file_done", i=idx, n=len(files), relpath=relpath, file_size=sz,
                 sent_total=sent_total, total_bytes=total_bytes)
        except Exception as e:
            errors += 1
            emit(type="file_error", i=idx, n=len(files), relpath=relpath, error=str(e))

        # Revenir proprement à la racine distante (évite surprises)
        cwd_mkdir(remote_dir)

    emit(type="ftp_done", remote_dir=remote_dir, uploaded=uploaded, skipped=skipped, errors=errors,
         sent_total=sent_total, total_bytes=total_bytes)

    print(f"FTP -> {remote_dir} : {uploaded} envoyé(s), {skipped} ignoré(s), {errors} erreur(s).")

    try:
        ftp.quit()
    except Exception:
        ftp.close()


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

    # output dir reset
    if out_dir.exists():
        for child in out_dir.iterdir():
            if child.name == "covers":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    (out_dir / "covers").mkdir(parents=True, exist_ok=True)

    # covers (copie d'abord pour savoir ce qui existe vraiment)
    if covers_dir:
        copy_covers(covers_dir, out_dir)

    # inventaire des covers réellement présentes dans dist/covers
    global AVAILABLE_COVERS
    AVAILABLE_COVERS = compute_available_covers(out_dir)

    # catalogue.json (ne listera que les covers existantes)
    build_catalogue_json(books, out_dir)


    # copy logos/favicon/pdf if declared
    copy_declared_assets(excel_path, out_dir, cfg)

    # validation report always produced
    build_validation_report(books, out_dir)
    if validate_only:
        return

    today = date.today()
    cutoff = months_ago(today, new_months)

    upcoming = books[books["pub_date"].isna() | (books["pub_date"] > today)].copy()
    recent = books[
        books["pub_date"].notna() &
        (books["pub_date"] <= today) &
        (books["pub_date"] >= cutoff)
    ].copy()

    featured = books[books["home_featured"].apply(norm_bool)].copy() if "home_featured" in books.columns else books.iloc[0:0].copy()
    home_books = pd.concat([recent, featured], ignore_index=True).drop_duplicates(subset=["slug"])

    # Build pages
    build_pages(cfg, pages, contacts, out_dir)
    build_home(cfg, home_books, out_dir)
    build_catalogue_page(cfg, out_dir)
    build_new_titles(cfg, recent, out_dir, new_months)
    build_upcoming_page(cfg, upcoming, out_dir)
    # build_contacts(cfg, contacts, out_dir)

    build_book_pages(cfg, books, out_dir)
    build_collections(cfg, books, collections, out_dir)
    build_revues(cfg, revues, out_dir)

    if publish:
        publish_ftp(cfg, out_dir, progress_cb=progress_cb)


def main():
    ap = argparse.ArgumentParser()

    # options ONIX
    ap.add_argument("--export-onix", action="store_true", help="Générer un export ONIX 3.0")
    ap.add_argument("--onix-out", default=None, help="Chemin du fichier ONIX XML de sortie")
    ap.add_argument("--onix-report", default=None, help="Chemin du CSV de contrôle (erreurs/alertes)")
    ap.add_argument("--onix-strict", action="store_true", help="Mode strict (échec si champs requis manquants)")

    ap.add_argument("--excel", required=True, help="Chemin du classeur Excel")
    ap.add_argument("--out", default="dist", help="Dossier de sortie")
    ap.add_argument("--covers-dir", default="", help="Dossier contenant les couvertures (images)")
    ap.add_argument("--validate-only", action="store_true", help="Ne génère que validation.csv + catalogue.json")
    ap.add_argument("--new-months", type=int, default=None,
                    help="Fenêtre (en mois) pour les nouveautés (par défaut : valeur CONFIG.new_months)")

    ap.add_argument("--publish-ftp", action="store_true", help="Publier le dossier de sortie en FTP/FTPS (selon CONFIG)")
    args = ap.parse_args()

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
        from export_onix import export_onix_from_excel
        import os  # assure-toi que c'est aussi importé en haut du fichier si tu préfères

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


if __name__ == "__main__":
    main()
