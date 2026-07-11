# Tests de normalize_excel_text (nettoyage des retours chariot OOXML "_x000D_")
# Lancement : .venv\Scripts\python.exe -m pytest tests/ -v

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from build_site import normalize_excel_text, normalize_editorial_columns


# --- Cas demandés explicitement ---

def test_x000d_simple_devient_saut_de_ligne():
    assert normalize_excel_text("Avant_x000D_Après") == "Avant\nAprès"


def test_x000d_suivi_de_newline_ne_double_pas():
    assert normalize_excel_text("Avant_x000D_\nAprès") == "Avant\nAprès"


def test_crlf_reel_devient_lf():
    assert normalize_excel_text("Avant\r\nAprès") == "Avant\nAprès"


def test_cr_seul_devient_lf():
    assert normalize_excel_text("Avant\rAprès") == "Avant\nAprès"


def test_transition_html_entre_paragraphes():
    out = normalize_excel_text("<p>Avant</p>_x000D_ _x000D_<p>Après</p>")
    assert "_x000D_" not in out
    assert out == "<p>Avant</p>\n<p>Après</p>"


# --- Formes observées dans le classeur réel (suffixe " " après chaque _x000D_) ---

def test_forme_reelle_double_x000d_avec_espaces():
    src = "…des genres littéraires variés.</p>_x000D_ _x000D_ <p>Cet ouvrage collectif…"
    out = normalize_excel_text(src)
    assert out == "…des genres littéraires variés.</p>\n<p>Cet ouvrage collectif…"


def test_forme_reelle_br_suivi_x000d():
    out = normalize_excel_text("semence.(Lily Robert-Foley)<br />_x000D_ * groupe d'écrivaines</p>")
    assert out == "semence.(Lily Robert-Foley)<br />\n* groupe d'écrivaines</p>"


def test_texte_brut_coupe_en_pleine_phrase():
    out = normalize_excel_text("la Querelle des_x000D_ Anciens et des Modernes")
    assert out == "la Querelle des\nAnciens et des Modernes"


# --- Robustesse ---

def test_x000d_successifs_sans_espaces():
    out = normalize_excel_text("A_x000D__x000D__x000D_B")
    assert "_x000D_" not in out
    assert out == "A\n\nB"  # au plus une ligne vide


def test_x000d_entoure_d_espaces():
    assert normalize_excel_text("A  _x000D_  B") == "A\nB"


def test_chaine_vide():
    assert normalize_excel_text("") == ""


def test_none():
    assert normalize_excel_text(None) == ""


def test_nan_pandas():
    assert normalize_excel_text(float("nan")) == ""


def test_valeur_numerique():
    assert normalize_excel_text(42) == "42"


def test_unicode_francais_preserve():
    s = "Édition – L’œuvre d’Évelyne : « À propos du XVIIe siècle » — cœur, œil, Ç, æ, …, insécable !"
    assert normalize_excel_text(s) == s


def test_chaine_propre_strictement_inchangee():
    s = "<p>Un paragraphe <em>simple</em>, sans caractère parasite.</p>"
    assert normalize_excel_text(s) == s


def test_saut_de_ligne_simple_preserve():
    # Deux lignes séparées par un \n légitime ne doivent pas être recollées
    assert normalize_excel_text("Ligne 1\nLigne 2") == "Ligne 1\nLigne 2"


def test_ligne_vide_preservee_pour_markdown():
    # Une ligne vide (séparateur de paragraphes Markdown) est conservée
    assert normalize_excel_text("Para 1\n\nPara 2") == "Para 1\n\nPara 2"


def test_x005f_echappement_litteral_preserve():
    # "_x005F_x000D_" encode la chaîne littérale "_x000D_" : ne pas la convertir
    assert "\n" not in normalize_excel_text("code _x005F_x000D_ littéral")


def test_casse_minuscule():
    assert normalize_excel_text("A_x000d_B") == "A\nB"


def test_espaces_en_fin_de_ligne_supprimes():
    assert normalize_excel_text("A   \nB") == "A\nB"


# --- Application aux colonnes de DataFrame ---

def test_normalize_editorial_columns():
    df = pd.DataFrame({
        "Description longue": ["<p>Un</p>_x000D_ _x000D_ <p>Deux</p>", None],
        "id13": ["9791024000000", "9791024000001"],
    })
    normalize_editorial_columns(df, ["Description longue", "colonne_absente"])
    assert df["Description longue"][0] == "<p>Un</p>\n<p>Deux</p>"
    assert df["Description longue"][1] == ""
    # les colonnes non listées ne sont pas touchées
    assert df["id13"][0] == "9791024000000"
