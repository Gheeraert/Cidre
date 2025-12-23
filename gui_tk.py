# gui_tk.py
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import sys
import webbrowser
import socket
import pandas as pd

# build_site.py doit être dans le même dossier et contenir build_site(...) + load_config(...)
from build_site import build_site, load_config


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Générateur de site statique (Excel → HTML)")
        self.geometry("900x610")

        # Vars
        self.var_excel = tk.StringVar(value="")
        self.var_out = tk.StringVar(value=str(Path.cwd() / "dist"))
        self.var_covers = tk.StringVar(value="")
        self.var_validate_only = tk.BooleanVar(value=False)

        # Publication FTP
        self.var_publish_ftp = tk.BooleanVar(value=False)

        # Debounce pour la vérification FTP quand le chemin Excel change
        self._ftp_check_job = None
        self.var_excel.trace_add("write", self._on_excel_changed)

        # Serveur local
        self.var_start_server = tk.BooleanVar(value=True)
        self.var_port = tk.IntVar(value=8000)
        self.server_proc: subprocess.Popen | None = None
        self._server_log_handle = None

        # UI
        self._build_ui()

        # État initial (case FTP grisée tant que la config n'est pas détectée)
        self.after(50, self.refresh_ftp_state)

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
        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Checkbutton(
            row,
            text="Validation seulement (ne génère que validation.csv + catalogue.json)",
            variable=self.var_validate_only
        ).pack(side="left")

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
        self.lbl_ftp_status = tk.Label(row, text="(FTP non configuré)")
        self.lbl_ftp_status.pack(side="left", padx=10)

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
            self.lbl_ftp_status.config(text="(FTP configuré)")
        else:
            self.var_publish_ftp.set(False)
            self.cb_publish_ftp.config(state="disabled")
            self.lbl_ftp_status.config(text=f"(FTP indisponible : {reason})")

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
    def is_port_free(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False

    def start_server(self, out_dir: Path, port: int):
        out_dir = out_dir.resolve()
        if not out_dir.exists():
            self.log("⚠️ Le dossier de sortie n’existe pas (génère d’abord).")
            return

        if self.server_proc and self.server_proc.poll() is None:
            self.log("ℹ️ Serveur déjà lancé.")
            return

        if not self.is_port_free(port):
            self.log(f"⚠️ Port {port} déjà utilisé. Choisis un autre port.")
            return

        try:
            log_path = out_dir / "server.log"
            self._server_log_handle = open(log_path, "a", encoding="utf-8")
            self.server_proc = subprocess.Popen(
                [sys.executable, "-m", "http.server", str(port)],
                cwd=str(out_dir),
                stdout=self._server_log_handle,
                stderr=subprocess.STDOUT,
            )
            self.log(f"📄 Log serveur : {log_path}")
            self.btn_server_toggle.config(state="normal", text="Arrêter le serveur")
            self.log(f"🌐 Serveur local : http://localhost:{port}/  (dossier: {out_dir})")
        except Exception as e:
            self.server_proc = None
            if self._server_log_handle:
                try: self._server_log_handle.close()
                except Exception: pass
                self._server_log_handle = None
            self.log(f"❌ Impossible de lancer le serveur : {e}")

    def stop_server(self):
        if not self.server_proc:
            return
        try:
            if self.server_proc.poll() is None:
                self.server_proc.terminate()
        except Exception:
            pass
        finally:
            self.server_proc = None
            self.btn_server_toggle.config(state="disabled", text="Arrêter le serveur")
            if self._server_log_handle:
                try: self._server_log_handle.close()
                except Exception: pass
                self._server_log_handle = None
            self.log("🛑 Serveur arrêté.")

    def toggle_server(self):
        if self.server_proc and self.server_proc.poll() is None:
            self.stop_server()
        else:
            out_dir = Path(self.var_out.get()).expanduser()
            port = int(self.var_port.get())
            self.start_server(out_dir, port)
            self.open_in_browser()

    def open_in_browser(self):
        port = int(self.var_port.get())
        webbrowser.open(f"http://localhost:{port}/")

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

        publish_ftp = bool(self.var_publish_ftp.get())

        # Vérification FTP au dernier moment (au cas où le fichier CONFIG a été modifié)
        if publish_ftp:
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
        self.log(f"FTP      : {'oui' if publish_ftp else 'non'}")
        self.log("------------------------------------------------------------")

        def worker():
            try:
                build_site(
                    excel_path=excel,
                    out_dir=out_dir,
                    covers_dir=covers,
                    validate_only=validate_only,
                    new_months=new_months,
                    publish=publish_ftp,
                )
                self.after(0, lambda: self.log("✅ Terminé."))
                self.after(0, lambda: self.log(f"→ {out_dir / 'validation.csv'}"))
                self.after(0, lambda: self.log(f"→ {out_dir / 'assets' / 'catalogue.json'}"))

                if (not validate_only) and bool(self.var_start_server.get()):
                    port = int(self.var_port.get())
                    self.after(0, lambda: self.start_server(out_dir, port))
                    self.after(200, self.open_in_browser)

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
