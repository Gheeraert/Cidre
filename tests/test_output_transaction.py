import sys
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_site as bs
import cidre.orchestrator as orchestrator
import cidre.output_transaction as output_transaction


def _workbook(path: Path, title: str = "Un livre") -> Path:
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
    books.append([
        "id13", "slug", "titre_norm", "sous_titre_norm", "credit_ligne",
        "collection", "collection_id", "date_parution_norm", "format_site",
        "price", "availability", "cover_file", "Description courte",
        "Description longue", "order_url", "openedition_url", "active_site",
    ])
    books.append([
        "9782877750001", "un-livre", title, "", "", "Essais", "col-essais",
        "2026-01-01", "Broche", "12", "Disponible", "", "Resume", "",
        "", "", 1,
    ])

    pages = wb.create_sheet("PAGES")
    pages.append(["slug", "title", "content_md", "is_published"])
    pages.append(["presentation", "Presentation", "Texte neuf", 1])

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


def _leftovers(out: Path) -> list[Path]:
    return sorted(out.parent.glob(f".{out.name}.build-*")) + sorted(out.parent.glob(f".{out.name}.backup-*"))


def _snapshot(path: Path) -> dict[str, bytes]:
    return {
        p.relative_to(path).as_posix(): p.read_bytes()
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def _prepare_old_dist(out: Path) -> dict[str, bytes]:
    (out / "livres").mkdir(parents=True)
    (out / "assets").mkdir()
    (out / "covers").mkdir()
    (out / "onix").mkdir()
    (out / "livres" / "orpheline.html").write_text("ancienne page", encoding="utf-8")
    (out / "index.html").write_text("ancien index", encoding="utf-8")
    (out / "manuel.txt").write_text("manuel", encoding="utf-8")
    (out / "assets" / "manuel-asset.txt").write_text("asset manuel", encoding="utf-8")
    (out / "covers" / "cover.jpg").write_bytes(b"cover")
    (out / "onix" / "temoin.xml").write_text("<ONIX/>", encoding="utf-8")
    return _snapshot(out)


def test_transaction_reussie_sans_ancien_dossier(tmp_path):
    wb = _workbook(tmp_path / "site.xlsx")
    out = tmp_path / "dist"

    report = bs.build_site(wb, out, covers_dir=None)

    assert out.exists()
    assert (out / "index.html").exists()
    assert (out / "validation.csv").exists()
    assert report is not None
    assert _leftovers(out) == []


def test_transaction_reussie_conserve_fichiers_non_geres(tmp_path):
    wb = _workbook(tmp_path / "site.xlsx")
    out = tmp_path / "dist"
    _prepare_old_dist(out)

    bs.build_site(wb, out, covers_dir=None)

    assert (out / "index.html").read_text(encoding="utf-8") != "ancien index"
    assert not (out / "livres" / "orpheline.html").exists()
    assert (out / "manuel.txt").read_text(encoding="utf-8") == "manuel"
    assert (out / "assets" / "manuel-asset.txt").read_text(encoding="utf-8") == "asset manuel"
    assert (out / "covers" / "cover.jpg").read_bytes() == b"cover"
    assert (out / "onix" / "temoin.xml").read_text(encoding="utf-8") == "<ONIX/>"
    assert _leftovers(out) == []


def test_echec_generation_garde_ancien_dist_intact_et_pas_de_ftp(tmp_path, monkeypatch):
    wb = _workbook(tmp_path / "site.xlsx")
    out = tmp_path / "dist"
    before = _prepare_old_dist(out)
    ftp_calls = []

    def fail_catalogue(*args, **kwargs):
        raise RuntimeError("boom-generation")

    monkeypatch.setattr(orchestrator, "build_catalogue_page", fail_catalogue)
    monkeypatch.setattr(orchestrator, "publish_ftp", lambda *a, **k: ftp_calls.append((a, k)))

    with pytest.raises(RuntimeError, match="boom-generation"):
        bs.build_site(wb, out, covers_dir=None, publish=True)

    assert _snapshot(out) == before
    assert _leftovers(out) == []
    assert ftp_calls == []


def test_echec_basculement_restaure_ancien_dist(tmp_path, monkeypatch):
    wb = _workbook(tmp_path / "site.xlsx")
    out = tmp_path / "dist"
    before = _prepare_old_dist(out)
    original_rename = output_transaction._rename_path

    def flaky_rename(src: Path, dst: Path) -> None:
        if ".build-" in src.name and dst == out:
            raise RuntimeError("boom-rename")
        original_rename(src, dst)

    monkeypatch.setattr(output_transaction, "_rename_path", flaky_rename)

    with pytest.raises(RuntimeError, match="boom-rename"):
        bs.build_site(wb, out, covers_dir=None)

    assert _snapshot(out) == before
    assert _leftovers(out) == []


def test_echec_nettoyage_backup_signale_et_garde_nouveau_site(tmp_path, monkeypatch, recwarn):
    wb = _workbook(tmp_path / "site.xlsx")
    out = tmp_path / "dist"
    _prepare_old_dist(out)
    original_remove = output_transaction._remove_tree

    def flaky_remove(path: Path) -> None:
        if ".backup-" in path.name:
            raise RuntimeError("boom-cleanup")
        original_remove(path)

    monkeypatch.setattr(output_transaction, "_remove_tree", flaky_remove)

    bs.build_site(wb, out, covers_dir=None)

    assert (out / "index.html").exists()
    assert "ancien index" not in (out / "index.html").read_text(encoding="utf-8")
    warnings = [w for w in recwarn if issubclass(w.category, output_transaction.OutputBackupCleanupWarning)]
    assert warnings
    backups = sorted(out.parent.glob(f".{out.name}.backup-*"))
    assert len(backups) == 1
    original_remove(backups[0])


def test_validate_only_ne_laisse_pas_de_staging_global(tmp_path):
    wb = _workbook(tmp_path / "site.xlsx", title="")
    out = tmp_path / "dist"

    bs.build_site(wb, out, covers_dir=None, validate_only=True, force_alerts=True)

    assert (out / "validation.csv").exists()
    assert (out / "assets" / "catalogue.json").exists()
    assert not (out / "index.html").exists()
    assert _leftovers(out) == []


def test_alerte_sans_force_ne_remplace_pas_ancien_site(tmp_path):
    wb = _workbook(tmp_path / "site.xlsx", title="")
    out = tmp_path / "dist"
    before = _prepare_old_dist(out)

    with pytest.raises(bs.ValidationAlertError):
        bs.build_site(wb, out, covers_dir=None, force_alerts=False)

    after = _snapshot(out)
    assert after["index.html"] == before["index.html"]
    assert after["livres/orpheline.html"] == before["livres/orpheline.html"]
    assert "validation.csv" in after
    assert _leftovers(out) == []


def test_alerte_avec_force_genere_transactionnellement(tmp_path):
    wb = _workbook(tmp_path / "site.xlsx", title="")
    out = tmp_path / "dist"
    _prepare_old_dist(out)

    report = bs.build_site(wb, out, covers_dir=None, force_alerts=True)

    assert report.has_alerts
    assert (out / "index.html").exists()
    assert not (out / "livres" / "orpheline.html").exists()
    assert _leftovers(out) == []

