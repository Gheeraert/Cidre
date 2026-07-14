# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
# Module extrait de build_site.py (découpage sans changement fonctionnel).

from __future__ import annotations

import calendar
import html
import math
import re
import unicodedata
from datetime import datetime, date
from pathlib import Path
from typing import Any, List, Optional

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


# Excel enregistre les retours chariot (\r) sous forme d'échappement OOXML "_x000D_" ;
# openpyxl ne décode pas cet échappement à la lecture, la séquence arrive donc
# littéralement dans les cellules. Le lookbehind préserve "_x005F_x000D_"
# (échappement d'un "_x000D_" voulu comme texte littéral).
OOXML_CR_RE = re.compile(r"(?<!_x005F)_x000[dD]_[ \t]*\n?")
# Transition entre une fermeture de balise de bloc et la balise suivante :
# inutile d'y conserver plusieurs lignes vides.
BLOCK_TAG_TRANSITION_RE = re.compile(
    r"(</(?:p|div|ul|ol|li|h[1-6]|table|thead|tbody|tr|td|blockquote)>)\n{2,}(?=<)",
    re.I,
)


def normalize_excel_text(v: Any) -> str:
    """Nettoie un contenu éditorial lu depuis Excel.

    - convertit les fins de ligne réelles \r\n / \r en \n ;
    - convertit chaque "_x000D_" (retour chariot OOXML non décodé) en \n,
      en absorbant l'espace ou le \n qui le suit pour ne pas doubler le saut ;
    - supprime les espaces autour des sauts de ligne ;
    - limite les sauts consécutifs à une ligne vide au plus ;
    - compacte les transitions entre balises HTML de bloc (</p>\n\n<p> -> </p>\n<p>).

    Les accents, apostrophes, espaces insécables et balises HTML sont préservés.
    """
    s = as_str(v)
    if not s:
        return ""
    if "\r" not in s and "\n" not in s and "_x000" not in s:
        return s
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = OOXML_CR_RE.sub("\n", s)
    s = re.sub(r"[ \t]*\n[ \t]*", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = BLOCK_TAG_TRANSITION_RE.sub(r"\1\n", s)
    return s.strip()


def normalize_editorial_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Applique normalize_excel_text aux colonnes éditoriales présentes dans df."""
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(normalize_excel_text)
    return df


def fmt_display_date(v: Any) -> str:
    """Affiche proprement une date Excel/pandas sans l'heure parasite."""
    if is_na(v):
        return ""

    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")

    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")

    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")

    s = as_str(v)

    # Cas fréquents : "2026-04-10 14:30", "2026-04-10T14:30:00Z".
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[ T]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?$", s)
    if m:
        return m.group(1)

    return s

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

def normalize_external_url(v: Any) -> str:
    u = as_str(v).strip()
    if not u:
        return ""
    if re.search(r"\s", u):
        return ""  # sécurité : pas d'espaces dans une URL
    if re.match(r"^(https?://|mailto:)", u, flags=re.I):
        return u
    # tolérance : "www..." ou "domaine.tld/..."
    if u.startswith("www."):
        return "https://" + u
    if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(/|$)", u, flags=re.I):
        return "https://" + u
    return ""

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

TAG_STRIP_RE = re.compile(r"(?s)<[^>]*>")

def sanitize_html_fragment(s: str) -> str:
    """Sanitization légère : enlève script/style et attributs on*."""
    s = s or ""
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", s)
    s = re.sub(r"(?i)\son\w+\s*=\s*\"[^\"]*\"", "", s)
    s = re.sub(r"(?i)\son\w+\s*=\s*'[^']*'", "", s)
    return s

_ACTU_A_OPEN_RE = re.compile(r"(?is)<a\b[^>]*>")
_ACTU_SPAN_OPEN_RE = re.compile(r"(?is)<span\b[^>]*>")
_ACTU_HREF_RE = re.compile(r"""(?is)\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_ACTU_CLASS_RE = re.compile(r"""(?is)\bclass\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def sanitize_actu_html(s: str) -> str:
    """Sanitization des fragments HTML d'actualités.

    En plus de sanitize_html_fragment (script/style, attributs on*) :
    - <a> : seules les URL http:// et https:// sont conservées ; les autres
      protocoles (javascript:, data:, …) sont supprimés avec tous les
      attributs de la balise. Les liens conservés reçoivent
      target="_blank" rel="noopener" (convention du site pour les liens
      externes) et leur href est ré-échappé ;
    - <span> : seule la classe small-caps est conservée ; toute autre
      classe ou attribut est retiré.
    Les balises légères (<em>, <i>, <strong>, <b>, <p>, <br>…) passent
    telles quelles, comme avant.
    """
    s = sanitize_html_fragment(s or "")

    def _fix_a(m: re.Match) -> str:
        hm = _ACTU_HREF_RE.search(m.group(0))
        href = html.unescape((hm.group(1) or hm.group(2) or "")).strip() if hm else ""
        if re.match(r"^https?://", href, flags=re.I) and not re.search(r"\s", href):
            return (f"<a href='{html.escape(href, quote=True)}'"
                    " target='_blank' rel='noopener'>")
        return "<a>"  # protocole non autorisé ou href absent : lien neutralisé

    def _fix_span(m: re.Match) -> str:
        cm = _ACTU_CLASS_RE.search(m.group(0))
        cls = (cm.group(1) or cm.group(2) or "").strip() if cm else ""
        if cls == "small-caps":
            return "<span class='small-caps'>"
        return "<span>"

    s = _ACTU_A_OPEN_RE.sub(_fix_a, s)
    s = _ACTU_SPAN_OPEN_RE.sub(_fix_span, s)
    return s


def html_to_text(s: str) -> str:
    """Texte brut à partir d'un fragment HTML."""
    s = (s or "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    s = TAG_STRIP_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

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



def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def resolve_asset_source(excel_dir: Path, asset_rel: str) -> Optional[Path]:
    """Retrouve un fichier déclaré dans CONFIG (logo/favicon/pdf) à partir du dossier du classeur."""
    if not asset_rel:
        return None
    rel = asset_rel.replace("\\", "/")
    # si on a "assets/foo.png", on testera excel_dir/assets/foo.png et excel_dir/foo.png
    candidates = [excel_dir / rel]
    if rel.startswith("assets/"):
        # ancien emplacement sans le préfixe assets/ (ex: docs/fichier.pdf à côté du classeur)
        candidates.append(excel_dir / rel[len("assets/"):])
    candidates += [
        excel_dir / Path(rel).name,
        excel_dir / "assets" / Path(rel).name,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None
