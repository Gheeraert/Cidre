from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROFILE_SCHEMA_VERSION = 1
PROFILE_PATH_FIELDS = ("excel_path", "output_dir", "covers_dir", "assets_dir")


class GenerationProfileError(ValueError):
    """Profil de generation invalide ou illisible."""


@dataclass(frozen=True)
class GenerationProfile:
    excel_path: str = ""
    output_dir: str = ""
    covers_dir: str = ""
    assets_dir: str = ""
    schema_version: int = PROFILE_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "excel_path": self.excel_path,
            "output_dir": self.output_dir,
            "covers_dir": self.covers_dir,
            "assets_dir": self.assets_dir,
        }


def _path_value(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise GenerationProfileError(
            f"La valeur du champ {key} doit etre une chaine de caracteres ou null."
        )
    return value


def profile_from_mapping(data: Any) -> GenerationProfile:
    if not isinstance(data, dict):
        raise GenerationProfileError("Le profil de generation doit etre un objet JSON.")

    version = data.get("schema_version")
    if version is None:
        raise GenerationProfileError("Version du profil de generation absente.")
    if version != PROFILE_SCHEMA_VERSION:
        raise GenerationProfileError(
            f"Version du profil de generation non prise en charge : {version}."
        )

    return GenerationProfile(
        schema_version=PROFILE_SCHEMA_VERSION,
        excel_path=_path_value(data, "excel_path"),
        output_dir=_path_value(data, "output_dir"),
        covers_dir=_path_value(data, "covers_dir"),
        assets_dir=_path_value(data, "assets_dir"),
    )


def load_generation_profile(path: Path) -> GenerationProfile:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise GenerationProfileError(f"Profil de generation illisible : {path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GenerationProfileError(f"JSON invalide dans le profil de generation : {exc}") from exc
    return profile_from_mapping(data)


def save_generation_profile(path: Path, profile: GenerationProfile) -> None:
    data = profile.to_json_dict() if isinstance(profile, GenerationProfile) else asdict(profile)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
