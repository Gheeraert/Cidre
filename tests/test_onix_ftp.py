# Tests des deux corrections de la micropasse :
# - export ONIX en CLI : import du module réellement présent (export_onix_py),
#   appel avec les arguments attendus, pas de ModuleNotFoundError ;
# - publish_ftp : login() sans argument « secure » en FTP simple ; en FTPS,
#   login() (AUTH TLS par défaut) puis prot_p(), comme le test de connexion
#   de la GUI. Aucune connexion réseau réelle : faux objets ftplib.
#
# Lancement : .venv\Scripts\python.exe -m pytest tests/ -v

import ftplib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import build_site
import export_onix_py

GABARIT = Path(__file__).resolve().parents[1] / "gabarit" / "purh_site_excel_gabarit.xlsx"


# ----------------------------------------------------------------------
# Export ONIX en ligne de commande
# ----------------------------------------------------------------------

def test_export_onix_cli(tmp_path, monkeypatch):
    """Le chemin --export-onix importe export_onix_py et l'appelle correctement."""
    calls = []

    def spy(**kwargs):
        calls.append(kwargs)
        Path(kwargs["out_xml_path"]).write_text("<ONIXMessage/>", encoding="utf-8")
        return kwargs["out_xml_path"], []

    monkeypatch.setattr(export_onix_py, "export_onix_from_excel", spy)
    out = tmp_path / "dist"
    monkeypatch.setattr(sys, "argv", [
        "build_site.py", "--excel", str(GABARIT), "--out", str(out), "--export-onix",
    ])
    build_site.main()  # ne doit lever ni ModuleNotFoundError ni autre exception

    assert len(calls) == 1
    kw = calls[0]
    assert kw["excel_path"] == str(GABARIT.resolve())
    assert kw["out_xml_path"] == str(out / "onix" / "purh_onix.xml")
    assert kw["report_csv_path"] == str(out / "onix" / "purh_onix_QA.csv")
    assert kw["strict"] is False


def test_export_onix_reel_sur_gabarit(tmp_path):
    """La vraie fonction d'export produit un XML ONIX depuis le gabarit."""
    out_xml = tmp_path / "onix.xml"
    report = tmp_path / "qa.csv"
    export_onix_py.export_onix_from_excel(
        excel_path=str(GABARIT),
        out_xml_path=str(out_xml),
        strict=False,
        report_csv_path=str(report),
    )
    assert out_xml.exists()
    assert "ONIXMessage" in out_xml.read_text(encoding="utf-8")[:2000]


# ----------------------------------------------------------------------
# Création des dossiers parents du XML et du rapport QA (--onix-out /
# --onix-report) : matrice A-F. Le faux exporteur écrit réellement les
# deux fichiers, donc échoue comme le vrai (pandas to_csv) si un dossier
# parent manque.
# ----------------------------------------------------------------------

def _run_cli_onix(tmp_path, monkeypatch, extra_args):
    calls = []

    def spy(**kwargs):
        calls.append(kwargs)
        Path(kwargs["out_xml_path"]).write_text("<ONIXMessage/>", encoding="utf-8")
        Path(kwargs["report_csv_path"]).write_text(
            "row_index,isbn13,title,issue\n", encoding="utf-8")
        return kwargs["out_xml_path"], []

    monkeypatch.setattr(export_onix_py, "export_onix_from_excel", spy)
    out = tmp_path / "dist"
    monkeypatch.setattr(sys, "argv", [
        "build_site.py", "--excel", str(GABARIT), "--out", str(out), *extra_args,
    ])
    build_site.main()
    return out, calls


def test_onix_dossiers_cas_a_chemins_par_defaut(tmp_path, monkeypatch):
    """Cas A : XML et rapport QA créés à leurs emplacements par défaut."""
    out, calls = _run_cli_onix(tmp_path, monkeypatch, ["--export-onix"])
    assert len(calls) == 1
    assert (out / "onix" / "purh_onix.xml").exists()
    assert (out / "onix" / "purh_onix_QA.csv").exists()


def test_onix_dossiers_cas_b_onix_out_personnalise(tmp_path, monkeypatch):
    """Cas B (bug reproduit) : --onix-out seul ; le dossier par défaut du
    rapport QA doit aussi être créé."""
    xml = tmp_path / "custom" / "export.xml"
    out, calls = _run_cli_onix(
        tmp_path, monkeypatch, ["--export-onix", "--onix-out", str(xml)])
    assert len(calls) == 1
    assert xml.exists()
    assert (out / "onix").is_dir()
    assert (out / "onix" / "purh_onix_QA.csv").exists()


def test_onix_dossiers_cas_c_onix_report_personnalise(tmp_path, monkeypatch):
    """Cas C : --onix-report seul ; son dossier est créé, XML par défaut."""
    report = tmp_path / "rapports" / "rapport.csv"
    out, calls = _run_cli_onix(
        tmp_path, monkeypatch, ["--export-onix", "--onix-report", str(report)])
    assert len(calls) == 1
    assert report.exists()
    assert (out / "onix" / "purh_onix.xml").exists()


def test_onix_dossiers_cas_d_deux_chemins_personnalises(tmp_path, monkeypatch):
    """Cas D : deux chemins personnalisés, les deux arborescences créées."""
    xml = tmp_path / "dossier-a" / "export.xml"
    report = tmp_path / "dossier-b" / "rapport.csv"
    out, calls = _run_cli_onix(tmp_path, monkeypatch, [
        "--export-onix", "--onix-out", str(xml), "--onix-report", str(report)])
    assert len(calls) == 1
    assert xml.exists()
    assert report.exists()


def test_onix_dossiers_cas_e_niveaux_imbriques(tmp_path, monkeypatch):
    """Cas E : plusieurs niveaux inexistants (parents=True)."""
    xml = tmp_path / "a" / "b" / "c" / "export.xml"
    report = tmp_path / "x" / "y" / "z" / "rapport.csv"
    out, calls = _run_cli_onix(tmp_path, monkeypatch, [
        "--export-onix", "--onix-out", str(xml), "--onix-report", str(report)])
    assert len(calls) == 1
    assert xml.exists()
    assert report.exists()


def test_onix_dossiers_cas_f_sans_export_onix(tmp_path, monkeypatch):
    """Cas F : sans --export-onix, aucun dossier onix créé, exporteur non appelé."""
    out, calls = _run_cli_onix(tmp_path, monkeypatch, [])
    assert calls == []
    assert not (out / "onix").exists()


# ----------------------------------------------------------------------
# publish_ftp : faux objets ftplib, aucune connexion réelle
# ----------------------------------------------------------------------

class FakeFTP:
    """Simule ftplib.FTP en journalisant les appels ; login() reproduit la
    vraie signature (pas d'argument « secure »)."""

    def __init__(self, *a, **kw):
        self.calls = []
        FakeFTP.last = self

    def connect(self, host="", port=0, timeout=None):
        self.calls.append(("connect", host, port))

    def login(self, user="", passwd="", acct=""):
        self.calls.append(("login", user, passwd))

    def set_pasv(self, val):
        self.calls.append(("set_pasv", bool(val)))

    def cwd(self, path):
        self.calls.append(("cwd", path))

    def mkd(self, path):
        self.calls.append(("mkd", path))

    def size(self, fn):
        raise ftplib.error_perm("550 SIZE non disponible")

    def storbinary(self, cmd, fp, blocksize=8192, callback=None):
        data = fp.read()
        if callback:
            callback(data)
        self.calls.append(("storbinary", cmd, len(data)))

    def quit(self):
        self.calls.append(("quit",))

    def close(self):
        self.calls.append(("close",))


class FakeFTPTLS(FakeFTP):
    """Simule ftplib.FTP_TLS : login(secure=True) par défaut + prot_p()."""

    def login(self, user="", passwd="", acct="", secure=True):
        self.calls.append(("login", user, passwd, secure))

    def prot_p(self):
        self.calls.append(("prot_p",))


def make_cfg(tls: bool) -> "build_site.SiteConfig":
    cfg = build_site.SiteConfig()
    cfg.ftp_host = "ftp.exemple.fr"
    cfg.ftp_user = "utilisatrice"
    cfg.ftp_password = "s3cret"
    cfg.ftp_remote_dir = "/www"
    cfg.ftp_tls = tls
    return cfg


@pytest.fixture
def site_local(tmp_path) -> Path:
    d = tmp_path / "dist"
    d.mkdir()
    (d / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return d


def _fake_ftplib(monkeypatch):
    # publish_ftp choisit la classe via isinstance : FakeFTPTLS doit passer
    # pour ftplib.FTP_TLS afin d'exercer la branche prot_p()
    monkeypatch.setattr(ftplib, "FTP", FakeFTP)
    monkeypatch.setattr(ftplib, "FTP_TLS", FakeFTPTLS)


def test_ftp_simple_login_sans_argument_secure(monkeypatch, site_local, capsys):
    _fake_ftplib(monkeypatch)
    build_site.publish_ftp(make_cfg(tls=False), site_local)
    ftp = FakeFTP.last
    assert type(ftp) is FakeFTP  # FTP simple, pas TLS
    assert ("login", "utilisatrice", "s3cret") in ftp.calls  # 3 champs : pas de « secure »
    assert ("prot_p",) not in ftp.calls
    assert any(c[0] == "storbinary" for c in ftp.calls)  # la publication a bien eu lieu
    assert ("quit",) in ftp.calls


def test_ftps_login_auth_tls_puis_prot_p(monkeypatch, site_local, capsys):
    _fake_ftplib(monkeypatch)
    build_site.publish_ftp(make_cfg(tls=True), site_local)
    ftp = FakeFTP.last
    assert type(ftp) is FakeFTPTLS
    # login() sans secure=False : AUTH TLS par défaut, comme la GUI
    assert ("login", "utilisatrice", "s3cret", True) in ftp.calls
    # prot_p() appelé après login, avant le premier transfert
    assert ftp.calls.index(("prot_p",)) > ftp.calls.index(("login", "utilisatrice", "s3cret", True))
    assert any(c[0] == "storbinary" for c in ftp.calls)


def test_publication_et_test_gui_meme_convention(monkeypatch, site_local):
    """La publication utilise la même convention que _ftp_try_connect de la GUI :
    FTP simple -> login(user, passwd) ; FTPS -> login() par défaut + prot_p()."""
    _fake_ftplib(monkeypatch)
    build_site.publish_ftp(make_cfg(tls=False), site_local)
    plain_login = [c for c in FakeFTP.last.calls if c[0] == "login"][0]
    build_site.publish_ftp(make_cfg(tls=True), site_local)
    tls_calls = FakeFTP.last.calls
    assert plain_login == ("login", "utilisatrice", "s3cret")
    assert ("prot_p",) in tls_calls
