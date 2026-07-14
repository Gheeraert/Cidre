import json

import pytest

import gui_tk
from gui_tk import App
from cidre.generation_profile import (
    GenerationProfile,
    GenerationProfileError,
    load_generation_profile,
    save_generation_profile,
)


class _FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_profil_generation_aller_retour(tmp_path):
    profile = GenerationProfile(
        excel_path="C:/PURH/catalogue avec espaces.xlsx",
        output_dir="C:/PURH/site public",
        covers_dir="C:/PURH/couvertures accentuees",
        assets_dir="C:/PURH/assets-source",
    )
    path = tmp_path / "profil.json"

    save_generation_profile(path, profile)
    loaded = load_generation_profile(path)

    assert loaded == profile
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {
        "schema_version": 1,
        "excel_path": "C:/PURH/catalogue avec espaces.xlsx",
        "output_dir": "C:/PURH/site public",
        "covers_dir": "C:/PURH/couvertures accentuees",
        "assets_dir": "C:/PURH/assets-source",
    }


def test_profil_generation_chemins_windows_accents_et_excel_vide(tmp_path):
    path = tmp_path / "profil.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "excel_path": "",
        "output_dir": r"C:\Site PURH\sortie",
        "covers_dir": r"C:\Données PURH\couvertures été",
        "assets_dir": r"C:\Site PURH\assets source",
    }), encoding="utf-8")

    profile = load_generation_profile(path)

    assert profile.excel_path == ""
    assert profile.output_dir == r"C:\Site PURH\sortie"
    assert profile.covers_dir == r"C:\Données PURH\couvertures été"
    assert profile.assets_dir == r"C:\Site PURH\assets source"


def test_profil_generation_partiel_null_et_cles_inconnues(tmp_path):
    path = tmp_path / "profil.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "output_dir": "C:/sortie",
        "covers_dir": None,
        "ftp_password": "ne-doit-pas-etre-relu",
        "future_option": True,
    }), encoding="utf-8")

    profile = load_generation_profile(path)

    assert profile.excel_path == ""
    assert profile.output_dir == "C:/sortie"
    assert profile.covers_dir == ""
    assert profile.assets_dir == ""


@pytest.mark.parametrize("content, message", [
    ("{", "JSON invalide"),
    ("[]", "objet JSON"),
    (json.dumps({"excel_path": "x"}), "Version"),
    (json.dumps({"schema_version": 2}), "non prise en charge"),
    (json.dumps({"schema_version": 1, "output_dir": 42}), "output_dir"),
])
def test_profil_generation_erreurs(tmp_path, content, message):
    path = tmp_path / "profil.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(GenerationProfileError) as exc:
        load_generation_profile(path)

    assert message in str(exc.value)


def test_profil_generation_absence_secrets_ftp(tmp_path):
    profile = GenerationProfile(
        excel_path="C:/catalogue.xlsx",
        output_dir="C:/site",
        covers_dir="C:/covers",
        assets_dir="C:/assets-source",
    )
    path = tmp_path / "profil.json"

    save_generation_profile(path, profile)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert "ftp_password" not in data
    assert "ftp_host" not in data
    assert "ftp_user" not in data
    assert "publish" not in data


def test_gui_charge_profil_remplit_variables_sans_build(tmp_path, monkeypatch):
    path = tmp_path / "profil.json"
    save_generation_profile(path, GenerationProfile(
        excel_path="C:/catalogue.xlsx",
        output_dir="C:/site",
        covers_dir="C:/covers",
        assets_dir="C:/assets-source",
    ))
    app = object.__new__(App)
    app.var_excel = _FakeVar()
    app.var_out = _FakeVar()
    app.var_covers = _FakeVar()
    app.var_assets = _FakeVar()
    refreshed = []
    infos = []
    build_calls = []
    app.refresh_ftp_state = lambda: refreshed.append(True)

    monkeypatch.setattr(gui_tk.filedialog, "askopenfilename", lambda **kwargs: str(path))
    monkeypatch.setattr(gui_tk.messagebox, "showinfo", lambda title, message: infos.append((title, message)))
    monkeypatch.setattr(gui_tk, "build_site", lambda **kwargs: build_calls.append(kwargs))

    app.load_profile()

    assert app.var_excel.get() == "C:/catalogue.xlsx"
    assert app.var_out.get() == "C:/site"
    assert app.var_covers.get() == "C:/covers"
    assert app.var_assets.get() == "C:/assets-source"
    assert refreshed == [True]
    assert infos == [("Profil de génération", "Profil de génération chargé.")]
    assert build_calls == []


def test_gui_enregistre_profil_partiel(tmp_path, monkeypatch):
    path = tmp_path / "profil.json"
    app = object.__new__(App)
    app.var_excel = _FakeVar("")
    app.var_out = _FakeVar("C:/site")
    app.var_covers = _FakeVar("")
    app.var_assets = _FakeVar("C:/assets-source")
    infos = []

    monkeypatch.setattr(gui_tk.filedialog, "asksaveasfilename", lambda **kwargs: str(path))
    monkeypatch.setattr(gui_tk.messagebox, "showinfo", lambda title, message: infos.append((title, message)))

    app.save_profile()

    assert load_generation_profile(path) == GenerationProfile(
        excel_path="",
        output_dir="C:/site",
        covers_dir="",
        assets_dir="C:/assets-source",
    )
    assert infos == [("Profil de génération", "Profil de génération enregistré.")]
