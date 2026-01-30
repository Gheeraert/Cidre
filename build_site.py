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

# build_site.py doit être dans le même dossier et contenir build_site(...) + load_config(...)
from build_site import build_site, load_config, publish_ftp, detect_books_sheet
from export_onix_py import export_onix_from_excel

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Générateur de site statique (Excel → HTML)")
        self.geometry("900x610")

        # serveur
        self._preview_server = None

        # Vars
        self.var_excel = tk.StringVar(value="")
        self.var_out = tk.StringVar(value=str(Path.cwd() / "dist"))
        self.var_covers = tk.StringVar(value="")
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

    def open_out_folder(self):
        out_dir = Path(self.var_out.get()).expanduser()
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
        out_dir = Path(self.var_out.get()).expanduser()
        if self._preview_server:
            self.stop_server()
        else:
            url = self.start_server(out_dir, int(self.var_port.get()))
            if url:
                webbrowser.open(url)

    def open_in_browser(self):
        out_dir = Path(self.var_out.get()).expanduser()

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
    def run_build(self):
        excel = Path(self.var_excel.get()).expanduser().resolve()
        out_dir = Path(self.var_out.get()).expanduser().resolve()
        covers = Path(self.var_covers.get()).expanduser() if self.var_covers.get().strip() else None
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
                    validate_only=validate_only,
                    new_months=new_months,
                    # code changé pour brancher la sortie onix d'abord
                    # on publie plus tard
                    # publish=do_publish_ftp,
                    publish=False,
                    progress_cb=progress_cb,
                )
                self.after(0, lambda: self.log("✅ Terminé."))
                self.after(0, lambda: self.log(f"→ {out_dir / 'validation.csv'}"))
                self.after(0, lambda: self.log(f"→ {out_dir / 'assets' / 'catalogue.json'}"))

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
