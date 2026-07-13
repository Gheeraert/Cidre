import sys
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_site as bs
import cidre.orchestrator as orchestrator
from gui_tk import should_continue_after_validation


def _book(**over):
    row = {
        "slug": "un-livre",
        "id13": "9782877750001",
        "titre_norm": "Un livre",
        "sous_titre_norm": "",
        "credit_ligne": "",
        "collection": "Essais",
        "collection_id": "col-essais",
        "date_parution_norm": "2026-01-01",
        "pub_date": pd.Timestamp("2026-01-01").date(),
        "format_site": "",
        "price": "12",
        "prix_ttc": "",
        "availability": "",
        "availability_label": "",
        "cover_file": "cover.jpg",
        "Description courte": "Resume",
        "Description longue": "",
        "Table des matieres": "",
        "order_url": "",
        "openedition_url": "",
    }
    row.update(over)
    return row


def _report(books, **kwargs):
    return bs.validate_site_data(books=pd.DataFrame(books), **kwargs)


def _codes(report):
    return {i.code for i in report.issues}


def test_donnees_valides_sans_blocage_ni_alerte(tmp_path):
    covers = tmp_path / "covers"
    covers.mkdir()
    (covers / "cover.jpg").write_bytes(b"jpg")
    collections = pd.DataFrame([{"collection_id": "col-essais", "is_active": 1, "slug": "essais"}])
    report = _report([_book()], collections=collections, covers_dir=covers)
    assert not report.has_blocking_issues
    assert not report.has_alerts


def test_titre_absent_alerte_contournable():
    report = _report([_book(titre_norm="")])
    assert "BOOK_TITLE_MISSING" in _codes(report)
    assert report.alerts[0].severity == "alert"


def test_isbn_absent_avertissement():
    report = _report([_book(id13="")])
    assert "BOOK_ID13_MISSING" in _codes(report)
    assert not report.has_alerts


def test_resume_absent_avertissement():
    report = _report([_book(**{"Description courte": "", "Description longue": ""})])
    assert "BOOK_DESCRIPTION_MISSING" in _codes(report)
    assert not report.has_alerts


def test_couverture_absente_ou_introuvable(tmp_path):
    assert "BOOK_COVER_MISSING" in _codes(_report([_book(cover_file="")]))
    covers = tmp_path / "covers"
    covers.mkdir()
    report = _report([_book(cover_file="absente.jpg")], covers_dir=covers)
    assert "BOOK_COVER_NOT_FOUND" in _codes(report)


def test_slug_duplique_alerte():
    report = _report([_book(slug="x"), _book(slug="x", id13="9782877750002")])
    assert "BOOK_SLUG_DUPLICATE" in _codes(report)
    assert report.has_alerts


def test_isbn_duplique_alerte():
    report = _report([_book(slug="a"), _book(slug="b")])
    assert "BOOK_ID13_DUPLICATE" in _codes(report)
    assert report.has_alerts


def test_collection_inconnue_alerte():
    collections = pd.DataFrame([{"collection_id": "col-connue", "is_active": 1, "slug": "connue"}])
    report = _report([_book(collection_id="col-inconnue")], collections=collections)
    assert "BOOK_COLLECTION_UNKNOWN" in _codes(report)


def test_revue_inconnue_alerte():
    revues = pd.DataFrame([{"journal_id": "rev-connue", "is_active": 1, "slug": "connue"}])
    report = _report([
        _book(collection="Revue inconnue", collection_id="rev-inconnue", titre_norm="Revue inconnue n° 1")
    ], revues=revues)
    assert "BOOK_REVUE_UNKNOWN" in _codes(report)


def test_date_invalide_avertissement():
    report = _report([_book(date_parution_norm="pas-une-date")])
    assert "BOOK_DATE_INVALID" in _codes(report)


def test_url_invalide_avertissement():
    report = _report([_book(order_url="javascript:alert(1)")])
    assert "BOOK_URL_INVALID" in _codes(report)


def test_generation_autorisee_avec_seulement_avertissements(tmp_path):
    wb = _workbook(tmp_path / "warn.xlsx", title="Un livre", id13="")
    out = tmp_path / "dist"
    bs.build_site(wb, out, covers_dir=None, force_alerts=False)
    assert (out / "index.html").exists()
    csv = (out / "validation.csv").read_text(encoding="utf-8")
    assert "BOOK_ID13_MISSING" in csv


def test_cli_refuse_alerte_sans_force(tmp_path, monkeypatch):
    wb = _workbook(tmp_path / "alert.xlsx", title="")
    out = tmp_path / "dist"
    monkeypatch.setattr(sys, "argv", ["build_site.py", "--excel", str(wb), "--out", str(out)])
    with pytest.raises(SystemExit) as exc:
        bs.main()
    assert exc.value.code == 4
    assert (out / "validation.csv").exists()
    assert not (out / "index.html").exists()


def test_cli_out_fichier_existant_blocage_sans_modifier(tmp_path, monkeypatch, capsys):
    wb = _workbook(tmp_path / "ok.xlsx")
    out = tmp_path / "dist.html"
    out.write_text("ancien", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["build_site.py", "--excel", str(wb), "--out", str(out)])
    with pytest.raises(SystemExit) as exc:
        bs.main()
    assert exc.value.code == 3
    assert out.read_text(encoding="utf-8") == "ancien"
    err = capsys.readouterr().err
    assert "OUTPUT_PATH_NOT_DIRECTORY" in err
    assert "Traceback" not in err


def test_cli_autorise_alerte_avec_force(tmp_path, monkeypatch):
    wb = _workbook(tmp_path / "alert-force.xlsx", title="")
    out = tmp_path / "dist"
    monkeypatch.setattr(sys, "argv", [
        "build_site.py", "--excel", str(wb), "--out", str(out), "--force"
    ])
    bs.main()
    assert (out / "index.html").exists()
    assert "BOOK_TITLE_MISSING" in (out / "validation.csv").read_text(encoding="utf-8")


def test_blocage_technique_empeche_ecriture_ancien_out(tmp_path):
    wb = _workbook(tmp_path / "ok.xlsx")
    out = tmp_path / "dist"
    out.write_text("ancien", encoding="utf-8")
    with pytest.raises(bs.ValidationBlockingError):
        bs.build_site(wb, out, covers_dir=None)
    assert out.read_text(encoding="utf-8") == "ancien"


def test_pas_de_ftp_en_cas_alerte_cli(tmp_path, monkeypatch):
    wb = _workbook(tmp_path / "ftp-alert.xlsx", title="", ftp=True)
    out = tmp_path / "dist"
    calls = []
    monkeypatch.setattr(orchestrator, "publish_ftp", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(sys, "argv", [
        "build_site.py", "--excel", str(wb), "--out", str(out), "--publish-ftp"
    ])
    with pytest.raises(SystemExit) as exc:
        bs.main()
    assert exc.value.code == 4
    assert calls == []


def test_validate_only_meme_moteur_sans_html(tmp_path, monkeypatch):
    wb = _workbook(tmp_path / "validate-only.xlsx", title="")
    out = tmp_path / "dist"
    monkeypatch.setattr(sys, "argv", [
        "build_site.py", "--excel", str(wb), "--out", str(out), "--validate-only", "--force"
    ])
    bs.main()
    assert "BOOK_TITLE_MISSING" in (out / "validation.csv").read_text(encoding="utf-8")
    assert (out / "assets" / "catalogue.json").exists()
    assert not (out / "index.html").exists()


def test_slug_duplique_depuis_classeur_apres_unicisation(tmp_path, monkeypatch):
    wb = _workbook(
        tmp_path / "dup-slug.xlsx",
        book_rows=[
            {"slug": "meme-slug", "id13": "9782877750001", "titre_norm": "Livre A"},
            {"slug": "meme-slug", "id13": "9782877750002", "titre_norm": "Livre B"},
        ],
    )
    out = tmp_path / "dist"
    monkeypatch.setattr(sys, "argv", ["build_site.py", "--excel", str(wb), "--out", str(out)])
    with pytest.raises(SystemExit) as exc:
        bs.main()
    assert exc.value.code == 4
    csv = (out / "validation.csv").read_text(encoding="utf-8")
    assert "BOOK_SLUG_DUPLICATE" in csv
    assert "DUPLICATE_OUTPUT_TARGET" not in csv


def test_pages_meme_slug_et_identifiant_collision_blocage():
    pages = pd.DataFrame([
        {"slug": "doublon", "title": "Doublon"},
        {"slug": "doublon", "title": "Doublon"},
    ])
    report = bs.validate_site_data(books=pd.DataFrame(), pages=pages)
    assert "DUPLICATE_OUTPUT_TARGET" in _codes(report)
    issue = [i for i in report.blocking_issues if i.code == "DUPLICATE_OUTPUT_TARGET"][0]
    assert "page:doublon" in issue.message


def test_collections_meme_slug_et_identifiant_collision_blocage():
    collections = pd.DataFrame([
        {"collection_id": "col", "slug": "index", "is_active": 1},
        {"collection_id": "col", "slug": "index", "is_active": 1},
    ])
    report = bs.validate_site_data(books=pd.DataFrame(), collections=collections)
    assert "DUPLICATE_OUTPUT_TARGET" in _codes(report)
    assert any("collections/index.html" in i.message for i in report.blocking_issues)


def test_revues_meme_slug_et_identifiant_collision_blocage():
    revues = pd.DataFrame([
        {"journal_id": "rev", "slug": "index", "title": "Revue", "is_active": 1},
        {"journal_id": "rev", "slug": "index", "title": "Revue", "is_active": 1},
    ])
    report = bs.validate_site_data(books=pd.DataFrame(), revues=revues)
    assert "DUPLICATE_OUTPUT_TARGET" in _codes(report)
    assert any("revues/index.html" in i.message for i in report.blocking_issues)


def test_page_collision_avec_page_automatique_blocage():
    pages = pd.DataFrame([{"slug": "catalogue", "title": "Catalogue manuel"}])
    report = bs.validate_site_data(books=pd.DataFrame(), pages=pages)
    assert "DUPLICATE_OUTPUT_TARGET" in _codes(report)
    assert any("catalogue.html" in i.message for i in report.blocking_issues)


def test_page_pilotee_par_pages_autorisee_si_producteur_unique():
    pages = pd.DataFrame([
        {"slug": "presentation", "title": "Presentation"},
        {"slug": "commander", "title": "Commander"},
        {"slug": "open-access", "title": "Open Access"},
    ])
    report = bs.validate_site_data(books=pd.DataFrame(), pages=pages)
    assert not report.has_blocking_issues


def test_csv_colonnes_attendues(tmp_path):
    report = _report([_book(id13="")])
    p = tmp_path / "validation.csv"
    bs.write_validation_csv(report, p)
    header = p.read_text(encoding="utf-8").splitlines()[0]
    assert header == "level,code,entity,identifier,field,message"


def test_imports_historiques_depuis_build_site():
    assert bs.build_validation_report
    assert bs.ValidationIssue
    assert bs.ValidationReport
    assert bs.validate_site_data


def test_decision_gui_pure():
    report = _report([_book(titre_norm="")])
    assert should_continue_after_validation(report, lambda r: True) is True
    assert should_continue_after_validation(report, lambda r: False) is False
    blocking = bs.ValidationReport([
        bs.ValidationIssue("blocking", "X", "site", "id", "field", "msg")
    ])
    assert should_continue_after_validation(blocking, lambda r: True) is False


def _workbook(path: Path, title: str = "Un livre", id13: str = "9782877750001",
              ftp: bool = False, book_rows: list[dict] | None = None) -> Path:
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
    if ftp:
        for key, value in [
            ("ftp_host", "ftp.example.test"),
            ("ftp_user", "user"),
            ("ftp_password", "secret"),
            ("ftp_remote_dir", "/www"),
        ]:
            ws.append([key, value])

    books = wb.create_sheet("CATALOGUE")
    books.append([
        "id13", "slug", "titre_norm", "sous_titre_norm", "credit_ligne",
        "collection", "collection_id", "date_parution_norm", "format_site",
        "price", "availability", "cover_file", "Description courte",
        "Description longue", "order_url", "openedition_url", "active_site",
    ])
    if book_rows is None:
        book_rows = [{"id13": id13, "slug": "un-livre", "titre_norm": title}]
    for row in book_rows:
        books.append([
            row.get("id13", id13),
            row.get("slug", "un-livre"),
            row.get("titre_norm", title),
            row.get("sous_titre_norm", ""),
            row.get("credit_ligne", ""),
            row.get("collection", "Essais"),
            row.get("collection_id", "col-essais"),
            row.get("date_parution_norm", "2026-01-01"),
            row.get("format_site", "Broche"),
            row.get("price", "12"),
            row.get("availability", "Disponible"),
            row.get("cover_file", ""),
            row.get("Description courte", "Resume"),
            row.get("Description longue", ""),
            row.get("order_url", ""),
            row.get("openedition_url", ""),
            row.get("active_site", 1),
        ])

    pages = wb.create_sheet("PAGES")
    pages.append(["slug", "title", "content_md", "is_published"])
    pages.append(["presentation", "Presentation", "Texte", 1])

    collections = wb.create_sheet("COLLECTIONS")
    collections.append(["collection_id", "name", "slug", "is_active"])
    collections.append(["col-essais", "Essais", "essais", 1])

    revues = wb.create_sheet("REVUES")
    revues.append(["revue_id", "title", "slug", "is_active"])

    contacts = wb.create_sheet("CONTACTS")
    contacts.append(["label", "name", "role", "email", "phone", "address", "order", "is_active"])

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
