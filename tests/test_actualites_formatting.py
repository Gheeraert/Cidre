# Tests de la mise en forme des actualités :
# - fonctions pures de l'éditeur (actualites_editor, sans ouvrir de fenêtre Tk) ;
# - chaîne de rendu de Cidre (build_site : md_to_html + sanitize_actu_html + CSS).
#
# Lancement : .venv\Scripts\python.exe -m pytest tests/ -v

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from actualites_editor import (
    FORMAT_TAGS, wrap_selection, validate_link_url, escape_href,
    link_open_tag, link_markup,
)
import build_site
from build_site import md_to_html, sanitize_actu_html, DEFAULT_CSS


# ----------------------------------------------------------------------
# Insertion dans l'éditeur (fonctions pures)
# ----------------------------------------------------------------------

def test_wrap_selection_em():
    text = "Un nouvel ouvrage paraît."
    new, c0, c1 = wrap_selection(text, 3, 17, *FORMAT_TAGS["em"])
    assert new == "Un <em>nouvel ouvrage</em> paraît."
    assert new[c0:c1] == "nouvel ouvrage"


def test_wrap_selection_strong():
    text = "Annonce importante."
    new, c0, c1 = wrap_selection(text, 8, 18, *FORMAT_TAGS["strong"])
    assert new == "Annonce <strong>importante</strong>."
    assert new[c0:c1] == "importante"


def test_wrap_selection_small_caps():
    text = "Les PURH participent au salon."
    new, c0, c1 = wrap_selection(text, 4, 8, *FORMAT_TAGS["small-caps"])
    assert new == 'Les <span class="small-caps">PURH</span> participent au salon.'
    assert new[c0:c1] == "PURH"


def test_wrap_selection_vide_curseur_entre_les_balises():
    text = "Début  fin."
    new, c0, c1 = wrap_selection(text, 6, 6, *FORMAT_TAGS["em"])
    assert new == "Début <em></em> fin."
    assert c0 == c1  # curseur entre <em> et </em>
    assert new[:c0].endswith("<em>")
    assert new[c0:].startswith("</em>")


def test_wrap_selection_unicode_francais_preserve():
    text = "L'Âme éphémère — cœur, où çà ?"
    new, c0, c1 = wrap_selection(text, 2, 16, *FORMAT_TAGS["em"])
    assert new[c0:c1] == "Âme éphémère —"
    assert new == "L'<em>Âme éphémère —</em> cœur, où çà ?"


def test_wrap_selection_multiligne_preservee():
    text = "Première ligne\nDeuxième ligne\nTroisième"
    start, end = 0, len("Première ligne\nDeuxième ligne")
    new, c0, c1 = wrap_selection(text, start, end, *FORMAT_TAGS["strong"])
    assert new == "<strong>Première ligne\nDeuxième ligne</strong>\nTroisième"
    assert new[c0:c1] == "Première ligne\nDeuxième ligne"


def test_wrap_selection_bornes_invalides():
    with pytest.raises(ValueError):
        wrap_selection("abc", 2, 1, "<em>", "</em>")
    with pytest.raises(ValueError):
        wrap_selection("abc", 0, 99, "<em>", "</em>")


def test_wrap_selection_imbrication_simple():
    new, c0, c1 = wrap_selection("mot", 0, 3, *FORMAT_TAGS["em"])
    new, c0, c1 = wrap_selection(new, 0, len(new), *FORMAT_TAGS["strong"])
    assert new == "<strong><em>mot</em></strong>"


# ----------------------------------------------------------------------
# Création d'un lien
# ----------------------------------------------------------------------

def test_lien_valide_http_et_https():
    assert validate_link_url("https://exemple.fr") == "https://exemple.fr"
    assert validate_link_url("  http://exemple.fr/page  ") == "http://exemple.fr/page"


@pytest.mark.parametrize("bad", [
    "javascript:alert(1)",
    "JAVASCRIPT:alert(1)",
    "data:text/html,x",
    "exemple.fr",          # pas de protocole
    "ftp://exemple.fr",
    "https://exemple.fr/a b",  # espace
    "",
])
def test_lien_invalide_refuse(bad):
    with pytest.raises(ValueError):
        validate_link_url(bad)


def test_lien_sur_selection():
    open_tag = link_open_tag("https://exemple.fr/prog")
    new, c0, c1 = wrap_selection("Voir le programme.", 0, 17, open_tag, "</a>")
    assert new == '<a href="https://exemple.fr/prog">Voir le programme</a>.'
    assert new[c0:c1] == "Voir le programme"


def test_lien_href_esperluette_et_guillemets_echappes():
    markup = link_markup('https://example.org/p?a=1&b=2', "Programme")
    assert markup == '<a href="https://example.org/p?a=1&amp;b=2">Programme</a>'
    assert escape_href('https://x.fr/"onmouseover=') == "https://x.fr/&quot;onmouseover="


def test_lien_sans_selection_url_comme_texte():
    markup = link_markup("https://exemple.fr/p?a=1&b=2")
    assert markup == ('<a href="https://exemple.fr/p?a=1&amp;b=2">'
                      "https://exemple.fr/p?a=1&amp;b=2</a>")


# ----------------------------------------------------------------------
# Rendu Cidre : md_to_html + sanitize_actu_html
# ----------------------------------------------------------------------

SAMPLE = (
    '<p>Les <span class="small-caps">PURH</span> publient un <em>nouvel ouvrage</em> '
    "particulièrement <strong>important</strong>.</p>\n"
    '<p><a href="https://example.org/programme?a=1&amp;b=2">Consulter le programme</a></p>'
)


@pytest.mark.skipif(build_site.md is None, reason="python-markdown non installé")
def test_rendu_balises_non_echappees():
    out = sanitize_actu_html(md_to_html(SAMPLE))
    assert "&lt;" not in out  # aucune balise affichée littéralement
    assert "<em>nouvel ouvrage</em>" in out
    assert "<strong>important</strong>" in out


@pytest.mark.skipif(build_site.md is None, reason="python-markdown non installé")
def test_rendu_small_caps_conserve():
    out = sanitize_actu_html(md_to_html(SAMPLE))
    assert "small-caps'>PURH</span>" in out or 'small-caps">PURH</span>' in out


@pytest.mark.skipif(build_site.md is None, reason="python-markdown non installé")
def test_rendu_lien_cliquable_url_intacte():
    out = sanitize_actu_html(md_to_html(SAMPLE))
    assert "href='https://example.org/programme?a=1&amp;b=2'" in out
    assert "target='_blank'" in out and "rel='noopener'" in out
    assert ">Consulter le programme</a>" in out


def test_rendu_ancien_contenu_i_et_b_conserves():
    out = sanitize_actu_html("<p>Texte avec <i>italique</i> et <b>gras</b>.</p>")
    assert "<i>italique</i>" in out
    assert "<b>gras</b>" in out


def test_rendu_protocole_dangereux_neutralise():
    out = sanitize_actu_html('<p><a href="javascript:alert(1)">clic</a></p>')
    assert "javascript:" not in out
    assert "<a>clic</a>" in out  # le texte reste, le lien est neutralisé


def test_rendu_span_classe_arbitraire_retiree():
    out = sanitize_actu_html('<p><span class="autre" style="color:red">x</span></p>')
    assert out == "<p><span>x</span></p>"
    out = sanitize_actu_html("<p><span class='small-caps'>PURH</span></p>")
    assert out == "<p><span class='small-caps'>PURH</span></p>"


def test_rendu_script_et_onclick_toujours_supprimes():
    out = sanitize_actu_html('<p onclick="x()">a</p><script>alert(1)</script>')
    assert "<script" not in out
    assert "onclick" not in out


def test_rendu_idempotent():
    once = sanitize_actu_html(SAMPLE)
    assert sanitize_actu_html(once) == once


def test_css_small_caps_present():
    assert ".small-caps" in DEFAULT_CSS
    assert "font-variant: small-caps" in DEFAULT_CSS
