# Tests des pages individuelles de revues : elles doivent afficher les cartes
# des numéros rattachés (livre.collection_id == journal_id slugifié de la
# revue), avec le même rendu que les pages de collections.
import hashlib
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

CARD_RE = re.compile(r'<div class="card">')
CARD_LINK_RE = re.compile(r'href="\.\./livres/([^"]+\.html)"')


def _book_row(**over):
    base = {
        "titre_norm": "Austriaca n° 1",
        "sous_titre_norm": "",
        "credit_ligne": "",
        "collection": "Austriaca",
        "collection_id": "austriaca",
        "format_site": "",
        "date_parution_norm": "2024-01-01",
        "year": 2024,
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


def _revue_row(**over):
    base = {
        "journal_id": "austriaca",
        "title": "Austriaca",
        "slug": "austriaca",
        "url": "",
        "issn_print": "",
        "issn_online": "",
        "description_md": "",
        "direction": "",
        "comite_scientifique": "",
        "contact_email": "",
        "is_active": 1,
        "order": None,
    }
    base.update(over)
    return base


def _gen_revues(tmp_path, book_rows, revue_rows):
    cfg = bs.SiteConfig()
    books = pd.DataFrame(book_rows) if book_rows else pd.DataFrame(
        columns=["collection_id", "year", "titre_norm", "slug"])
    revues = pd.DataFrame(revue_rows)
    bs.build_revues(cfg, books, revues, tmp_path)
    return {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "revues").glob("*.html")}


# ---------------------------------------------------------------
# 1. Une revue avec un seul numéro : une carte sur sa page
# ---------------------------------------------------------------

def test_revue_un_numero(tmp_path):
    pages = _gen_revues(tmp_path, [_book_row()], [_revue_row()])
    html = pages["austriaca.html"]
    assert "<h3>Numéros parus</h3>" in html
    assert len(CARD_RE.findall(html)) == 1
    assert 'href="../livres/austriaca-n-1.html"' in html
    assert "Aucun numéro rattaché trouvé." not in html


# ---------------------------------------------------------------
# 2. Une revue avec plusieurs numéros : toutes les cartes
# ---------------------------------------------------------------

def test_revue_plusieurs_numeros(tmp_path):
    rows = [
        _book_row(titre_norm=f"Austriaca n° {i}", slug=f"austriaca-n-{i}",
                  id13=f"978287775000{i}", year=2020 + i)
        for i in range(1, 4)
    ]
    pages = _gen_revues(tmp_path, rows, [_revue_row()])
    html = pages["austriaca.html"]
    assert len(CARD_RE.findall(html)) == 3
    for i in range(1, 4):
        assert f'href="../livres/austriaca-n-{i}.html"' in html


# ---------------------------------------------------------------
# 3. Tri : le numéro le plus récent apparaît en premier
# ---------------------------------------------------------------

def test_tri_numeros_recent_en_premier(tmp_path):
    rows = [
        _book_row(titre_norm="Austriaca ancien", slug="austriaca-ancien", year=2010),
        _book_row(titre_norm="Austriaca récent", slug="austriaca-recent", year=2025),
        _book_row(titre_norm="Austriaca médian", slug="austriaca-median", year=2018),
    ]
    pages = _gen_revues(tmp_path, rows, [_revue_row()])
    html = pages["austriaca.html"]
    ordre = CARD_LINK_RE.findall(html)
    assert ordre == ["austriaca-recent.html", "austriaca-median.html", "austriaca-ancien.html"]


# ---------------------------------------------------------------
# 4. Revue sans numéro : page présente, message dédié
# ---------------------------------------------------------------

def test_revue_sans_numero(tmp_path):
    pages = _gen_revues(tmp_path, [], [_revue_row()])
    html = pages["austriaca.html"]
    assert "<h3>Numéros parus</h3>" in html
    assert "Aucun numéro rattaché trouvé." in html
    assert not CARD_RE.findall(html)


# ---------------------------------------------------------------
# 5. Un ouvrage de collection classique n'apparaît pas sur une revue
# ---------------------------------------------------------------

def test_ouvrage_collection_absent_des_revues(tmp_path):
    rows = [
        _book_row(),
        _book_row(titre_norm="Un essai", slug="un-essai",
                  collection="Essais", collection_id="col-essais"),
    ]
    pages = _gen_revues(tmp_path, rows, [_revue_row()])
    html = pages["austriaca.html"]
    assert 'href="../livres/austriaca-n-1.html"' in html
    assert "un-essai.html" not in html


# ---------------------------------------------------------------
# 6. Deux revues : les numéros ne sont pas mélangés
# ---------------------------------------------------------------

def test_deux_revues_pas_melangees(tmp_path):
    rows = [
        _book_row(),
        _book_row(titre_norm="Fontenelle n° 1", slug="fontenelle-n-1",
                  collection="Revue Fontenelle", collection_id="revue-fontenelle"),
    ]
    revues = [
        _revue_row(),
        _revue_row(journal_id="revue-fontenelle", title="Revue Fontenelle",
                   slug="revue-fontenelle"),
    ]
    pages = _gen_revues(tmp_path, rows, revues)
    assert "austriaca-n-1.html" in pages["austriaca.html"]
    assert "fontenelle-n-1.html" not in pages["austriaca.html"]
    assert "fontenelle-n-1.html" in pages["revue-fontenelle.html"]
    assert "austriaca-n-1.html" not in pages["revue-fontenelle.html"]


# ---------------------------------------------------------------
# 7. journal_id différent du slug : sélection par journal_id,
#    page écrite sous le slug public
# ---------------------------------------------------------------

def test_journal_id_different_du_slug(tmp_path):
    rows = [_book_row(titre_norm="Revue exemple n° 1", slug="revue-exemple-n-1",
                      collection="Revue exemple", collection_id="rev-001")]
    pages = _gen_revues(tmp_path, rows,
                        [_revue_row(journal_id="rev-001", title="Revue exemple",
                                    slug="revue-exemple")])
    assert "rev-001.html" not in pages  # pas de page sous l'identifiant interne
    html = pages["revue-exemple.html"]
    assert 'href="../livres/revue-exemple-n-1.html"' in html
    assert len(CARD_RE.findall(html)) == 1


# ---------------------------------------------------------------
# 8. Génération complète du gabarit : cartes -> fiches existantes
# ---------------------------------------------------------------

def _revue_cards_ok(out: Path):
    erreurs = []
    for page in (out / "revues").glob("*.html"):
        if page.name == "index.html":
            continue
        html = page.read_text(encoding="utf-8")
        assert "<h3>Numéros parus</h3>" in html, f"{page.name} : section manquante"
        for target in CARD_LINK_RE.findall(html):
            if not (out / "livres" / target).exists():
                erreurs.append(f"{page.name} -> livres/{target} (inexistant)")
    assert not erreurs, "Cartes de revue erronées :\n" + "\n".join(erreurs)


def test_generation_complete_gabarit(tmp_path):
    avant = hashlib.sha256(GABARIT.read_bytes()).hexdigest()
    out = tmp_path / "dist"
    bs.build_site(GABARIT, out, covers_dir=None)
    _revue_cards_ok(out)
    assert hashlib.sha256(GABARIT.read_bytes()).hexdigest() == avant, \
        "le gabarit a été modifié"


# ---------------------------------------------------------------
# 9. Génération complète du classeur réel : décomptes par revue
# ---------------------------------------------------------------

@pytest.mark.skipif(not CLASSEUR_REEL.exists(),
                    reason="classeur de production absent de cette machine")
def test_generation_complete_classeur_reel(tmp_path):
    avant = hashlib.sha256(CLASSEUR_REEL.read_bytes()).hexdigest()
    out = tmp_path / "dist"
    bs.build_site(CLASSEUR_REEL, out, covers_dir=None)
    assert hashlib.sha256(CLASSEUR_REEL.read_bytes()).hexdigest() == avant, \
        "le classeur de production a été modifié"

    _revue_cards_ok(out)

    # Décomptes attendus (audit du 2026-07-12 sur le classeur v25)
    attendus = {
        "austriaca.html": 97,
        "penser-l-education.html": 24,
        "les-annales-de-droit.html": 16,
        "revue-fontenelle.html": 14,
        "revue-du-philanthrope.html": 11,
        "etudes-normandes.html": 10,
        "revue-sculptures.html": 8,
        "cahiers-historiques-des-annales-de-droit.html": 4,
        "cahiers-du-ciriec-france.html": 3,
        "revue-normande-d-histoire-du-sport.html": 2,
        "glottopol.html": 0,
    }
    slugs_par_page = {}
    for name, n in attendus.items():
        html = (out / "revues" / name).read_text(encoding="utf-8")
        cards = CARD_LINK_RE.findall(html)
        assert len(cards) == n, f"{name} : {len(cards)} cartes au lieu de {n}"
        slugs_par_page[name] = set(cards)
        if n == 0:
            assert "Aucun numéro rattaché trouvé." in html

    # Aucun numéro sur la mauvaise revue : les ensembles sont disjoints
    noms = list(slugs_par_page)
    for i, a in enumerate(noms):
        for b in noms[i + 1:]:
            commun = slugs_par_page[a] & slugs_par_page[b]
            assert not commun, f"numéros partagés entre {a} et {b} : {commun}"

    # Les badges des fiches de numéros pointent toujours vers la revue
    austriaca_fiches = [p for p in (out / "livres").glob("*.html")
                        if "href='../revues/austriaca.html'" in p.read_text(encoding="utf-8")]
    assert len(austriaca_fiches) == 97
