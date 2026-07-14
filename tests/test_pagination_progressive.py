# Tests de la pagination progressive des cartes sur les pages individuelles
# de collections et de revues : lots de CARD_PAGE_SIZE (le même 60 que le
# catalogue), bouton « Afficher plus », toutes les cartes présentes sans JS.
#
# Le JavaScript est exécuté avec Node (déjà présent sur la machine) contre un
# stub DOM minimal — pas de dépendance navigateur.
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_site as bs

GABARIT = ROOT / "gabarit" / "purh_site_excel_gabarit.xlsx"
CLASSEUR_REEL = ROOT / "20260630_purh_master_v25.xlsx"
NODE = shutil.which("node")

CARD_RE = re.compile(r'<div class="card">')
CARD_LINK_RE = re.compile(r'href="\.\./livres/([^"]+\.html)"')
BUTTON_HTML = "<button type='button' class='btn progressive-card-more' hidden>Afficher plus</button>"

# --- Stub DOM minimal pour exécuter PROGRESSIVE_CARDS_JS sous Node ---------
# usage : node harness.js <script.js> <nb_cartes> <nb_clics>
DOM_STUB_JS = r"""
const fs = require("fs");
const scriptSrc = fs.readFileSync(process.argv[2], "utf8");
const n = parseInt(process.argv[3], 10);
const clicks = parseInt(process.argv[4], 10);

class El {
  constructor(classes) {
    this._c = new Set(classes);
    this.dataset = {};
    this.hidden = false;
    this.attrs = {};
    this.handlers = {};
    this.id = "";
    this.nextElementSibling = null;
    this.children = [];
  }
  get classList() {
    const s = this._c;
    return {
      contains: (c) => s.has(c),
      add: (c) => s.add(c),
      remove: (c) => s.delete(c),
      toggle: (c, force) => {
        if (force === undefined) { s.has(c) ? s.delete(c) : s.add(c); }
        else if (force) s.add(c); else s.delete(c);
      },
    };
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); }
  click() { (this.handlers.click || []).forEach((f) => f()); }
  querySelectorAll(sel) {
    if (sel === ".card") return this.children.filter((c) => c._c.has("card"));
    return [];
  }
  querySelector(sel) {
    if (sel === ".progressive-card-more")
      return this.children.find((c) => c._c.has("progressive-card-more")) || null;
    return null;
  }
}

const grid = new El(["grid", "progressive-card-grid"]);
for (let i = 0; i < n; i++) grid.children.push(new El(["card"]));
const actions = new El(["progressive-card-actions"]);
const btn = new El(["btn", "progressive-card-more"]);
btn.hidden = true; // attribut hidden émis côté Python
actions.children = [btn];
grid.nextElementSibling = actions;

global.document = {
  querySelectorAll: (sel) => (sel === ".progressive-card-grid" ? [grid] : []),
};

eval(scriptSrc);

function visibleCount() {
  return grid.children.filter((c) => !c._c.has("card-progressive-hidden")).length;
}
const states = [visibleCount()];
const btnVisible = [!btn.hidden];
const expanded = [btn.attrs["aria-expanded"] || null];
for (let i = 0; i < clicks; i++) {
  btn.click();
  states.push(visibleCount());
  btnVisible.push(!btn.hidden);
  expanded.push(btn.attrs["aria-expanded"] || null);
}
console.log(JSON.stringify({
  states, btnVisible, expanded,
  ariaControls: btn.attrs["aria-controls"] || null,
  gridId: grid.id,
}));
"""


def _run_js(tmp_path, n_cards, clicks):
    harness = tmp_path / "harness.js"
    script = tmp_path / "progressive.js"
    harness.write_text(DOM_STUB_JS, encoding="utf-8")
    script.write_text(bs.PROGRESSIVE_CARDS_JS, encoding="utf-8")
    out = subprocess.run([NODE, str(harness), str(script), str(n_cards), str(clicks)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


# --- Fixtures synthétiques ---------------------------------------------------

def _book_row(i, cid="col-essais", name="Essais"):
    return {
        "titre_norm": f"Ouvrage {i:03d}",
        "sous_titre_norm": "",
        "credit_ligne": "",
        "collection": name,
        "collection_id": cid,
        "format_site": "",
        "date_parution_norm": None,
        "year": 2000 + i,  # années distinctes : tri décroissant vérifiable
        "id13": f"9782{i:09d}",
        "openedition_url": "",
        "cover_file": "",
        "price_str": "",
        "availability_label": "",
        "physical_str": "",
        "Description longue": "",
        "Description courte": "",
        "Table des matières": "",
        "order_url": "",
        "slug": f"ouvrage-{i:03d}",
    }


BOOK_COLS = list(_book_row(0))


def _gen_collection(tmp_path, n_books):
    cfg = bs.SiteConfig()
    books = pd.DataFrame([_book_row(i) for i in range(1, n_books + 1)],
                         columns=BOOK_COLS)
    collections = pd.DataFrame([{
        "collection_id": "col-essais", "name": "Essais", "slug": "essais",
        "description_md": "", "directeurs": "", "comite_scientifique": "",
        "issn_print": "", "is_active": 1,
    }])
    bs.build_collections(cfg, books, collections, tmp_path)
    return (tmp_path / "collections" / "essais.html").read_text(encoding="utf-8")


def _gen_revue(tmp_path, n_books):
    cfg = bs.SiteConfig()
    books = pd.DataFrame(
        [_book_row(i, cid="austriaca", name="Austriaca") for i in range(1, n_books + 1)],
        columns=BOOK_COLS)
    revues = pd.DataFrame([{
        "journal_id": "austriaca", "title": "Austriaca", "slug": "austriaca",
        "url": "", "issn_print": "", "issn_online": "", "description_md": "",
        "direction": "", "comite_scientifique": "", "contact_email": "",
        "is_active": 1, "order": None,
    }])
    bs.build_revues(cfg, books, revues, tmp_path)
    return (tmp_path / "revues" / "austriaca.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------
# 1. Collection avec 0 carte : message existant, aucun bouton
# ---------------------------------------------------------------

def test_collection_sans_carte(tmp_path):
    html = _gen_collection(tmp_path, 0)
    assert "Aucun ouvrage rattaché trouvé (vérifier collection_id dans le catalogue)." in html
    assert "progressive-card-more" not in html
    assert not CARD_RE.findall(html)


# ---------------------------------------------------------------
# 2. Collection avec 1 carte : carte visible, aucun bouton
# ---------------------------------------------------------------

def test_collection_une_carte(tmp_path):
    html = _gen_collection(tmp_path, 1)
    assert len(CARD_RE.findall(html)) == 1
    assert "progressive-card-more" not in html
    assert "card-progressive-hidden" not in html.split("<style>")[-1].split("</style>")[-1]


# ---------------------------------------------------------------
# 3. Collection avec 60 cartes : tout visible, aucun bouton
# ---------------------------------------------------------------

def test_collection_60_cartes(tmp_path):
    html = _gen_collection(tmp_path, 60)
    assert len(CARD_RE.findall(html)) == 60
    assert "progressive-card-more" not in html
    assert "progressive-card-grid" in html  # grille commune tout de même posée


# ---------------------------------------------------------------
# 4. Collection avec 61 cartes : bouton présent, 61e révélable
# ---------------------------------------------------------------

def test_collection_61_cartes_html(tmp_path):
    html = _gen_collection(tmp_path, 61)
    assert len(CARD_RE.findall(html)) == 61  # toutes présentes sans JS
    assert BUTTON_HTML in html
    assert bs.PROGRESSIVE_CARDS_JS in html


@pytest.mark.skipif(NODE is None, reason="node indisponible")
def test_collection_61_cartes_js(tmp_path):
    res = _run_js(tmp_path, 61, 1)
    assert res["states"] == [60, 61]
    assert res["btnVisible"] == [True, False]  # masqué quand tout est visible
    assert res["expanded"] == ["false", "true"]
    assert res["ariaControls"] == res["gridId"] != ""


# ---------------------------------------------------------------
# 5. Collection avec 125 cartes : états 60, 120, 125
# ---------------------------------------------------------------

@pytest.mark.skipif(NODE is None, reason="node indisponible")
def test_collection_125_cartes_js(tmp_path):
    assert len(CARD_RE.findall(_gen_collection(tmp_path, 125))) == 125
    res = _run_js(tmp_path, 125, 2)
    assert res["states"] == [60, 120, 125]
    assert res["btnVisible"] == [True, True, False]


# ---------------------------------------------------------------
# 6. Revue avec 2 numéros : aucun bouton
# ---------------------------------------------------------------

def test_revue_2_numeros(tmp_path):
    html = _gen_revue(tmp_path, 2)
    assert len(CARD_RE.findall(html)) == 2
    assert "progressive-card-more" not in html


# ---------------------------------------------------------------
# 7. Revue à 97 numéros (profil Austriaca) : 60 puis 97
# ---------------------------------------------------------------

@pytest.mark.skipif(NODE is None, reason="node indisponible")
def test_revue_97_numeros_js(tmp_path):
    html = _gen_revue(tmp_path, 97)
    assert len(CARD_RE.findall(html)) == 97
    assert BUTTON_HTML in html
    res = _run_js(tmp_path, 97, 1)
    assert res["states"] == [60, 97]
    assert res["btnVisible"] == [True, False]


# ---------------------------------------------------------------
# 8. Ordre des cartes inchangé (année décroissante, titre croissant)
# ---------------------------------------------------------------

def test_ordre_conserve(tmp_path):
    html = _gen_collection(tmp_path, 61)
    ordre = CARD_LINK_RE.findall(html)
    attendu = [f"ouvrage-{i:03d}.html" for i in range(61, 0, -1)]  # années décroissantes
    assert ordre == attendu


# ---------------------------------------------------------------
# 9. Sans JavaScript : toutes les cartes lisibles, bouton non focalisable
# ---------------------------------------------------------------

def test_sans_javascript(tmp_path):
    html = _gen_revue(tmp_path, 97)
    assert len(CARD_RE.findall(html)) == 97          # rien de masqué côté HTML
    # la classe de masquage n'est posée par aucun élément HTML (JS uniquement)
    assert not re.search(r'<div class="[^"]*card-progressive-hidden', html)
    assert "hidden>Afficher plus</button>" in html   # bouton inerte masqué sans JS


# ---------------------------------------------------------------
# 10. Collections et revues : même helper, même script, même lot
# ---------------------------------------------------------------

def test_meme_mecanisme_collections_revues(tmp_path):
    hc = _gen_collection(tmp_path / "c", 61)
    hr = _gen_revue(tmp_path / "r", 61)
    for html in (hc, hr):
        assert "class='grid progressive-card-grid'" in html
        assert BUTTON_HTML in html
        assert bs.PROGRESSIVE_CARDS_JS in html
    assert bs.CARD_PAGE_SIZE == 60
    assert f"var SIZE = {bs.CARD_PAGE_SIZE};" in bs.PROGRESSIVE_CARDS_JS


# ---------------------------------------------------------------
# 11. Catalogue général : lots de 60 inchangés
# ---------------------------------------------------------------

def test_catalogue_lots_de_60(tmp_path):
    assert f"const PAGE_SIZE = {bs.CARD_PAGE_SIZE};" in bs.DEFAULT_JS
    assert "const PAGE_SIZE = 60;" in bs.DEFAULT_JS
    books = pd.DataFrame([_book_row(i) for i in range(1, 62)], columns=BOOK_COLS)
    bs.build_catalogue_page(bs.SiteConfig(), books, tmp_path)
    html = (tmp_path / "catalogue.html").read_text(encoding="utf-8")
    assert "const PAGE_SIZE = 60;" in html
    assert 'id="more"' in html and 'type="button"' in html and "Afficher plus" in html


# ---------------------------------------------------------------
# 12. Génération réelle : liens valides, pages témoins, classeur intact
# ---------------------------------------------------------------

@pytest.mark.skipif(not CLASSEUR_REEL.exists(),
                    reason="classeur de production absent de cette machine")
def test_generation_complete_classeur_reel(tmp_path):
    avant = CLASSEUR_REEL.read_bytes()
    out = tmp_path / "dist"
    bs.build_site(CLASSEUR_REEL, out, covers_dir=None)
    assert CLASSEUR_REEL.read_bytes() == avant, "le classeur de production a été modifié"

    # Austriaca : 97 cartes, bouton, script
    html = (out / "revues" / "austriaca.html").read_text(encoding="utf-8")
    assert len(CARD_RE.findall(html)) == 97
    assert BUTTON_HTML in html
    assert bs.PROGRESSIVE_CARDS_JS in html

    # Revue normande d'histoire du sport : 2 cartes, pas de bouton
    html = (out / "revues" / "revue-normande-d-histoire-du-sport.html").read_text(encoding="utf-8")
    assert len(CARD_RE.findall(html)) == 2
    assert "progressive-card-more" not in html

    # Glottopol : message, pas de bouton
    html = (out / "revues" / "glottopol.html").read_text(encoding="utf-8")
    assert "Aucun numéro rattaché trouvé." in html
    assert "progressive-card-more" not in html

    # Toutes les pages collections + revues : bouton ssi > 60 cartes,
    # et chaque carte pointe vers une fiche livres/ existante
    erreurs = []
    for dossier in ("collections", "revues"):
        for page in (out / dossier).glob("*.html"):
            if page.name == "index.html":
                continue
            h = page.read_text(encoding="utf-8")
            n = len(CARD_RE.findall(h))
            a_bouton = "progressive-card-more" in h
            if a_bouton != (n > bs.CARD_PAGE_SIZE):
                erreurs.append(f"{dossier}/{page.name} : {n} cartes, bouton={a_bouton}")
            for target in CARD_LINK_RE.findall(h):
                if not (out / "livres" / target).exists():
                    erreurs.append(f"{dossier}/{page.name} -> livres/{target} (inexistant)")
    assert not erreurs, "Pages incohérentes :\n" + "\n".join(erreurs)
