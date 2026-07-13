# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
"""Remplacement transactionnel du dossier de sortie local."""

from __future__ import annotations

import uuid
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import shutil


class OutputTransactionError(RuntimeError):
    """Erreur explicite lors du basculement transactionnel."""


class OutputBackupCleanupWarning(RuntimeWarning):
    """La sauvegarde temporaire n'a pas pu être supprimée après succès."""


class OutputCleanupError(RuntimeError):
    """Le nettoyage a échoué après une erreur initiale."""


def _unique_neighbor(out_dir: Path, kind: str) -> Path:
    parent = out_dir.parent
    stem = out_dir.name
    for _ in range(100):
        candidate = parent / f".{stem}.{kind}-{uuid.uuid4().hex}"
        if not candidate.exists():
            return candidate
    raise OutputTransactionError(f"Impossible de créer un nom temporaire unique près de {out_dir}.")


def _rename_path(src: Path, dst: Path) -> None:
    src.rename(dst)


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path)


def _install_staging(staging_dir: Path, out_dir: Path) -> None:
    _rename_path(staging_dir, out_dir)


@dataclass
class StagedOutput:
    out_dir: Path
    staging_dir: Path
    backup_dir: Path | None = None
    committed: bool = False

    def commit(self) -> None:
        if self.committed:
            return

        if self.out_dir.exists():
            self.backup_dir = _unique_neighbor(self.out_dir, "backup")
            _rename_path(self.out_dir, self.backup_dir)
            try:
                _install_staging(self.staging_dir, self.out_dir)
            except Exception as exc:
                try:
                    if self.out_dir.exists():
                        _remove_tree(self.out_dir)
                    _rename_path(self.backup_dir, self.out_dir)
                except Exception as restore_exc:
                    raise OutputTransactionError(
                        "Le remplacement du dossier de sortie a échoué et la restauration "
                        f"automatique a échoué aussi. Sauvegarde : {self.backup_dir}. "
                        f"Dossier attendu : {self.out_dir}. Intervention manuelle possible."
                    ) from restore_exc
                try:
                    if self.staging_dir.exists():
                        _remove_tree(self.staging_dir)
                except Exception:
                    pass
                raise exc

            self.committed = True
            try:
                _remove_tree(self.backup_dir)
            except Exception as cleanup_exc:
                warnings.warn(
                    f"Le nouveau site est en place, mais la sauvegarde temporaire "
                    f"n'a pas pu être supprimée : {self.backup_dir} ({cleanup_exc})",
                    OutputBackupCleanupWarning,
                    stacklevel=2,
                )
        else:
            try:
                _install_staging(self.staging_dir, self.out_dir)
            except Exception:
                try:
                    if self.staging_dir.exists():
                        _remove_tree(self.staging_dir)
                except Exception:
                    pass
                raise
            self.committed = True

    def cleanup(self) -> None:
        if not self.committed and self.staging_dir.exists():
            _remove_tree(self.staging_dir)

    def cleanup_after_error(self, initial_exc: BaseException) -> None:
        try:
            self.cleanup()
        except Exception as cleanup_exc:
            raise OutputCleanupError(
                "Une erreur est survenue pendant la génération, puis le nettoyage "
                f"du staging a échoué. Erreur initiale : {initial_exc!r}. "
                f"Staging résiduel : {self.staging_dir}. Nettoyage manuel possible."
            ) from cleanup_exc


@contextmanager
def staged_output(out_dir: Path) -> Iterator[StagedOutput]:
    out_dir = Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = _unique_neighbor(out_dir, "build")
    try:
        if out_dir.exists():
            if not out_dir.is_dir():
                raise OutputTransactionError(f"Le chemin de sortie existe mais n'est pas un dossier : {out_dir}")
            shutil.copytree(out_dir, staging)
        else:
            staging.mkdir(parents=True)
    except Exception:
        if staging.exists():
            try:
                _remove_tree(staging)
            except Exception:
                pass
        raise

    tx = StagedOutput(out_dir=out_dir, staging_dir=staging)
    try:
        yield tx
    except Exception as exc:
        tx.cleanup_after_error(exc)
        raise
    else:
        if not tx.committed:
            tx.cleanup()
