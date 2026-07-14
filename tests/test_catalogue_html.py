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

NODE = shutil.which("node")


def _book(index: int, **overrides):
    row = {
        "slug": f"ouvrage-{index}",
        "titre_norm": f"Titre {index}",
        "sous_titre_norm": f"Sous-titre {index}",
        "credit_ligne": f"Auteur {index}",
        "id13": f"978000000{index:04d}",
        "collection": "Essais" if index % 2 == 0 else "Romans",
        "format_site": "Broché" if index % 3 == 0 else "Numérique",
        "year": 2026 if index <= 80 else 2025,
        "cover_file": f"cover-{index}.jpg",
        "price_str": "12 €",
        "availability_label": "Disponible",
        "physical_str": "200 p.",
        "date_parution_norm": "2026-01-01",
        "openedition_url": "",
        "excerpt": f"Résumé {index}",
    }
    row.update(overrides)
    return row


def _build_catalogue(tmp_path: Path, books: pd.DataFrame, existing_covers=()) -> str:
    if existing_covers:
        covers_dir = tmp_path / "covers"
        covers_dir.mkdir()
        for name in existing_covers:
            (covers_dir / name).write_bytes(b"fake image")
    bs.build_catalogue_page(bs.SiteConfig(), books, tmp_path)
    return (tmp_path / "catalogue.html").read_text(encoding="utf-8")


def test_catalogue_html_contient_toutes_les_cartes_et_leurs_attributs(tmp_path):
    books = pd.DataFrame([
        _book(1, collection='Essais " & <spéciaux>', format_site='Broché & <format>'),
        _book(2),
    ])
    html = _build_catalogue(tmp_path, books, existing_covers=["cover-1.jpg"])

    assert html.count('class="card catalogue-card"') == 2
    assert './livres/ouvrage-1.html' in html
    assert './livres/ouvrage-2.html' in html
    assert 'data-collection="Essais &quot; &amp; &lt;spéciaux&gt;"' in html
    assert 'data-format="Broché &amp; &lt;format&gt;"' in html
    assert 'data-year="2026"' in html
    assert 'data-search="Titre 1 Sous-titre 1 Auteur 1 9780000000001 Essais &quot; &amp; &lt;spéciaux&gt; Broché &amp; &lt;format&gt;"' in html
    assert 'loading="lazy" decoding="async"' in html
    assert not re.search(r'class="card catalogue-card"[^>]*\shidden', html)


def test_catalogue_html_ignore_les_couvertures_absentes(tmp_path):
    books = pd.DataFrame([
        _book(1, slug="avec-couverture", cover_file="presente.jpg"),
        _book(2, slug="sans-couverture", cover_file="absente.jpg"),
    ])
    html = _build_catalogue(tmp_path, books, existing_covers=["presente.jpg"])

    assert html.count('class="card catalogue-card"') == 2
    assert './livres/avec-couverture.html' in html
    assert './livres/sans-couverture.html' in html
    assert "src='./covers/presente.jpg'" in html
    assert "data-lightbox-src='./covers/presente.jpg'" in html
    assert 'loading="lazy" decoding="async"' in html
    assert "src='./covers/absente.jpg'" not in html
    assert "data-lightbox-src='./covers/absente.jpg'" not in html


def test_catalogue_html_est_complet_sans_catalogue_json(tmp_path):
    books = pd.DataFrame([_book(1), _book(2)])
    html = _build_catalogue(tmp_path, books)

    assert not (tmp_path / "catalogue.json").exists()
    assert html.count('class="card catalogue-card"') == 2
    assert 'id="catalogue-toolbar" class="toolbar" hidden' in html
    assert '<button type="button" id="more" class="btn" hidden>' in html
    assert '<span id="count">2</span>' in html


def test_catalogue_json_reste_un_export_independant(tmp_path):
    books = pd.DataFrame([_book(1), _book(2)])
    _build_catalogue(tmp_path, books)
    bs.build_catalogue_json(books, tmp_path)

    records = json.loads((tmp_path / "catalogue.json").read_text(encoding="utf-8"))
    assert [record["slug"] for record in records] == ["ouvrage-1", "ouvrage-2"]
    assert [record["id13"] for record in records] == ["9780000000001", "9780000000002"]


def test_catalogue_script_ne_construit_ni_ne_charge_les_cartes():
    assert 'fetch("./catalogue.json")' not in bs.DEFAULT_JS
    assert "loadCatalogue" not in bs.DEFAULT_JS
    assert "function card(" not in bs.DEFAULT_JS
    assert ".innerHTML" not in bs.DEFAULT_JS
    assert 'querySelectorAll(".catalogue-card")' in bs.DEFAULT_JS


CATALOGUE_DOM_HARNESS = r"""
const fs = require("fs");
const script = fs.readFileSync(process.argv[2], "utf8");
const missingGrid = process.argv[3] === "missing-grid";

class El {
  constructor(dataset = {}) {
    this.dataset = dataset;
    this.value = "";
    this.hidden = true;
    this.textContent = "";
    this.handlers = {};
  }
  addEventListener(type, callback) {
    (this.handlers[type] = this.handlers[type] || []).push(callback);
  }
  trigger(type) {
    (this.handlers[type] || []).forEach((callback) => callback({ preventDefault() {} }));
  }
}

const toolbar = new El();
const query = new El();
const grid = new El();
const count = new El();
const collection = new El();
const format = new El();
const year = new El();
const more = new El();
const empty = new El();
const cards = [];
for (let i = 1; i <= 125; i += 1) {
  const card = new El({
    collection: i % 2 === 0 ? "Essais" : "Romans",
    format: i % 3 === 0 ? "Broché" : "Numérique",
    year: i <= 80 ? "2026" : "2025",
    search: `titre ${i} auteur ${i} isbn-${String(i).padStart(3, "0")}`,
  });
  card.hidden = false;
  cards.push(card);
}

const elements = {
  "catalogue-toolbar": toolbar,
  q: query,
  out: missingGrid ? null : grid,
  count,
  f_collection: collection,
  f_format: format,
  f_year: year,
  more,
  "catalogue-empty": empty,
};
global.document = {
  getElementById: (id) => elements[id] || null,
  querySelectorAll: (selector) => selector === ".catalogue-card" ? cards : [],
};
global.setTimeout = (callback) => { callback(); return 1; };
global.clearTimeout = () => {};

eval(script);

function state() {
  return {
    count: count.textContent,
    visible: cards.filter((card) => !card.hidden).length,
    toolbarHidden: toolbar.hidden,
    moreHidden: more.hidden,
    emptyHidden: empty.hidden,
  };
}
const states = { initial: state() };
more.trigger("click");
states.afterMore = state();
collection.value = "Essais";
collection.trigger("change");
states.collection = state();
format.value = "Broché";
format.trigger("change");
states.format = state();
year.value = "2026";
year.trigger("change");
states.year = state();
query.value = "isbn-006";
query.trigger("input");
states.search = state();
query.value = "introuvable";
query.trigger("input");
states.empty = state();
console.log(JSON.stringify(states));
"""


def _catalogue_js_state(tmp_path: Path, missing_grid: bool = False):
    harness = tmp_path / "catalogue_harness.js"
    script = tmp_path / "catalogue.js"
    harness.write_text(CATALOGUE_DOM_HARNESS, encoding="utf-8")
    script.write_text(bs.DEFAULT_JS, encoding="utf-8")
    result = subprocess.run(
        [NODE, str(harness), str(script), "missing-grid" if missing_grid else "ok"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(NODE is None, reason="node indisponible")
def test_catalogue_script_filtre_et_revele_par_lots(tmp_path):
    states = _catalogue_js_state(tmp_path)

    assert states["initial"] == {
        "count": "125", "visible": 60, "toolbarHidden": False,
        "moreHidden": False, "emptyHidden": True,
    }
    assert states["afterMore"]["visible"] == 120
    assert states["collection"] == {
        "count": "62", "visible": 60, "toolbarHidden": False,
        "moreHidden": False, "emptyHidden": True,
    }
    assert states["format"] == {
        "count": "20", "visible": 20, "toolbarHidden": False,
        "moreHidden": True, "emptyHidden": True,
    }
    assert states["year"] == {
        "count": "13", "visible": 13, "toolbarHidden": False,
        "moreHidden": True, "emptyHidden": True,
    }
    assert states["search"] == {
        "count": "1", "visible": 1, "toolbarHidden": False,
        "moreHidden": True, "emptyHidden": True,
    }
    assert states["empty"] == {
        "count": "0", "visible": 0, "toolbarHidden": False,
        "moreHidden": True, "emptyHidden": False,
    }


@pytest.mark.skipif(NODE is None, reason="node indisponible")
def test_catalogue_script_ne_revele_pas_les_controles_si_le_dom_est_incomplet(tmp_path):
    states = _catalogue_js_state(tmp_path, missing_grid=True)
    assert states["initial"]["toolbarHidden"] is True
    assert states["initial"]["visible"] == 125
