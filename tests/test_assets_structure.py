# Tests de la structure des assets (sources à côté du classeur -> dossier de sortie/assets/)
# Lancement : .venv\Scripts\python.exe -m pytest tests/ -v
#
# Convention source canonique, à côté du classeur :
#   assets/           logos et favicon
#   assets/actu/      images d'actualités
#   assets/social/    icônes des réseaux
#   assets/docs/      PDF (bon de commande…)
# Les anciens emplacements (racine, actu/, social/, images/) restent acceptés.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

import build_site as bs


@pytest.fixture
def excel_dir(tmp_path) -> Path:
    """Dossier simulant l'emplacement du classeur (le fichier n'est jamais ouvert ici)."""
    (tmp_path / "classeur.xlsx").write_text("x")
    return tmp_path


def excel_path(excel_dir: Path) -> Path:
    return excel_dir / "classeur.xlsx"


def put(excel_dir: Path, rel: str, content: bytes = b"DATA") -> Path:
    p = excel_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


# ---------------------------------------------------------------------------
# Images d'actualités
# ---------------------------------------------------------------------------

def test_actu_image_dans_assets_actu(excel_dir, tmp_path):
    put(excel_dir, "assets/actu/photo.jpg")
    actus = pd.DataFrame({"image": ["photo.jpg"]})
    out = tmp_path / "dist"
    bs.copy_actualites_images(excel_path(excel_dir), out, actus)
    assert (out / "assets" / "actu" / "photo.jpg").is_file()


def test_actu_image_ancien_dossier_actu(excel_dir, tmp_path):
    put(excel_dir, "actu/photo.jpg")
    actus = pd.DataFrame({"image": ["photo.jpg"]})
    out = tmp_path / "dist"
    bs.copy_actualites_images(excel_path(excel_dir), out, actus)
    assert (out / "assets" / "actu" / "photo.jpg").is_file()


def test_actu_image_priorite_assets_actu(excel_dir):
    # homonymes dans tous les emplacements historiques : assets/actu/ gagne
    put(excel_dir, "photo.jpg", b"RACINE")
    put(excel_dir, "assets/photo.jpg", b"ASSETS")
    put(excel_dir, "actu/photo.jpg", b"ACTU")
    put(excel_dir, "images/photo.jpg", b"IMAGES")
    put(excel_dir, "assets/actu/photo.jpg", b"CANONIQUE")
    src = bs.resolve_actu_image_source(excel_dir, "photo.jpg")
    assert src.read_bytes() == b"CANONIQUE"


# ---------------------------------------------------------------------------
# Icônes sociales
# ---------------------------------------------------------------------------

def test_icone_sociale_assets_social(excel_dir, tmp_path):
    put(excel_dir, "assets/social/instagram.svg", b"<svg/>")
    cfg = bs.SiteConfig(social_1_icon="instagram")
    out = tmp_path / "dist"
    bs.copy_declared_assets(excel_path(excel_dir), out, cfg)
    assert (out / "assets" / "social" / "instagram.svg").is_file()


def test_icone_sociale_ancien_dossier_social(excel_dir, tmp_path):
    put(excel_dir, "social/facebook.svg", b"<svg/>")
    cfg = bs.SiteConfig(social_1_icon="facebook")
    out = tmp_path / "dist"
    bs.copy_declared_assets(excel_path(excel_dir), out, cfg)
    assert (out / "assets" / "social" / "facebook.svg").is_file()


# ---------------------------------------------------------------------------
# PDF de commande
# ---------------------------------------------------------------------------

def order_href(cfg) -> str:
    html = bs.book_order_block(cfg, {"title": "T", "id13": "1"})
    return html.split('href="')[1].split('"')[0]


def test_pdf_simple_racine_assets(excel_dir, tmp_path):
    put(excel_dir, "assets/bon.pdf", b"%PDF")
    cfg = bs.SiteConfig(order_mode="pdf", order_pdf_filename="bon.pdf")
    out = tmp_path / "dist"
    bs.copy_declared_assets(excel_path(excel_dir), out, cfg)
    assert (out / "assets" / "bon.pdf").is_file()
    assert order_href(cfg) == "../assets/bon.pdf"


def test_pdf_sous_docs(excel_dir, tmp_path):
    # source canonique : assets/docs/, lien ../assets/docs/, copie dist/assets/docs/
    put(excel_dir, "assets/docs/bon.pdf", b"%PDF")
    cfg = bs.SiteConfig(order_mode="pdf", order_pdf_filename="docs/bon.pdf")
    out = tmp_path / "dist"
    bs.copy_declared_assets(excel_path(excel_dir), out, cfg)
    assert (out / "assets" / "docs" / "bon.pdf").is_file()
    assert order_href(cfg) == "../assets/docs/bon.pdf"
    # le lien pointe bien vers le fichier copié (résolu depuis dist/livres/)
    target = (out / "livres" / order_href(cfg)).resolve()
    assert target == (out / "assets" / "docs" / "bon.pdf").resolve()


def test_pdf_sous_docs_ancien_emplacement(excel_dir, tmp_path):
    # compat : docs/ à côté du classeur, sans assets/
    put(excel_dir, "docs/bon.pdf", b"%PDF")
    cfg = bs.SiteConfig(order_mode="pdf", order_pdf_filename="docs/bon.pdf")
    out = tmp_path / "dist"
    bs.copy_declared_assets(excel_path(excel_dir), out, cfg)
    assert (out / "assets" / "docs" / "bon.pdf").is_file()


def test_pdf_pas_de_double_prefixe_assets(excel_dir, tmp_path):
    # une valeur CONFIG déjà préfixée assets/ ne produit ni assets/assets/ ni lien cassé
    put(excel_dir, "assets/docs/bon.pdf", b"%PDF")
    cfg = bs.SiteConfig(order_mode="pdf", order_pdf_filename="assets/docs/bon.pdf")
    out = tmp_path / "dist"
    bs.copy_declared_assets(excel_path(excel_dir), out, cfg)
    assert (out / "assets" / "docs" / "bon.pdf").is_file()
    assert not (out / "assets" / "assets").exists()
    assert order_href(cfg) == "../assets/docs/bon.pdf"


# ---------------------------------------------------------------------------
# Logos et JSON à la racine de dist/assets/
# ---------------------------------------------------------------------------

def test_logos_racine_dist_assets(excel_dir, tmp_path):
    put(excel_dir, "assets/logo.png", b"PNG")
    cfg = bs.SiteConfig(logo_left="assets/logo.png")
    out = tmp_path / "dist"
    bs.copy_declared_assets(excel_path(excel_dir), out, cfg)
    assert (out / "assets" / "logo.png").is_file()


def test_logo_ancien_emplacement_racine(excel_dir, tmp_path):
    # repli : logo posé à côté du classeur, hors assets/
    put(excel_dir, "logo.png", b"PNG")
    cfg = bs.SiteConfig(logo_left="assets/logo.png")
    out = tmp_path / "dist"
    bs.copy_declared_assets(excel_path(excel_dir), out, cfg)
    assert (out / "assets" / "logo.png").is_file()


def test_json_racine_dossier_sortie(tmp_path):
    out = tmp_path / "sortie"
    (out / "assets").mkdir(parents=True)
    bs.build_catalogue_json(pd.DataFrame(), out)
    bs.build_actualites_json(pd.DataFrame(), out)
    assert (out / "catalogue.json").is_file()
    assert (out / "actualites.json").is_file()
    assert not (out / "assets" / "catalogue.json").exists()
    assert not (out / "assets" / "actualites.json").exists()
