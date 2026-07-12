# Tests des badges de collection sur les fiches livres :
# le lien doit viser la page réellement générée par build_collections
# (slug de la feuille, sinon collection_id), jamais une URL déduite
# aveuglément de l'identifiant.
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


def _book_row(**over):
    base = {
        "titre_norm": "Un livre",
        "sous_titre_norm": "",
        "credit_ligne": "",
        "collection": "Classiques",
        "collection_id": "col-classiques",
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
        "slug": "un-livre",
    }
    base.update(over)
    return base


def _gen_book_pages(tmp_path, rows, revue_slugs=None, collection_slugs=None):
    cfg = bs.SiteConfig()
    books = pd.DataFrame(rows)
    bs.build_book_pages(cfg, books, tmp_path,
                        revue_slugs=revue_slugs, collection_slugs=collection_slugs)
    return {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "livres").glob("*.html")}


def _coll_df(rows):
    base_cols = ["collection_id", "name", "slug", "is_active"]
    return pd.DataFrame(rows, columns=base_cols)


# ---------------------------------------------------------------
# Mapping : règle « slug de la feuille, sinon collection_id »
# ---------------------------------------------------------------

def test_mapping_slug_different_de_l_identifiant():
    m = bs.build_collection_slug_map(_coll_df([
        {"collection_id": "col-classiques", "name": "Classiques", "slug": "classiques", "is_active": 1},
        {"collection_id": "col-essais", "name": "Essais", "slug": "essais", "is_active": 1},
    ]))
    assert m == {"col-classiques": "classiques", "col-essais": "essais"}


def test_mapping_slug_vide_retombe_sur_l_identifiant():
    m = bs.build_collection_slug_map(_coll_df([
        {"collection_id": "cours", "name": "Cours", "slug": "", "is_active": 1},
    ]))
    assert m == {"cours": "cours"}


def test_mapping_collection_inactive_valeur_vide():
    m = bs.build_collection_slug_map(_coll_df([
        {"collection_id": "col-histoire", "name": "Histoire", "slug": "histoire", "is_active": 0},
    ]))
    assert m == {"col-histoire": ""}


def test_mapping_feuille_vide_derive_du_catalogue():
    # sans feuille COLLECTIONS, build_collections crée les pages depuis les
    # noms du catalogue : le mapping doit refléter ces pages dérivées.
    books = pd.DataFrame([_book_row(collection="Essais", collection_id="essais")])
    m = bs.build_collection_slug_map(pd.DataFrame(), books)
    assert m == {"essais": "essais"}


def test_mapping_doublon_ambigu_erreur_metier():
    with pytest.raises(ValueError) as exc:
        bs.build_collection_slug_map(_coll_df([
            {"collection_id": "col-essais", "name": "Essais", "slug": "essais", "is_active": 1},
            {"collection_id": "col-essais", "name": "Essais bis", "slug": "essais-bis", "is_active": 1},
        ]))
    msg = str(exc.value)
    assert "col-essais" in msg and "essais.html" in msg and "essais-bis.html" in msg


def test_mapping_doublon_meme_cible_tolere():
    m = bs.build_collection_slug_map(_coll_df([
        {"collection_id": "col-essais", "name": "Essais", "slug": "essais", "is_active": 1},
        {"collection_id": "col-essais", "name": "Essais", "slug": "essais", "is_active": 1},
    ]))
    assert m == {"col-essais": "essais"}


def test_mapping_ligne_active_prime_sur_doublon_inactif():
    m = bs.build_collection_slug_map(_coll_df([
        {"collection_id": "col-essais", "name": "Essais", "slug": "essais", "is_active": 0},
        {"collection_id": "col-essais", "name": "Essais", "slug": "essais", "is_active": 1},
    ]))
    assert m == {"col-essais": "essais"}


# ---------------------------------------------------------------
# 1. collection_id != slug : badge vers la page réelle
# ---------------------------------------------------------------

def test_badge_collection_slug_different(tmp_path):
    pages = _gen_book_pages(tmp_path, [_book_row()],
                            collection_slugs={"col-classiques": "classiques"})
    html = pages["un-livre.html"]
    assert "<a class='badge' href='../collections/classiques.html'>Classiques</a>" in html
    assert "../collections/col-classiques.html" not in html


# ---------------------------------------------------------------
# 2. slug identique à l'identifiant : comportement inchangé
# ---------------------------------------------------------------

def test_badge_collection_slug_identique(tmp_path):
    pages = _gen_book_pages(
        tmp_path,
        [_book_row(collection="Cours", collection_id="cours", slug="livre-cours")],
        collection_slugs={"cours": "cours"},
    )
    assert "<a class='badge' href='../collections/cours.html'>Cours</a>" in pages["livre-cours.html"]


# ---------------------------------------------------------------
# 3. Plusieurs livres d'une même collection : même cible
# ---------------------------------------------------------------

def test_plusieurs_livres_meme_collection(tmp_path):
    rows = [_book_row(titre_norm=f"Livre {i}", slug=f"livre-{i}", id13=f"978287775000{i}")
            for i in range(1, 4)]
    pages = _gen_book_pages(tmp_path, rows, collection_slugs={"col-classiques": "classiques"})
    for i in range(1, 4):
        assert "href='../collections/classiques.html'" in pages[f"livre-{i}.html"]


# ---------------------------------------------------------------
# 4. Collection inactive : badge sans lien
# ---------------------------------------------------------------

def test_collection_inactive_badge_sans_lien(tmp_path):
    pages = _gen_book_pages(
        tmp_path,
        [_book_row(collection="Histoire", collection_id="col-histoire", slug="livre-histoire")],
        collection_slugs={"col-histoire": ""},
    )
    html = pages["livre-histoire.html"]
    assert "<span class='badge'>Histoire</span>" in html
    assert "<a class='badge' href='../collections/" not in html


# ---------------------------------------------------------------
# 5. Identifiant inconnu : badge sans lien (plus de lien aveugle)
# ---------------------------------------------------------------

def test_identifiant_inconnu_badge_sans_lien(tmp_path):
    pages = _gen_book_pages(
        tmp_path,
        [_book_row(collection="Divers", collection_id="serie-inconnue", slug="livre-x")],
        collection_slugs={"col-classiques": "classiques"},
    )
    html = pages["livre-x.html"]
    assert "<span class='badge'>Divers</span>" in html
    assert "../collections/serie-inconnue.html" not in html


# ---------------------------------------------------------------
# 6. Livre de revue : la priorité revue reste intacte
# ---------------------------------------------------------------

def test_priorite_revue_intacte(tmp_path):
    pages = _gen_book_pages(
        tmp_path,
        [_book_row(collection="Austriaca", collection_id="austriaca",
                   titre_norm="Austriaca n° 1", slug="austriaca-n-1")],
        revue_slugs={"austriaca": "austriaca"},
        collection_slugs={"col-classiques": "classiques"},
    )
    html = pages["austriaca-n-1.html"]
    assert "<a class='badge' href='../revues/austriaca.html'>Austriaca</a>" in html
    assert "<a class='badge' href='../collections/" not in html


# ---------------------------------------------------------------
# 7. Collision collection/revue : la revue prime (règle existante)
# ---------------------------------------------------------------

def test_collision_collection_revue_la_revue_prime(tmp_path):
    pages = _gen_book_pages(
        tmp_path,
        [_book_row(collection="Revue exemple", collection_id="rev-001",
                   slug="revue-exemple-n-1")],
        revue_slugs={"rev-001": "revue-exemple"},
        collection_slugs={"rev-001": "revue-exemple-collection"},
    )
    html = pages["revue-exemple-n-1.html"]
    assert "href='../revues/revue-exemple.html'" in html
    assert "<a class='badge' href='../collections/" not in html


# ---------------------------------------------------------------
# 8-10. Générations complètes : tous les badges visent des fichiers
# réellement présents dans dist/collections/ et dist/revues/ ;
# classeurs inchangés par hachage.
# ---------------------------------------------------------------

BADGE_RE = re.compile(r"<a class='badge' href='\.\./(collections|revues)/([^']+\.html)'")


def _check_full_generation(excel_path: Path, out: Path):
    h_avant = hashlib.sha256(excel_path.read_bytes()).hexdigest()
    bs.build_site(excel_path, out, covers_dir=None)
    assert hashlib.sha256(excel_path.read_bytes()).hexdigest() == h_avant, \
        f"{excel_path.name} a été modifié par la génération"

    erreurs = []
    for page in (out / "livres").glob("*.html"):
        for kind, target in BADGE_RE.findall(page.read_text(encoding="utf-8")):
            if not (out / kind / target).exists():
                erreurs.append(f"{page.name} -> {kind}/{target} (inexistant)")
    assert not erreurs, "Badges pointant vers des pages absentes :\n" + "\n".join(erreurs)


def test_generation_complete_gabarit(tmp_path):
    out = tmp_path / "dist"
    _check_full_generation(GABARIT, out)
    # le cas nominal du gabarit : col-classiques -> classiques.html
    html = "".join(p.read_text(encoding="utf-8") for p in (out / "livres").glob("*.html"))
    assert "href='../collections/classiques.html'" in html
    assert "../collections/col-classiques.html" not in html


@pytest.mark.skipif(not CLASSEUR_REEL.exists(),
                    reason="classeur de production absent de cette machine")
def test_generation_complete_classeur_reel(tmp_path):
    _check_full_generation(CLASSEUR_REEL, tmp_path / "dist")
