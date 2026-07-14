# Générateur de site statique de maison d'édition scientifique et / ou indépendante
# © 2025 Tony Gheeraert - Licence MIT (voir LICENSE)
# Crédits : PURH + Chaire d'excellence édition numérique de l'université de Rouen
# Fichier de lancement
#
# gui_tk.py
import threading, queue
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
from local_server import PreviewServer
import pandas as pd
from ftplib import FTP, FTP_TLS, error_perm
from cidre.routes import book_public_path
from cidre.utils import as_str
from cidre.orchestrator import (
    AssetSourceError,
    ignored_reserved_asset_json,
    validate_assets_source,
)
from cidre.generation_profile import (
    GenerationProfile,
    GenerationProfileError,
    load_generation_profile,
    save_generation_profile,
)
from cidre.published_slugs import (
    PUBLISHED_SLUG_ALERT_CODES,
    SlugChange,
    compare_published_book_slugs,
    published_slug_issues,
    slug_correction_text,
)

# build_site.py doit être dans le même dossier et contenir build_site(...) + load_config(...)
from build_site import (
    build_site, load_config, publish_ftp, detect_books_sheet,
    load_books, load_pages, load_collections, load_revues, load_contacts,
    load_actualites, format_validation_summary, validate_site_data,
    write_validation_csv,
)
from export_onix_py import export_onix_from_excel

DEFAULT_ASSETS_VALUE = ""

ASSETS_HELP_TEXT = """Ce dossier est facultatif.

Son contenu sera copié dans le dossier « assets » du site.

Placez directement à sa racine les logos et les sous-dossiers utiles, par exemple :

logo_purh.jpg
logo_univ.png
docs/
images/
actu/
social/

Ne placez pas ces fichiers dans un second dossier nommé « assets » :
le dossier sélectionné représente déjà le contenu futur de « assets ».

Les couvertures de livres restent dans le dossier des couvertures, sélectionné séparément.

Les fichiers catalogue.json et actualites.json sont générés automatiquement par CIDRE à la racine du site et ne doivent pas être placés dans ce dossier."""


def resolve_assets_dir_for_gui(assets_value: str, out_dir: Path) -> Path | None:
    assets_value = as_str(assets_value).strip()
    if not assets_value:
        return None
    return validate_assets_source(Path(assets_value).expanduser(), out_dir)


def should_continue_after_validation(report, confirm_alerts) -> bool:
    """Decision pure pour la GUI : blocages = stop, alertes = confirmation."""
    if report.has_blocking_issues:
        return False
    if report.has_alerts:
        return bool(confirm_alerts(report))
    return True


def find_book_url_collisions(books):
    """Retourne les groupes de livres actifs qui produisent la meme URL publique."""
    if books is None or books.empty or "slug" not in books.columns:
        return []

    groups = {}
    for idx, row in books.iterrows():
        slug = as_str(row.get("slug"))
        if not slug:
            continue
        public_path = book_public_path(slug)
        groups.setdefault(public_path, []).append((idx, row))

    collisions = []
    for public_path, items in groups.items():
        if len(items) >= 2:
            collisions.append({"public_path": public_path, "items": items})
    return sorted(collisions, key=lambda c: c["public_path"])


def _format_book_collision_item(idx, row) -> str:
    line_no = idx + 2
    title = as_str(row.get("titre_norm") or row.get("Titre")) or "(titre absent)"
    id13 = as_str(row.get("id13"))
    source_slug = as_str(row.get("_source_slug_raw"))
    if not source_slug:
        source_slug = as_str(row.get("_source_slug"))
    slug_label = source_slug if source_slug else "(vide — URL calculée automatiquement)"
    isbn_part = f" - ISBN {id13}" if id13 else ""
    return f"- ligne {line_no} - {title}{isbn_part}\n  slug Excel : {slug_label}"


def _format_book_collisions(collisions, limit=None) -> str:
    selected = collisions if limit is None else collisions[:limit]
    parts = []
    for collision in selected:
        lines = [collision["public_path"]]
        lines.extend(_format_book_collision_item(idx, row) for idx, row in collision["items"])
        parts.append("\n\n".join(lines))
    return "\n\n".join(parts)


def format_blocking_validation_message(report, books):
    """Formate le blocage GUI sans creer de fenetre Tk."""
    collisions = find_book_url_collisions(books)
    if collisions:
        title = "URLs de livres en conflit"
        if len(collisions) > 1:
            intro = "Plusieurs ouvrages actifs produisent des URL identiques"
        elif len(collisions[0]["items"]) == 2:
            intro = "Deux ouvrages actifs produisent la même URL"
        else:
            intro = "Plusieurs ouvrages actifs produisent la même URL"
        message = [
            "La génération est arrêtée avant toute modification du site.",
            "",
            f"{intro} :",
            "",
            _format_book_collisions(collisions, limit=5),
        ]
        remaining = len(collisions) - 5
        if remaining > 0:
            message.extend(["", f"... et {remaining} autre(s) URL en conflit."])

        message.extend([
            "",
            "Dans le fichier Excel, modifiez la cellule de la colonne « slug »",
            "de l'un des ouvrages afin de lui donner une valeur différente,",
            "par exemple « meme-slug-2 ».",
            "",
            "Enregistrez le classeur, puis relancez la génération.",
        ])

        other_blocking = [
            issue for issue in report.blocking_issues
            if not (issue.code == "DUPLICATE_OUTPUT_TARGET" and issue.entity == "book")
        ]
        if other_blocking:
            message.extend(["", "Autres problèmes bloquants :"])
            message.extend(f"- {i.code} : {i.message}" for i in other_blocking)

        log_message = "Collisions d'URL de livres détectées:\n\n" + _format_book_collisions(collisions)
        if other_blocking:
            log_message += "\n\nAutres problèmes bloquants:\n" + "\n".join(
                f"- {i.code} : {i.message}" for i in other_blocking
            )
        return title, "\n".join(message), log_message

    title = "Blocage de validation"
    message = "La génération est interrompue avant toute modification du dossier de sortie.\n\n"
    message += "\n".join(f"- {i.code} : {i.message}" for i in report.blocking_issues[:8])
    if len(report.blocking_issues) > 8:
        message += f"\n- ... {len(report.blocking_issues) - 8} autre(s) problème(s)"
    return title, message, message


def format_slug_change_message(change: SlugChange) -> str:
    return (
        f"Titre : {change.title or '(titre absent)'}\n"
        f"ISBN : {change.id13}\n\n"
        "Slug actuellement publié :\n"
        f"{change.published_slug}\n\n"
        "Slug qui serait généré :\n"
        f"{change.current_slug}\n\n"
        "Slug recommandé à recopier dans l'Excel :\n"
        f"{change.recommended_slug}"
    )


def format_slug_changes_log(changes: list[SlugChange]) -> str:
    parts = ["Changements de slug de livres détectés :"]
    for change in changes:
        parts.extend(["", format_slug_change_message(change)])
    return "\n".join(parts)


def validation_report_without_slug_changes(report):
    return type(report)([issue for issue in report.issues if issue.code not in PUBLISHED_SLUG_ALERT_CODES])


def validation_report_for_stability_alerts(report, *, include_slug_changes: bool = True):
    return type(report)([
        issue for issue in report.issues
        if issue.code in PUBLISHED_SLUG_ALERT_CODES
        and (include_slug_changes or issue.code != "BOOK_SLUG_CHANGED")
    ])


class SlugChangeDialog(tk.Toplevel):
    def __init__(self, parent, changes: list[SlugChange]):
        super().__init__(parent)
        self.title("Stabilité des URL des livres")
        self.result = False
        self.changes = changes

        self.transient(parent)
        self.grab_set()

        tk.Label(
            self,
            text=(
                "Des ouvrages déjà publiés changeraient d'URL.\n"
                "L'action recommandée est d'annuler et de recopier le slug publié dans l'Excel."
            ),
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 8))

        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=12, pady=6)

        self.listbox = tk.Listbox(body, height=min(8, max(3, len(changes))), exportselection=False)
        self.listbox.pack(side="left", fill="y")
        for change in changes:
            self.listbox.insert("end", f"{change.id13} - {change.title or '(titre absent)'}")

        self.text = tk.Text(body, height=14, width=72, wrap="word")
        self.text.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.listbox.bind("<<ListboxSelect>>", lambda _evt: self._refresh_details())
        self.listbox.selection_set(0)
        self._refresh_details()

        buttons = tk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=(8, 12))
        tk.Button(buttons, text="Copier le slug recommandé", command=self.copy_selected_slug).pack(side="left")
        tk.Button(buttons, text="Copier toutes les corrections", command=self.copy_all_corrections).pack(side="left", padx=8)
        tk.Button(buttons, text="Annuler et corriger l'Excel", command=self.cancel).pack(side="right")
        tk.Button(buttons, text="Générer malgré les changements", command=self.continue_build).pack(side="right", padx=8)

        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def _selected_index(self) -> int:
        selection = self.listbox.curselection()
        return int(selection[0]) if selection else 0

    def _refresh_details(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", format_slug_change_message(self.changes[self._selected_index()]))
        self.text.configure(state="disabled")

    def _copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)

    def copy_selected_slug(self) -> None:
        self._copy_text(self.changes[self._selected_index()].recommended_slug)

    def copy_all_corrections(self) -> None:
        self._copy_text(slug_correction_text(self.changes))

    def cancel(self) -> None:
        self.result = False
        self.destroy()

    def continue_build(self) -> None:
        self.result = True
        self.destroy()


def confirm_slug_changes(parent, changes: list[SlugChange]) -> bool:
    dialog = SlugChangeDialog(parent, changes)
    parent.wait_window(dialog)
    return bool(dialog.result)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Générateur de site statique (Excel → HTML)")
        self.geometry("900x610")

        # serveur
        self._preview_server = None

        # Vars
        self.var_excel = tk.StringVar(value="")
        self.var_out = tk.StringVar(value="")
        self.var_covers = tk.StringVar(value="")
        self.var_assets = tk.StringVar(value=DEFAULT_ASSETS_VALUE)
        self.var_validate_only = tk.BooleanVar(value=False)
        self.var_export_onix = tk.BooleanVar(value=False)

        # Publication FTP
        self.var_publish_ftp = tk.BooleanVar(value=False)

        # Debounce pour la vérification FTP quand le chemin Excel change
        self._ftp_check_job = None
        self.var_excel.trace_add("write", self._on_excel_changed)

        # Serveur local
        self.var_start_server = tk.BooleanVar(value=True)
        self.var_port = tk.IntVar(value=8000)

        # UI
        self._build_ui()

        # État initial (case FTP grisée tant que la config n'est pas détectée)
        self.after(50, self.refresh_ftp_state)

    def _ui_pump(self):
        try:
            while True:
                evt = self._uiq.get_nowait()
                etype = evt.get("type")

                if etype == "ftp_start":
                    self.var_status.set(f"FTP : préparation ({evt.get('total_files')} fichiers)…")
                    self.var_prog.set(0.0)

                elif etype in ("file_start", "progress", "file_done", "file_skip"):
                    i = evt.get("i", 0);
                    n = evt.get("n", 0)
                    relpath = evt.get("relpath", "")
                    sent_total = float(evt.get("sent_total", 0) or 0)
                    total_bytes = float(evt.get("total_bytes", 1) or 1)
                    pct = 0.0 if total_bytes <= 0 else (sent_total / total_bytes) * 100.0
                    if pct > 100.0: pct = 100.0

                    self.var_prog.set(pct)
                    self.var_status.set(f"FTP {i}/{n} : {relpath} — {pct:.0f}%")

                elif etype == "file_error":
                    self.log(f"❌ FTP erreur sur {evt.get('relpath')}: {evt.get('error')}")

                elif etype == "ftp_done":
                    self.var_prog.set(100.0)
                    self.var_status.set(
                        f"FTP terminé ✅  envoyés={evt.get('uploaded')}  ignorés={evt.get('skipped')}  erreurs={evt.get('errors')}"
                    )

        except queue.Empty:
            pass
        self.after(100, self._ui_pump)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        frm = tk.Frame(self)
        frm.pack(fill="x", **pad)

        # Excel
        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Label(row, text="Fichier Excel (.xlsx recommandé) :", width=30, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=self.var_excel).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Choisir…", command=self.pick_excel).pack(side="left")

        # Output
        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Label(row, text="Dossier de sortie :", width=30, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=self.var_out).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Choisir…", command=self.pick_out).pack(side="left")

        # Covers
        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Label(row, text="Dossier des couvertures (optionnel) :", width=30, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=self.var_covers).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Choisir…", command=self.pick_covers).pack(side="left")

        # Assets
        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Label(row, text="Dossier source des assets (optionnel) :", width=30, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=self.var_assets).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Choisir…", command=self.pick_assets).pack(side="left")
        tk.Button(
            row,
            text="?",
            width=3,
            command=self.show_assets_help,
            takefocus=True,
        ).pack(side="left", padx=(6, 0))

        # Profil de génération
        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Label(row, text="Profil de génération :", width=30, anchor="w").pack(side="left")
        tk.Button(row, text="Charger un profil…", command=self.load_profile).pack(side="left")
        tk.Button(row, text="Enregistrer le profil…", command=self.save_profile).pack(side="left", padx=8)

        # Options
        # Options (sur 2 lignes pour éviter le débordement)
        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Checkbutton(
            row,
            text="Validation seulement (ne génère que validation.csv + catalogue.json)",
            variable=self.var_validate_only,
            anchor="w",
            justify="left",
            wraplength=820,  # ajuste si tu changes la largeur fenêtre
        ).pack(side="top", anchor="w", fill="x")

        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Checkbutton(
            row,
            text="Générer l’export ONIX (onix/purh_onix.xml + onix/purh_onix_QA.csv)",
            variable=self.var_export_onix,
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(side="top", anchor="w", fill="x")

        # FTP
        row = tk.Frame(frm)
        row.pack(fill="x", **pad)

        self.cb_publish_ftp = tk.Checkbutton(
            row,
            text="Publier en FTP après génération (selon l’onglet CONFIG)",
            variable=self.var_publish_ftp,
            state="disabled",
        )
        self.cb_publish_ftp.pack(side="left")

        # Voyant ● + texte statut
        self.lbl_ftp_light = tk.Label(row, text="●", fg="gray")
        self.lbl_ftp_light.pack(side="left", padx=(10, 2))

        self.lbl_ftp_status = tk.Label(row, text="(FTP non configuré)")
        self.lbl_ftp_status.pack(side="left", padx=(0, 10))

        # Bouton test
        self.btn_ftp_test = tk.Button(row, text="Tester", command=self.test_ftp, state="disabled")
        self.btn_ftp_test.pack(side="left")

        # Serveur local
        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Checkbutton(
            row,
            text="Lancer le serveur local après génération",
            variable=self.var_start_server
        ).pack(side="left")
        tk.Label(row, text="Port :", padx=10).pack(side="left")
        tk.Spinbox(row, from_=1024, to=65535, textvariable=self.var_port, width=8).pack(side="left")

        # Actions
        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        self.btn_run = tk.Button(row, text="Générer le site", command=self.run_build)
        self.btn_run.pack(side="left")

        tk.Button(row, text="Ouvrir le dossier de sortie", command=self.open_out_folder).pack(side="left", padx=8)

        self.btn_server_toggle = tk.Button(row, text="Arrêter le serveur", command=self.toggle_server, state="disabled")
        self.btn_server_toggle.pack(side="left", padx=8)

        tk.Button(row, text="Ouvrir dans le navigateur", command=self.open_in_browser).pack(side="left")

        # --- Statut + jauge FTP/Build ---
        row = tk.Frame(frm)
        row.pack(fill="x", padx=10, pady=(0, 6))

        self.var_status = tk.StringVar(value="Prêt.")
        tk.Label(row, textvariable=self.var_status, anchor="w").pack(side="left", fill="x", expand=True)

        self.var_prog = tk.DoubleVar(value=0.0)
        self.pbar = ttk.Progressbar(row, variable=self.var_prog, maximum=100.0, mode="determinate", length=260)
        self.pbar.pack(side="right")

        self._uiq = queue.Queue()
        self.after(100, self._ui_pump)

        # Log
        tk.Label(self, text="Journal :", anchor="w").pack(fill="x", padx=10, pady=(10, 0))
        self.txt = tk.Text(self, height=20)
        self.txt.pack(fill="both", expand=True, padx=10, pady=10)
        self.log("Prêt. Choisis un Excel, puis clique sur “Générer le site”.")

        # Arrêt propre si on ferme la fenêtre
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def log(self, msg: str):
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")

    # -------------------------
    # Vérification config FTP depuis l'Excel
    # -------------------------
    def _on_excel_changed(self, *_):
        """Debounce: ne relit pas l'Excel à chaque frappe."""
        if self._ftp_check_job is not None:
            try:
                self.after_cancel(self._ftp_check_job)
            except Exception:
                pass
        self._ftp_check_job = self.after(450, self.refresh_ftp_state)

    def _read_cfg_from_excel(self, excel_path: Path):
        wb = pd.ExcelFile(excel_path)
        return load_config(wb, "CONFIG")

    def _ftp_config_status(self, excel_path: Path) -> tuple[bool, str]:
        """Retourne (ok, raison) pour activer la publication FTP."""
        try:
            if not excel_path or not excel_path.exists():
                return False, "classeur non sélectionné"
            cfg = self._read_cfg_from_excel(excel_path)
        except Exception:
            return False, "onglet CONFIG illisible"

        host = (getattr(cfg, "ftp_host", "") or "").strip()
        user = (getattr(cfg, "ftp_user", "") or "").strip()
        pw = (getattr(cfg, "ftp_password", "") or "").strip()
        remote_dir = (getattr(cfg, "ftp_remote_dir", "") or "").strip()
        if remote_dir.endswith("."):
            # petit garde-fou contre le point final souvent ajouté dans les phrases
            remote_dir = remote_dir.rstrip(".").strip()

        missing = [
            ("ftp_host", host),
            ("ftp_user", user),
            ("ftp_password", pw),
            ("ftp_remote_dir", remote_dir),
        ]
        missing = [k for (k, v) in missing if not v]
        if missing:
            return False, "champs manquants: " + ", ".join(missing)
        return True, "ok"

    def refresh_ftp_state(self):
        """Active/désactive la case 'Publier par FTP' en fonction de l'Excel."""
        self._ftp_check_job = None

        path_str = self.var_excel.get().strip()
        if not path_str:
            self.var_publish_ftp.set(False)
            self.cb_publish_ftp.config(state="disabled")
            self.lbl_ftp_status.config(text="(FTP indisponible : classeur non sélectionné)")
            return

        excel_path = Path(path_str).expanduser()

        ok, reason = self._ftp_config_status(excel_path)
        if ok:
            self.cb_publish_ftp.config(state="normal")
            self.btn_ftp_test.config(state="normal")
            self._set_ftp_ui("gray", "(FTP configuré – non testé)")
        else:
            self.var_publish_ftp.set(False)
            self.cb_publish_ftp.config(state="disabled")
            self.btn_ftp_test.config(state="disabled")
            self._set_ftp_ui("gray", f"(FTP indisponible : {reason})")

    def _set_ftp_ui(self, color: str, text: str):
        self.lbl_ftp_light.config(fg=color)
        self.lbl_ftp_status.config(text=text)

    def _ftp_try_connect(self, cfg) -> tuple[bool, str]:
        """
        Test réel : connect -> login -> (optionnel) cwd(remote_dir).
        Mode 'auto' : tente FTPS explicite, si refus (500/503) bascule en FTP simple.
        """
        host = (getattr(cfg, "ftp_host", "") or "").strip()
        user = (getattr(cfg, "ftp_user", "") or "").strip()
        pw   = (getattr(cfg, "ftp_password", "") or "").strip()
        remote_dir = (getattr(cfg, "ftp_remote_dir", "") or "").strip().rstrip(".").strip()

        port = int(getattr(cfg, "ftp_port", 21) or 21)
        passive = bool(getattr(cfg, "ftp_passive", True))

        # optionnel : dans CONFIG tu pourras mettre ftp_security = auto/plain/ftps
        security = (getattr(cfg, "ftp_security", "auto") or "auto").strip().lower()

        def try_plain():
            ftp = FTP(timeout=15)
            ftp.connect(host, port)
            ftp.login(user=user, passwd=pw)
            ftp.set_pasv(passive)
            if remote_dir:
                ftp.cwd(remote_dir)
            ftp.quit()
            return True, "Connexion FTP OK"

        def try_ftps_explicit():
            ftps = FTP_TLS(timeout=15)
            ftps.connect(host, port)
            ftps.login(user=user, passwd=pw)  # déclenche AUTH TLS
            # protection canal de données
            ftps.prot_p()  # PBSZ 0 + PROT P
            ftps.set_pasv(passive)
            if remote_dir:
                ftps.cwd(remote_dir)
            ftps.quit()
            return True, "Connexion FTPS (TLS explicite) OK"

        # Choix explicite
        if security in ("plain", "ftp"):
            return try_plain()
        if security in ("ftps", "tls", "explicit"):
            return try_ftps_explicit()

        # Auto : FTPS puis fallback FTP si le serveur refuse TLS
        try:
            return try_ftps_explicit()
        except error_perm as e:
            msg = str(e).lower()
            # Tes erreurs précédentes typiques :
            # - 500 This security scheme is not implemented
            # - 503 PBSZ=0
            if msg.startswith("500") or msg.startswith("503") or "security scheme" in msg or "pbsz" in msg:
                return try_plain()
            raise

    def test_ftp(self):
        """Lance un test de connexion FTP sans bloquer l'UI."""
        path_str = self.var_excel.get().strip()
        if not path_str:
            self.var_publish_ftp.set(False)
            self.cb_publish_ftp.config(state="disabled")
            self.btn_ftp_test.config(state="disabled")
            self._set_ftp_ui("gray", "(FTP indisponible : classeur non sélectionné)")
            return

        excel_path = Path(path_str).expanduser()
        ok, reason = self._ftp_config_status(excel_path)
        if not ok:
            self._set_ftp_ui("red", f"(FTP indisponible : {reason})")
            return

        # UI : état "en cours"
        self.btn_ftp_test.config(state="disabled")
        self._set_ftp_ui("gray", "(Test FTP en cours…)")

        def worker():
            try:
                cfg = self._read_cfg_from_excel(excel_path)
                ok2, msg = self._ftp_try_connect(cfg)
                if ok2:
                    self.after(0, lambda: self._set_ftp_ui("green", f"(OK) {msg}"))
                else:
                    self.after(0, lambda: self._set_ftp_ui("red", f"(KO) {msg}"))
            except Exception as e:
                self.after(0, lambda: self._set_ftp_ui("red", f"(KO) {e}"))
            finally:
                self.after(0, lambda: self.btn_ftp_test.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def pick_excel(self):
        path = filedialog.askopenfilename(
            title="Choisir le classeur Excel",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Excel xlsx", "*.xlsx"), ("Excel xls", "*.xls"), ("Tous fichiers", "*.*")]
        )
        if path:
            self.var_excel.set(path)

    def pick_out(self):
        path = filedialog.askdirectory(title="Choisir le dossier de sortie")
        if path:
            self.var_out.set(path)

    def pick_covers(self):
        path = filedialog.askdirectory(title="Choisir le dossier des couvertures")
        if path:
            self.var_covers.set(path)

    def pick_assets(self):
        path = filedialog.askdirectory(title="Choisir le dossier source des assets")
        if path:
            self.var_assets.set(path)

    def show_assets_help(self):
        messagebox.showinfo("Structure du dossier des assets", ASSETS_HELP_TEXT)

    def _current_generation_profile(self) -> GenerationProfile:
        return GenerationProfile(
            excel_path=self.var_excel.get().strip(),
            output_dir=self.var_out.get().strip(),
            covers_dir=self.var_covers.get().strip(),
            assets_dir=self.var_assets.get().strip(),
        )

    def _apply_generation_profile(self, profile: GenerationProfile) -> None:
        self.var_excel.set(profile.excel_path)
        self.var_out.set(profile.output_dir)
        self.var_covers.set(profile.covers_dir)
        self.var_assets.set(profile.assets_dir)
        self.refresh_ftp_state()

    def load_profile(self):
        path = filedialog.askopenfilename(
            title="Charger un profil de génération",
            filetypes=[("Profil JSON", "*.json"), ("Tous fichiers", "*.*")],
        )
        if not path:
            return
        try:
            profile = load_generation_profile(Path(path))
            self._apply_generation_profile(profile)
        except GenerationProfileError as exc:
            messagebox.showerror("Profil de génération invalide", str(exc))
            return
        messagebox.showinfo("Profil de génération", "Profil de génération chargé.")

    def save_profile(self):
        path = filedialog.asksaveasfilename(
            title="Enregistrer le profil de génération",
            defaultextension=".json",
            filetypes=[("Profil JSON", "*.json"), ("Tous fichiers", "*.*")],
        )
        if not path:
            return
        try:
            save_generation_profile(Path(path), self._current_generation_profile())
        except OSError as exc:
            messagebox.showerror("Profil de génération", f"Impossible d'enregistrer le profil :\n\n{exc}")
            return
        messagebox.showinfo("Profil de génération", "Profil de génération enregistré.")

    def open_out_folder(self):
        out_dir = self._selected_out_dir()
        if out_dir is None:
            return
        if not out_dir.exists():
            messagebox.showinfo("Info", "Le dossier de sortie n’existe pas encore (génère d’abord).")
            return
        try:
            import os
            os.startfile(out_dir)  # Windows
        except Exception:
            messagebox.showinfo("Info", f"Dossier : {out_dir}")

    # -------------------------
    # Serveur local
    # -------------------------
    # -------------------------
    # Serveur local (embarqué, compatible .exe)
    # -------------------------
    def start_server(self, out_dir: Path, port: int) -> str | None:
        out_dir = out_dir.resolve()
        if not out_dir.exists():
            self.log("⚠️ Le dossier de sortie n’existe pas (génère d’abord).")
            return None

        # Stoppe un serveur existant
        if self._preview_server:
            try:
                self._preview_server.stop()
            except Exception:
                pass
            self._preview_server = None

        try:
            srv = PreviewServer(directory=str(out_dir), host="127.0.0.1", port=int(port))
            url = srv.start()  # peut changer de port si déjà pris
            self._preview_server = srv

            # Met à jour le port réel (si fallback automatique)
            self.var_port.set(int(srv.port))

            self.btn_server_toggle.config(state="normal", text="Arrêter le serveur")
            self.log(f"🌐 Serveur local : {url}  (dossier: {out_dir})")
            return url
        except Exception as e:
            self._preview_server = None
            self.btn_server_toggle.config(state="disabled", text="Arrêter le serveur")
            self.log(f"❌ Impossible de lancer le serveur : {e}")
            return None

    def stop_server(self):
        if not self._preview_server:
            return
        try:
            self._preview_server.stop()
        except Exception:
            pass
        finally:
            self._preview_server = None
            self.btn_server_toggle.config(state="disabled", text="Arrêter le serveur")
            self.log("🛑 Serveur arrêté.")

    def toggle_server(self):
        out_dir = self._selected_out_dir()
        if out_dir is None:
            return
        if self._preview_server:
            self.stop_server()
        else:
            url = self.start_server(out_dir, int(self.var_port.get()))
            if url:
                webbrowser.open(url)

    def open_in_browser(self):
        out_dir = self._selected_out_dir()
        if out_dir is None:
            return

        # Si déjà lancé, on ouvre l’URL réelle
        if self._preview_server:
            webbrowser.open(f"http://127.0.0.1:{int(self._preview_server.port)}/")
            return

        # Sinon, on démarre puis on ouvre (comportement pratique)
        url = self.start_server(out_dir, int(self.var_port.get()))
        if url:
            webbrowser.open(url)

    def on_close(self):
        self.stop_server()
        self.destroy()


    # -------------------------
    # Build
    # -------------------------
    def _selected_out_dir(self) -> Path | None:
        out_value = self.var_out.get().strip()
        if not out_value:
            messagebox.showerror(
                "Dossier de sortie manquant",
                "Choisissez le dossier dans lequel le site doit être généré.",
            )
            return None
        return Path(out_value).expanduser()

    def run_build(self):
        excel = Path(self.var_excel.get()).expanduser().resolve()
        out_value = self.var_out.get().strip()
        if not out_value:
            messagebox.showerror(
                "Dossier de sortie manquant",
                "Choisissez le dossier dans lequel le site doit être généré.",
            )
            return
        out_dir = Path(out_value).expanduser().resolve()
        covers = Path(self.var_covers.get()).expanduser() if self.var_covers.get().strip() else None
        try:
            assets_dir = resolve_assets_dir_for_gui(self.var_assets.get(), out_dir)
        except AssetSourceError as e:
            messagebox.showerror("Dossier des assets invalide", f"{e}")
            return
        validate_only = bool(self.var_validate_only.get())

        if not excel.exists():
            messagebox.showerror("Erreur", "Choisis un fichier Excel existant.")
            return

        # Lire new_months depuis CONFIG (et fallback à 6 si problème)
        try:
            cfg = self._read_cfg_from_excel(excel)
            new_months = int(getattr(cfg, "new_months", 6) or 6)
        except Exception:
            new_months = 6

        books_validation = pd.DataFrame()
        try:
            with pd.ExcelFile(excel) as wb:
                cfg_validation = load_config(wb, "CONFIG")
                books_sheet = detect_books_sheet(wb, getattr(cfg_validation, "books_sheet", "") or "")
                books_validation = load_books(wb, books_sheet)
                pages_validation = load_pages(wb, cfg_validation.pages_sheet)
                collections_validation = load_collections(wb, cfg_validation.collections_sheet)
                revues_validation = load_revues(wb, cfg_validation.revues_sheet)
                contacts_validation = load_contacts(wb, cfg_validation.contacts_sheet)
                actualites_validation = load_actualites(wb)
            validation_report = validate_site_data(
                books=books_validation,
                cfg=cfg_validation,
                pages=pages_validation,
                collections=collections_validation,
                revues=revues_validation,
                contacts=contacts_validation,
                actualites=actualites_validation,
                excel_path=excel,
                out_dir=out_dir,
                covers_dir=covers,
            )
            if validation_report.has_blocking_issues:
                published_comparison = None
            else:
                published_comparison = compare_published_book_slugs(out_dir / "catalogue.json", books_validation)
                validation_report.issues.extend(published_slug_issues(published_comparison))
        except Exception as e:
            messagebox.showerror("Validation impossible", f"La validation a échoué :\n\n{e}")
            return

        self.log(format_validation_summary(validation_report))

        def confirm_alerts(report):
            extrait = "\n".join(
                f"- {i.code} : {i.message}" for i in report.alerts[:8]
            )
            if len(report.alerts) > 8:
                extrait += f"\n- ... {len(report.alerts) - 8} autre(s) alerte(s)"
            return messagebox.askyesno(
                "Alertes de validation",
                "CIDRE a détecté des alertes fortes mais contournables.\n\n"
                f"{extrait}\n\n"
                "Voulez-vous générer malgré ces alertes ?"
            )

        if validation_report.has_blocking_issues:
            title, message, log_message = format_blocking_validation_message(validation_report, books_validation)
            self.log(log_message)
            messagebox.showerror(title, message)
            return

        slug_changes = published_comparison.changes if published_comparison else []
        if slug_changes:
            self.log(format_slug_changes_log(slug_changes))
            if not confirm_slug_changes(self, slug_changes):
                self.log("Génération annulée : corrigez les slugs dans l'Excel puis relancez.")
                return

        stability_alert_report = validation_report_for_stability_alerts(
            validation_report,
            include_slug_changes=not bool(slug_changes),
        )
        if stability_alert_report.has_alerts and not should_continue_after_validation(stability_alert_report, confirm_alerts):
            self.log("Génération annulée : le dossier de sortie n'a pas été modifié.")
            return

        remaining_alert_report = validation_report_without_slug_changes(validation_report)
        if not should_continue_after_validation(remaining_alert_report, confirm_alerts):
            out_dir.mkdir(parents=True, exist_ok=True)
            write_validation_csv(validation_report, out_dir / "validation.csv")
            self.log(f"Validation interrompue : rapport écrit dans {out_dir / 'validation.csv'}")
            return

        if out_dir.exists() and not validate_only:
            if not messagebox.askyesno(
                "Recomposer le dossier de sortie",
                "Le dossier de sortie existe déjà.\n\n"
                "La génération complète va le recomposer entièrement : "
                "tout son contenu sera supprimé sauf les dossiers assets/ et covers/.\n\n"
                "Voulez-vous continuer ?",
            ):
                return

        do_publish_ftp = bool(self.var_publish_ftp.get())
        export_onix = bool(self.var_export_onix.get())

        # Vérification FTP au dernier moment (au cas où le fichier CONFIG a été modifié)
        if do_publish_ftp:
            ftp_ok, ftp_reason = self._ftp_config_status(excel)
            if not ftp_ok:
                self.refresh_ftp_state()
                messagebox.showerror(
                    "FTP indisponible",
                    f"La publication FTP est cochée, mais la configuration est incomplète :\n\n{ftp_reason}\n\n"
                    "Complète l'onglet CONFIG puis réessaie."
                )
                return

        self.btn_run.config(state="disabled")
        self.log("------------------------------------------------------------")
        self.log(f"Lancement : {excel}")
        self.log(f"Sortie   : {out_dir}")
        self.log(f"Covers   : {covers if covers else '(aucun)'}")
        self.log(f"Assets   : {assets_dir if assets_dir else '(aucun)'}")
        for ignored in ignored_reserved_asset_json(assets_dir):
            self.log(
                f"⚠️ Asset ignoré : {ignored} "
                "(catalogue.json et actualites.json sont générés à la racine du site)."
            )
        self.log(f"Mode     : {'validation seulement' if validate_only else 'génération complète'}")
        self.log(f"FTP      : {'oui' if do_publish_ftp else 'non'}")
        self.log(f"ONIX     : {'oui' if export_onix else 'non'}")
        self.log("------------------------------------------------------------")

        def worker():
            def progress_cb(evt: dict):
                # callback appelée depuis le thread worker → on passe par la queue
                self._uiq.put(evt)
            try:
                build_site(
                    excel_path=excel,
                    out_dir=out_dir,
                    covers_dir=covers,
                    assets_dir=assets_dir,
                    validate_only=validate_only,
                    new_months=new_months,
                    # code changé pour brancher la sortie onix d'abord
                    # on publie plus tard
                    # publish=do_publish_ftp,
                    publish=False,
                    force_alerts=True,
                    progress_cb=progress_cb,
                )
                self.after(0, lambda: self.log("✅ Terminé."))
                self.after(0, lambda: self.log(f"→ {out_dir / 'validation.csv'}"))
                self.after(0, lambda: self.log(f"→ {out_dir / 'catalogue.json'}"))

                if export_onix:
                    try:
                        wb = pd.ExcelFile(excel)
                        cfg_onix = load_config(wb, "CONFIG")
                        sheet_master = detect_books_sheet(wb, getattr(cfg_onix, "books_sheet", "") or "")

                        onix_dir = out_dir / "onix"
                        onix_dir.mkdir(parents=True, exist_ok=True)

                        onix_xml = onix_dir / "purh_onix.xml"
                        onix_report = onix_dir / "purh_onix_QA.csv"

                        export_onix_from_excel(
                            excel_path=str(excel),
                            out_xml_path=str(onix_xml),
                            sheet_master=sheet_master,
                            strict=False,
                            report_csv_path=str(onix_report),
                        )

                        self.after(0, lambda: self.log(f"→ {onix_xml}"))
                        self.after(0, lambda: self.log(f"→ {onix_report}"))
                    except Exception as e:
                        self.after(0, lambda: self.log(f"❌ Erreur ONIX : {e}"))

                # =========================================================
                # (ÉTAPE 4) FTP : à faire APRÈS l’ONIX pour qu’il soit uploadé
                # =========================================================
                if do_publish_ftp:
                    cfg_publish = self._read_cfg_from_excel(excel)
                    publish_ftp(cfg_publish, out_dir, progress_cb=progress_cb)

                if (not validate_only) and bool(self.var_start_server.get()):
                    def _start_and_open():
                        url = self.start_server(out_dir, int(self.var_port.get()))
                        if url:
                            webbrowser.open(url)

                    self.after(0, _start_and_open)

            except Exception:
                err = traceback.format_exc()
                self.after(0, lambda: self.log("❌ Erreur pendant la génération :"))
                self.after(0, lambda: self.log(err))
                self.after(0, lambda: messagebox.showerror("Erreur", "La génération a échoué. Copie/colle le log."))
            finally:
                self.after(0, lambda: self.btn_run.config(state="normal"))

        self.stop_server()
        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    App().mainloop()
