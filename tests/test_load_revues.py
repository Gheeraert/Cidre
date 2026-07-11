# Tests du chargement des revues (build_site.load_revues) :
# - tolérance REVUE / REVUES sur le nom de feuille (garantie de non-régression) ;
# - alias d'en-tête d'identifiant (revue_id, journal_id, review_id, id) ;
# - détection des colonnes synonymes simultanées (erreur métier, pas de
#   traceback pandas) ;
# - gabarit officiel : chargement et génération complète.
#
# Lancement : .venv\Scripts\python.exe -m pytest tests/ -v

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import openpyxl
import pandas as pd
import pytest

import build_site
from build_site import detect_revues_sheet, load_revues

GABARIT = (Path(__file__).resolve().parents[1]
           / "gabarit" / "purh_site_excel_gabarit.xlsx")


def make_workbook(tmp_path: Path, sheet: str, headers: list[str],
                  rows: list[list] | None = None) -> pd.ExcelFile:
    p = tmp_path / "revues.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    for row in rows if rows is not None else [["glottopol"] + [""] * (len(headers) - 1)]:
        ws.append(row)
    wb.save(p)
    return pd.ExcelFile(p)


# ----------------------------------------------------------------------
# Nom de feuille : REVUE et REVUES restent tous deux acceptés
# ----------------------------------------------------------------------

def test_feuille_revue_singulier_et_colonne_revue_id(tmp_path):
    wb = make_workbook(tmp_path, "REVUE", ["revue_id", "title"],
                       [["glottopol", "Glottopol"]])
    assert detect_revues_sheet(wb, "REVUES") == "REVUE"  # CONFIG discordant absorbé
    df = load_revues(wb, "REVUES")
    assert df["journal_id"].tolist() == ["glottopol"]


def test_feuille_revues_pluriel_et_colonne_revue_id(tmp_path):
    wb = make_workbook(tmp_path, "REVUES", ["revue_id", "title"],
                       [["glottopol", "Glottopol"]])
    assert detect_revues_sheet(wb, "REVUES") == "REVUES"
    df = load_revues(wb, "REVUES")
    assert df["journal_id"].tolist() == ["glottopol"]


# ----------------------------------------------------------------------
# Un seul alias d'identifiant : normalisation vers journal_id
# ----------------------------------------------------------------------

@pytest.mark.parametrize("header", ["journal_id", "revue_id", "review_id", "id"])
def test_alias_identifiant_seul(tmp_path, header):
    wb = make_workbook(tmp_path, "REVUES", [header, "title"],
                       [["glottopol", "Glottopol"]])
    df = load_revues(wb, "REVUES")
    assert df["journal_id"].tolist() == ["glottopol"]


def test_pas_de_colonne_dupliquee_apres_normalisation(tmp_path):
    wb = make_workbook(tmp_path, "REVUES",
                       ["revue_id", "title", "url", "issn_print"],
                       [["glottopol", "Glottopol", "https://exemple.fr", ""]])
    df = load_revues(wb, "REVUES")
    assert not df.columns.duplicated().any()
    assert type(df["journal_id"]).__name__ == "Series"


# ----------------------------------------------------------------------
# Synonymes simultanés : erreur métier claire, pas de traceback pandas
# ----------------------------------------------------------------------

def test_collision_revue_id_et_journal_id(tmp_path):
    wb = make_workbook(tmp_path, "REVUES",
                       ["revue_id", "journal_id", "title"],
                       [["glottopol", "glottopol", "Glottopol"]])
    with pytest.raises(ValueError) as exc:
        load_revues(wb, "REVUES")
    msg = str(exc.value)
    assert "REVUES" in msg
    assert "revue_id" in msg and "journal_id" in msg
    assert "Conservez une seule de ces colonnes" in msg
    assert "truth value" not in msg  # plus l'erreur pandas d'origine


def test_collision_revue_id_et_id(tmp_path):
    # l'alias générique « id » reste accepté seul, mais sa présence à côté
    # d'un alias explicite est une collision comme une autre
    wb = make_workbook(tmp_path, "REVUES",
                       ["revue_id", "id", "title"],
                       [["glottopol", "glottopol", "Glottopol"]])
    with pytest.raises(ValueError) as exc:
        load_revues(wb, "REVUES")
    msg = str(exc.value)
    assert "revue_id" in msg and "« id »" in msg


def test_collision_message_independant_du_nom_de_feuille(tmp_path):
    wb = make_workbook(tmp_path, "REVUE",
                       ["revue_id", "journal_id", "title"],
                       [["glottopol", "glottopol", "Glottopol"]])
    with pytest.raises(ValueError) as exc:
        load_revues(wb, "REVUES")
    assert "REVUE" in str(exc.value)  # le message cite la feuille réelle


# ----------------------------------------------------------------------
# Gabarit officiel corrigé
# ----------------------------------------------------------------------

def test_gabarit_officiel_une_seule_colonne_identifiant():
    wb = pd.ExcelFile(GABARIT)
    raw = wb.parse("REVUES", nrows=1)
    id_cols = [c for c in raw.columns
               if build_site.slugify(str(c)) in {"journal-id", "revue-id", "review-id", "id"}]
    assert id_cols == ["revue_id"]


def test_gabarit_officiel_load_revues():
    df = load_revues(pd.ExcelFile(GABARIT), "REVUES")
    assert len(df) == 1
    assert df["journal_id"].tolist() == ["rev-001"]
    assert not df.columns.duplicated().any()


def test_gabarit_officiel_generation_complete(tmp_path):
    avant = GABARIT.read_bytes()
    out = tmp_path / "dist"
    build_site.build_site(
        excel_path=GABARIT, out_dir=out, covers_dir=None,
        validate_only=False, new_months=None, publish=False,
    )
    pages_revues = sorted(p.name for p in (out / "revues").glob("*.html"))
    assert "index.html" in pages_revues
    assert len(pages_revues) >= 2  # index + au moins la revue du gabarit
    assert (out / "index.html").exists()
    assert GABARIT.read_bytes() == avant  # la génération ne modifie pas le gabarit
