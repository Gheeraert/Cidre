# Tests des badges de rattachement sur les fiches livres :
# un numéro de revue doit pointer vers revues/<slug>.html (page réellement
# générée par build_revues), pas vers collections/<journal_id>.html.
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_site as bs

GABARIT = ROOT / "gabarit" / "purh_site_excel_gabarit.xlsx"
CLASSEUR_REEL = ROOT / "20260630_purh_master_v25.xlsx"


def _book_row(**over):
    base = {
        "titre_norm": "Austriaca n° 1",
        "sous_titre_norm": "",
        "credit_ligne": "",
        "collection": "Austriaca",
        "collection_id": "austriaca",
        "format_site": "",
        "date_parution_norm": None,
        "id13": "9782877750001",
        "openedition_url": "",
        "cover_file": "",
        "price_str": "",
        "availability_label": "",
        "physical_str": "",
        "Description longue": "",
        "Description courte": "",
        "Table des matières": "",
        "order_url": "",
        "slug": "austriaca-n-1",
    }
    base.update(over)
    return base


def _gen_book_pages(tmp_path, rows, revue_slugs):
    cfg = bs.SiteConfig()
    books = pd.DataFrame(rows)
    bs.build_book_pages(cfg, books, tmp_path, revue_slugs=revue_slugs)
    return {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "livres").glob("*.html")}


# ---------------------------------------------------------------
# 1. Un numéro d'Austriaca pointe vers ../revues/austriaca.html
# ---------------------------------------------------------------

def test_numero_austriaca_badge_vers_revues(tmp_path):
    pages = _gen_book_pages(tmp_path, [_book_row()], {"austriaca": "austriaca"})
    html = pages["austriaca-n-1.html"]
    assert "<a class='badge' href='../revues/austriaca.html'>Austriaca</a>" in html
    assert "../collections/austriaca.html" not in html


# ---------------------------------------------------------------
# 2. journal_id et slug différents : le lien utilise le slug réel
# ---------------------------------------------------------------

def test_journal_id_et_slug_differents(tmp_path):
    revues = pd.DataFrame([{
        "journal_id": "rev-001", "slug": "revue-exemple",
        "title": "Revue exemple", "is_active": True,
    }])
    m = bs.build_revue_slug_map(revues)
    assert m == {"rev-001": "revue-exemple"}

    pages = _gen_book_pages(
        tmp_path,
        [_book_row(collection="Revue exemple", collection_id="rev-001",
                   titre_norm="Revue exemple n° 1", slug="revue-exemple-n-1")],
        m,
    )
    html = pages["revue-exemple-n-1.html"]
    assert "href='../revues/revue-exemple.html'" in html
    assert "../collections/rev-001.html" not in html


# ---------------------------------------------------------------
# 3. Plusieurs numéros d'une même revue : même cible pour tous
# ---------------------------------------------------------------

def test_plusieurs_numeros_meme_cible(tmp_path):
    rows = [
        _book_row(titre_norm=f"Austriaca n° {i}", slug=f"austriaca-n-{i}",
                  id13=f"978287775000{i}")
        for i in range(1, 4)
    ]
    pages = _gen_book_pages(tmp_path, rows, {"austriaca": "austriaca"})
    for i in range(1, 4):
        assert "href='../revues/austriaca.html'" in pages[f"austriaca-n-{i}.html"]


# ---------------------------------------------------------------
# 4. Une véritable collection garde le comportement actuel
# ---------------------------------------------------------------

def test_vraie_collection_comportement_inchange(tmp_path):
    pages = _gen_book_pages(
        tmp_path,
        [_book_row(collection="Essais", collection_id="col-essais",
                   titre_norm="Un essai", slug="un-essai")],
        {"austriaca": "austriaca"},
    )
    html = pages["un-essai.html"]
    assert "<a class='badge' href='../collections/col-essais.html'>Essais</a>" in html
    # pas de badge vers une revue (le menu de navigation, lui, référence revues/index.html)
    assert "<a class='badge' href='../revues/" not in html


# ---------------------------------------------------------------
# 5. Revue inactive : badge sans lien (pas d'URL 404)
# ---------------------------------------------------------------

def test_revue_inactive_badge_sans_lien(tmp_path):
    revues = pd.DataFrame([{
        "journal_id": "austriaca", "slug": "austriaca",
        "title": "Austriaca", "is_active": 0,
    }])
    m = bs.build_revue_slug_map(revues)
    assert m == {"austriaca": ""}

    pages = _gen_book_pages(tmp_path, [_book_row()], m)
    html = pages["austriaca-n-1.html"]
    assert "<span class='badge'>Austriaca</span>" in html
    assert "../revues/austriaca.html" not in html
    assert "../collections/austriaca.html" not in html


def test_revue_active_prime_sur_doublon_inactif():
    revues = pd.DataFrame([
        {"journal_id": "austriaca", "slug": "austriaca", "title": "Austriaca", "is_active": 1},
        {"journal_id": "austriaca", "slug": "austriaca-2", "title": "Austriaca", "is_active": 0},
    ])
    assert bs.build_revue_slug_map(revues)["austriaca"] == "austriaca"


# ---------------------------------------------------------------
# 6. Identifiant inconnu : aucun changement imprévu
# ---------------------------------------------------------------

def test_identifiant_inconnu_inchange(tmp_path):
    pages = _gen_book_pages(
        tmp_path,
        [_book_row(collection="Divers", collection_id="serie-inconnue",
                   titre_norm="Un livre", slug="un-livre")],
        {"austriaca": "austriaca"},
    )
    html = pages["un-livre.html"]
    assert "<a class='badge' href='../collections/serie-inconnue.html'>Divers</a>" in html


def test_sans_mapping_comportement_historique(tmp_path):
    # revue_slugs=None (appel historique) : lien collections/ comme avant
    pages = _gen_book_pages(tmp_path, [_book_row()], None)
    assert "../collections/austriaca.html" in pages["austriaca-n-1.html"]


# ---------------------------------------------------------------
# 7. Génération complète du gabarit : liens ../revues/*.html valides
# ---------------------------------------------------------------

BADGE_REVUE_RE = re.compile(r"href='\.\./revues/([^']+\.html)'")


def _check_full_generation(excel_path: Path, out: Path):
    bs.build_site(excel_path, out, covers_dir=None)

    wb = pd.ExcelFile(excel_path)
    cfg = bs.load_config(wb, "CONFIG")
    revues = bs.load_revues(wb, cfg.revues_sheet)
    rmap = bs.build_revue_slug_map(revues)

    erreurs = []
    for page in (out / "livres").glob("*.html"):
        html = page.read_text(encoding="utf-8")
        # aucun numéro de revue reconnu ne pointe encore vers collections/<journal_id>.html
        for jid in rmap:
            if f"../collections/{jid}.html" in html:
                erreurs.append(f"{page.name} -> collections/{jid}.html")
        # tout lien ../revues/*.html vise un fichier généré
        for target in BADGE_REVUE_RE.findall(html):
            if not (out / "revues" / target).exists():
                erreurs.append(f"{page.name} -> revues/{target} (inexistant)")
    assert not erreurs, "Liens de badges erronés :\n" + "\n".join(erreurs)


def test_generation_complete_gabarit(tmp_path):
    _check_full_generation(GABARIT, tmp_path / "dist")


# ---------------------------------------------------------------
# 8. Génération complète du classeur réel (si présent localement)
# ---------------------------------------------------------------

@pytest.mark.skipif(not CLASSEUR_REEL.exists(),
                    reason="classeur de production absent de cette machine")
def test_generation_complete_classeur_reel(tmp_path):
    avant = CLASSEUR_REEL.read_bytes()
    _check_full_generation(CLASSEUR_REEL, tmp_path / "dist")
    assert CLASSEUR_REEL.read_bytes() == avant, "le classeur de production a été modifié"

    # le cas confirmé de l'audit : Austriaca
    livres = tmp_path / "dist" / "livres"
    austriaca_pages = [p for p in livres.glob("*.html")
                       if "href='../revues/austriaca.html'" in p.read_text(encoding="utf-8")]
    assert austriaca_pages, "aucune fiche ne pointe vers revues/austriaca.html"
