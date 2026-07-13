import csv
import json
import sys
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_site as bs
from cidre import routes
from cidre.data_models import load_config
from cidre.excel_data import detect_books_sheet, load_books, load_collections, load_revues
from cidre.url_inventory import INVENTORY_COLUMNS, collect_url_inventory, main as inventory_main


BOOK_HEADERS = [
    "id13", "slug", "titre_norm", "sous_titre_norm", "credit_ligne",
    "collection", "collection_id", "date_parution_norm", "format_site",
    "price", "availability", "cover_file", "Description courte",
    "Description longue", "order_url", "openedition_url", "active_site",
]


def _book(isbn, slug, title, collection="Essais", collection_id="col-essais"):
    return [
        isbn, slug, title, "", "", collection, collection_id,
        "2026-01-01", "Broche", "12", "Disponible", "", "Resume", "",
        "", "", 1,
    ]


def _workbook(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CONFIG"
    ws.append(["key", "value"])
    for key, value in [
        ("site_title", "Site test"),
        ("books_sheet", "CATALOGUE"),
        ("pages_sheet", "PAGES"),
        ("collections_sheet", "COLLECTIONS"),
        ("revues_sheet", "REVUES"),
        ("contacts_sheet", "CONTACTS"),
    ]:
        ws.append([key, value])

    books = wb.create_sheet("CATALOGUE")
    books.append(BOOK_HEADERS)
    books.append(_book("9782877750001", "mon-livre-2", "Slug deja suffixe"))
    books.append(_book("9782877750002", "", "Fallback ISBN"))
    books.append(_book("9782877750003", "meme-slug", "Premier doublon"))
    books.append(_book("9782877750004", "meme-slug", "Second doublon"))
    books.append(_book("", "", "Sans ISBN"))
    books.append(_book("", "", "Sans ISBN"))
    books.append(_book("9782877750005", "livre-actu", "Livre actu"))
    books.append(_book("9782877750006", "numero-revue", "Numero revue", "Revue test", "revue-test"))

    pages = wb.create_sheet("PAGES")
    pages.append(["slug", "title", "content_md", "is_published"])
    pages.append(["presentation", "Presentation", "Texte", 1])
    pages.append(["brouillon", "Brouillon", "Texte", 0])
    pages.append(["actualites", "Actualites", "Texte", 1])

    collections = wb.create_sheet("COLLECTIONS")
    collections.append(["collection_id", "name", "slug", "is_active"])
    collections.append(["col-essais", "Essais", "essais", 1])

    revues = wb.create_sheet("REVUES")
    revues.append(["journal_id", "title", "slug", "is_active"])
    revues.append(["revue-test", "Revue test", "revue-test", 1])

    actualites = wb.create_sheet("ACTUALITES")
    actualites.append(["title", "image", "date", "text", "is_active", "id13", "link"])
    actualites.append(["Actu livre", "", "2026-01-01", "Texte", 1, "9782877750005", ""])

    contacts = wb.create_sheet("CONTACTS")
    contacts.append(["label", "name", "role", "email", "phone", "address", "order", "is_active"])

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _books(path: Path):
    wb = pd.ExcelFile(path)
    cfg = load_config(wb, "CONFIG")
    return load_books(wb, detect_books_sheet(wb, cfg.books_sheet))


def test_provenance_slug_explicite_non_unicifie(tmp_path):
    books = _books(_workbook(tmp_path / "site.xlsx"))
    row = books[books["titre_norm"] == "Slug deja suffixe"].iloc[0]
    assert row["_source_slug"] == "mon-livre-2"
    assert row["_slug_candidate"] == "mon-livre-2"
    assert row["slug"] == "mon-livre-2"
    assert row["_slug_was_uniquified"] is False
    assert row["_slug_origin"] == "explicit"


def test_provenance_doublon_explicite(tmp_path):
    books = _books(_workbook(tmp_path / "site.xlsx"))
    first = books[books["titre_norm"] == "Premier doublon"].iloc[0]
    second = books[books["titre_norm"] == "Second doublon"].iloc[0]
    assert first["_slug_candidate"] == "meme-slug"
    assert first["slug"] == "meme-slug"
    assert first["_slug_was_uniquified"] is False
    assert first["_slug_origin"] == "explicit"
    assert second["_slug_candidate"] == "meme-slug"
    assert second["slug"] == "meme-slug-2"
    assert second["_slug_was_uniquified"] is True
    assert second["_slug_origin"] == "explicit"


def test_provenance_fallbacks(tmp_path):
    books = _books(_workbook(tmp_path / "site.xlsx"))
    isbn = books[books["titre_norm"] == "Fallback ISBN"].iloc[0]
    assert isbn["_slug_origin"] == "fallback_title_isbn"
    assert isbn["_slug_candidate"] == "fallback-isbn-9782877750002"
    assert isbn["slug"] == "fallback-isbn-9782877750002"

    sans = books[books["titre_norm"] == "Sans ISBN"]
    assert sans.iloc[0]["_slug_origin"] == "fallback_title"
    assert sans.iloc[0]["_slug_candidate"] == "sans-isbn"
    assert sans.iloc[0]["slug"] == "sans-isbn"
    assert sans.iloc[0]["_slug_was_uniquified"] is False
    assert sans.iloc[1]["_slug_candidate"] == "sans-isbn"
    assert sans.iloc[1]["slug"] == "sans-isbn-2"
    assert sans.iloc[1]["_slug_was_uniquified"] is True


def test_coherence_producteurs_consommateurs(tmp_path):
    wb = _workbook(tmp_path / "site.xlsx")
    out = tmp_path / "dist"
    bs.build_site(wb, out, covers_dir=None, force_alerts=True)

    books = _books(wb)
    livre_actu = books[books["titre_norm"] == "Livre actu"].iloc[0]
    numero_revue = books[books["titre_norm"] == "Numero revue"].iloc[0]
    assert (out / routes.book_public_path(livre_actu["slug"])).exists()

    actualites = json.loads((out / "assets" / "actualites.json").read_text(encoding="utf-8"))
    assert actualites[0]["href"] == routes.actualite_book_href(livre_actu["slug"], ".")

    wb_xl = pd.ExcelFile(wb)
    cfg = load_config(wb_xl, "CONFIG")
    collections = load_collections(wb_xl, cfg.collections_sheet)
    revues = load_revues(wb_xl, cfg.revues_sheet)
    collection = collections.iloc[0]
    revue = revues.iloc[0]
    assert (out / routes.collection_public_path(collection["slug"], collection["collection_id"])).exists()
    assert routes.collection_href(collection["slug"], collection["collection_id"], "..") in (
        out / routes.book_public_path(livre_actu["slug"])
    ).read_text(encoding="utf-8")
    assert (out / routes.revue_public_path(revue["slug"], revue["title"], revue["journal_id"])).exists()
    assert routes.revue_href(revue["slug"], revue["title"], revue["journal_id"], "..") in (
        out / routes.book_public_path(numero_revue["slug"])
    ).read_text(encoding="utf-8")


def test_inventaire_csv(tmp_path):
    wb = _workbook(tmp_path / "site.xlsx")
    before = wb.read_bytes()
    csv_path = tmp_path / "audit" / "url_inventory.csv"

    exit_code = inventory_main(["--excel", str(wb), "--csv", str(csv_path)])

    assert exit_code == 0
    assert wb.read_bytes() == before
    assert not (tmp_path / "dist").exists()
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert rows
    assert list(rows[0].keys()) == INVENTORY_COLUMNS

    categories = {r["entity_type"] for r in rows}
    assert {
        "automatic_page", "book", "collection", "revue", "editorial_page",
        "actualite_anchor", "actualite_book_link",
    } <= categories

    by_title = {r["title"]: r for r in rows if r["entity_type"] == "book"}
    assert by_title["Slug deja suffixe"]["explicit_slug"] == "mon-livre-2"
    assert by_title["Slug deja suffixe"]["auto_uniquified"] == "False"
    assert by_title["Second doublon"]["slug_candidate"] == "meme-slug"
    assert by_title["Second doublon"]["final_slug"] == "meme-slug-2"
    assert by_title["Second doublon"]["auto_uniquified"] == "True"
    assert by_title["Fallback ISBN"]["slug_origin"] == "fallback_title_isbn"
    assert by_title["Sans ISBN"]["slug_origin"] == "fallback_title"
    assert any(r["public_path"] == "livres/livre-actu.html" for r in rows)
    assert any(r["public_path"] == "actualites.html#actu-actu-livre" for r in rows)
