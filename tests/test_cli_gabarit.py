# Tests de la ligne de commande (--excel / --tableur) et du gabarit officiel :
# - --excel est l'option canonique, --tableur son alias rétrocompatible ;
# - le gabarit existe à l'emplacement documenté (gabarit/purh_site_excel_gabarit.xlsx) ;
# - aucun fichier suivi par git ne référence les anciens gabarits disparus.
#
# Lancement : .venv\Scripts\python.exe -m pytest tests/ -v

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from build_site import make_arg_parser

RACINE = Path(__file__).resolve().parents[1]
GABARIT = RACINE / "gabarit" / "purh_site_excel_gabarit.xlsx"


# ----------------------------------------------------------------------
# Options --excel / --tableur
# ----------------------------------------------------------------------

def test_option_excel_acceptee():
    args = make_arg_parser().parse_args(["--excel", "classeur.xlsx"])
    assert args.excel == "classeur.xlsx"


def test_option_tableur_alias_retrocompatible():
    args = make_arg_parser().parse_args(["--tableur", "classeur.xlsx"])
    assert args.excel == "classeur.xlsx"  # même destination interne


def test_les_deux_options_meme_destination():
    a = make_arg_parser().parse_args(["--excel", "x.xlsx"])
    b = make_arg_parser().parse_args(["--tableur", "x.xlsx"])
    assert a.excel == b.excel
    assert not hasattr(a, "tableur")  # une seule valeur interne, pas deux


def test_aide_presente_excel():
    # argparse replie les lignes : on normalise les blancs avant de chercher
    help_text = " ".join(make_arg_parser().format_help().split())
    assert "--excel" in help_text
    assert "ancien alias" in help_text  # --tableur mentionné sobrement


# ----------------------------------------------------------------------
# Gabarit officiel
# ----------------------------------------------------------------------

def test_gabarit_officiel_existe_au_chemin_documente():
    assert GABARIT.exists(), f"gabarit absent : {GABARIT}"


def test_gabarit_officiel_est_le_seul_xlsx_suivi_par_git():
    res = subprocess.run(["git", "ls-files", "*.xlsx"],
                         cwd=RACINE, capture_output=True, text=True)
    if res.returncode != 0:
        pytest.skip("git indisponible")
    suivis = [l for l in res.stdout.splitlines() if l.strip()]
    assert suivis == ["gabarit/purh_site_excel_gabarit.xlsx"]


ANCIENS_NOMS = [
    "sample_site_excel_gabarit_checked_with_assets.xlsx",
    "sample_site_excel_squelette.xlsx",
    "site_tableur_template.xlsx",
    "purh_site_tableur_template_v2.xlsx",
    "purh_site_excel_template_v4.xlsx",
]


def test_aucune_reference_aux_anciens_gabarits():
    """Les fichiers suivis (code, docs, scripts) ne citent plus d'ancien gabarit.

    Ce test est la seule mention autorisée de ces noms dans le dépôt.
    """
    res = subprocess.run(["git", "ls-files", "*.py", "*.md", "*.bat", "*.txt"],
                         cwd=RACINE, capture_output=True, text=True)
    if res.returncode != 0:
        pytest.skip("git indisponible")
    moi = Path(__file__).resolve()
    fautifs = []
    for rel in res.stdout.splitlines():
        p = RACINE / rel
        if not rel.strip() or p.resolve() == moi or not p.exists():
            continue
        contenu = p.read_text(encoding="utf-8", errors="replace")
        for nom in ANCIENS_NOMS:
            if nom in contenu:
                fautifs.append(f"{rel} -> {nom}")
    assert not fautifs, "références obsolètes : " + "; ".join(fautifs)
