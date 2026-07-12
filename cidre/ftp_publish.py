# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
# Module extrait de build_site.py (découpage sans changement fonctionnel).

from __future__ import annotations

import os
from pathlib import Path

from .data_models import SiteConfig
from .utils import as_str

# -------------------------
# FTP publish (optionnel)
# -------------------------

def publish_ftp(cfg: SiteConfig, local_dir: Path, progress_cb=None) -> None:
    """Publie local_dir en FTP/FTPS, en créant les dossiers distants si besoin.
       progress_cb(event: dict) optionnel, appelé pendant le transfert.
    """
    import ftplib
    import time

    def emit(**evt):
        if progress_cb:
            try:
                progress_cb(evt)
            except Exception:
                pass

    host = as_str(cfg.ftp_host)
    user = as_str(cfg.ftp_user)
    password = as_str(cfg.ftp_password)
    remote_dir = as_str(cfg.ftp_remote_dir)
    port = int(cfg.ftp_port or 21)

    if not host or not user or not password or not remote_dir:
        raise ValueError("FTP incomplet : renseigner ftp_host / ftp_user / ftp_password / ftp_remote_dir dans CONFIG.")

    ftp = ftplib.FTP_TLS() if cfg.ftp_tls else ftplib.FTP()
    ftp.connect(host=host, port=port, timeout=30)
    # FTP.login() n'accepte pas d'argument « secure ». En FTPS, login()
    # déclenche AUTH TLS (secure=True par défaut) et prot_p() chiffre le
    # canal de données — même convention que le test de connexion de la GUI.
    ftp.login(user=user, passwd=password)
    if isinstance(ftp, ftplib.FTP_TLS):
        ftp.prot_p()
    ftp.set_pasv(bool(cfg.ftp_passive))

    def cwd_mkdir(path: str) -> None:
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        if path.startswith("/"):
            ftp.cwd("/")
        for p in parts:
            try:
                ftp.cwd(p)
            except Exception:
                ftp.mkd(p)
                ftp.cwd(p)

    # --- Préparer la liste des fichiers à transférer (pour un vrai % global)
    local_dir = local_dir.resolve()
    files = []
    total_bytes = 0

    for root, dirs, fns in os.walk(local_dir):
        root_p = Path(root)
        for fn in fns:
            if fn.lower().endswith(".log"):
                continue
            lp = root_p / fn
            if not lp.is_file():
                continue
            sz = lp.stat().st_size
            rel_dir = root_p.relative_to(local_dir).as_posix()
            files.append((lp, rel_dir, fn, sz))
            total_bytes += sz

    emit(type="ftp_start", remote_dir=remote_dir, total_files=len(files), total_bytes=total_bytes)

    # --- Aller dans la racine distante une fois
    cwd_mkdir(remote_dir)

    uploaded = 0
    skipped = 0
    errors = 0
    sent_total = 0

    # Throttle UI (évite 10 000 updates/seconde)
    last_emit = 0.0

    def maybe_emit_progress(file_sent, file_size, idx, relpath):
        nonlocal last_emit
        now = time.time()
        if now - last_emit >= 0.08:  # 80ms
            last_emit = now
            emit(
                type="progress",
                i=idx, n=len(files),
                relpath=relpath,
                file_sent=file_sent, file_size=file_size,
                sent_total=sent_total, total_bytes=total_bytes
            )

    for idx, (lp, rel_dir, fn, sz) in enumerate(files, start=1):
        # Se positionner dans le bon sous-dossier distant
        if rel_dir and rel_dir != ".":
            cwd_mkdir(remote_dir.rstrip("/") + "/" + rel_dir)
        else:
            cwd_mkdir(remote_dir)

        relpath = f"{rel_dir}/{fn}" if rel_dir and rel_dir != "." else fn
        emit(type="file_start", i=idx, n=len(files), relpath=relpath, file_size=sz)

        # Skip si même taille distante (si SIZE disponible)
        try:
            rsize = ftp.size(fn)
            if rsize is not None and int(rsize) == sz:
                skipped += 1
                # on retire ce poids du total pour garder un % global exact
                total_bytes -= sz
                emit(type="file_skip", i=idx, n=len(files), relpath=relpath, file_size=sz,
                     sent_total=sent_total, total_bytes=total_bytes)
                continue
        except Exception:
            pass

        file_sent = 0

        def cb(block: bytes):
            nonlocal file_sent, sent_total
            nbytes = len(block)
            file_sent += nbytes
            sent_total += nbytes
            maybe_emit_progress(file_sent, sz, idx, relpath)

        try:
            with open(lp, "rb") as f:
                ftp.storbinary(f"STOR {fn}", f, blocksize=64 * 1024, callback=cb)
            uploaded += 1
            emit(type="file_done", i=idx, n=len(files), relpath=relpath, file_size=sz,
                 sent_total=sent_total, total_bytes=total_bytes)
        except Exception as e:
            errors += 1
            emit(type="file_error", i=idx, n=len(files), relpath=relpath, error=str(e))

        # Revenir proprement à la racine distante (évite surprises)
        cwd_mkdir(remote_dir)

    emit(type="ftp_done", remote_dir=remote_dir, uploaded=uploaded, skipped=skipped, errors=errors,
         sent_total=sent_total, total_bytes=total_bytes)

    print(f"FTP -> {remote_dir} : {uploaded} envoyé(s), {skipped} ignoré(s), {errors} erreur(s).")

    try:
        ftp.quit()
    except Exception:
        ftp.close()


