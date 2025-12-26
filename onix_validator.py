#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import queue
import re
import threading
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Dépendance externe
try:
    import onixcheck
except Exception as e:
    onixcheck = None
    _onixcheck_import_error = e


SHORT_RE = re.compile(
    r"^(?P<level>\w+)\s*-\s*(?P<code>[^-]+?)\s*-\s*(?P<loc>[^-]+?)\s*-\s*(?P<msg>.*)$"
)


@dataclass
class ErrRow:
    level: str
    code: str
    file: str
    line: str
    col: str
    message: str


def iter_files(p: Path, recursive: bool, exts: set[str]) -> list[Path]:
    if p.is_file():
        return [p]
    if not p.exists():
        return []
    pattern = "**/*" if recursive else "*"
    out = []
    for f in p.glob(pattern):
        if f.is_file() and f.suffix.lower().lstrip(".") in exts:
            out.append(f)
    return sorted(out)


def parse_short(short: str, fallback_file: str = "") -> ErrRow:
    """
    Exemple typique:
      ERROR - SCHEMASV - C:\\path\\file.xml:4:0 - Element 'X': ...
    """
    s = (short or "").strip()
    m = SHORT_RE.match(s)
    if not m:
        return ErrRow("", "", fallback_file, "", "", s)

    level = m.group("level").strip()
    code = m.group("code").strip()
    loc = m.group("loc").strip()
    msg = m.group("msg").strip()

    file_part, line, col = loc, "", ""
    if loc.count(":") >= 2:
        try:
            file_part, line, col = loc.rsplit(":", 2)
        except ValueError:
            pass

    if not file_part:
        file_part = fallback_file

    return ErrRow(level, code, file_part, line, col, msg)


class OnixValidatorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Validateur ONIX (onixcheck)")
        self.geometry("1050x680")
        self.minsize(950, 620)

        # État
        self.path_var = tk.StringVar(value="")
        self.recursive_var = tk.BooleanVar(value=True)
        self.ext_var = tk.StringVar(value="xml,onix,onx")
        self.schemas_var = tk.StringVar(value="xsd")  # xsd par défaut
        self.report_path_var = tk.StringVar(value="")

        self._uiq: queue.Queue = queue.Queue()
        self._rows: list[ErrRow] = []
        self._running = False

        self._build_ui()
        self.after(120, self._ui_pump)

        if onixcheck is None:
            messagebox.showwarning(
                "Dépendance manquante",
                "Le module 'onixcheck' n'est pas disponible.\n\n"
                "Installe-le puis relance :\n"
                "  pip install onixcheck\n\n"
                f"Détail import : {type(_onixcheck_import_error).__name__}: {_onixcheck_import_error}"
            )

    def _build_ui(self):
        pad = dict(padx=10, pady=6)

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        # Ligne chemin
        row = ttk.Frame(top)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Fichier ou dossier :", width=18).pack(side="left")
        ttk.Entry(row, textvariable=self.path_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Choisir fichier…", command=self.pick_file).pack(side="left")
        ttk.Button(row, text="Choisir dossier…", command=self.pick_dir).pack(side="left", padx=(6, 0))

        # Options
        row = ttk.Frame(top)
        row.pack(fill="x", **pad)

        ttk.Checkbutton(row, text="Inclure sous-dossiers (récursif)", variable=self.recursive_var).pack(side="left")

        ttk.Label(row, text="Extensions :", padding=(12, 0, 0, 0)).pack(side="left")
        ttk.Entry(row, textvariable=self.ext_var, width=18).pack(side="left", padx=6)

        ttk.Label(row, text="Schémas :", padding=(12, 0, 0, 0)).pack(side="left")
        cb = ttk.Combobox(
            row,
            textvariable=self.schemas_var,
            values=["xsd", "xsd,rng", "xsd,rng,google"],
            width=14,
            state="readonly",
        )
        cb.pack(side="left", padx=6)

        # Actions
        row = ttk.Frame(top)
        row.pack(fill="x", **pad)
        self.btn_validate = ttk.Button(row, text="Valider", command=self.run_validation)
        self.btn_validate.pack(side="left")

        self.btn_clear = ttk.Button(row, text="Effacer", command=self.clear_results)
        self.btn_clear.pack(side="left", padx=6)

        ttk.Separator(top, orient="horizontal").pack(fill="x", pady=8)

        # Tableau résultats
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        cols = ("level", "code", "file", "line", "col", "message")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings")
        self.tree.heading("level", text="Niveau")
        self.tree.heading("code", text="Code")
        self.tree.heading("file", text="Fichier")
        self.tree.heading("line", text="Ligne")
        self.tree.heading("col", text="Col")
        self.tree.heading("message", text="Message")

        self.tree.column("level", width=70, anchor="w")
        self.tree.column("code", width=90, anchor="w")
        self.tree.column("file", width=330, anchor="w")
        self.tree.column("line", width=55, anchor="e")
        self.tree.column("col", width=45, anchor="e")
        self.tree.column("message", width=420, anchor="w")

        yscroll = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(mid, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        mid.grid_rowconfigure(0, weight=1)
        mid.grid_columnconfigure(0, weight=1)

        # Bas : rapport + statut
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Label(bottom, text="Rapport CSV :").pack(side="left")
        ttk.Entry(bottom, textvariable=self.report_path_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(bottom, text="Choisir…", command=self.pick_report).pack(side="left")

        self.btn_save = ttk.Button(bottom, text="Enregistrer rapport", command=self.save_report, state="disabled")
        self.btn_save.pack(side="left", padx=(6, 0))

        self.status_var = tk.StringVar(value="Prêt.")
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", padx=10, pady=(0, 8))

    # ---------- UI helpers ----------
    def pick_file(self):
        p = filedialog.askopenfilename(
            title="Choisir un fichier ONIX",
            filetypes=[("ONIX / XML", "*.xml *.onix *.onx"), ("Tous fichiers", "*.*")]
        )
        if p:
            self.path_var.set(p)

    def pick_dir(self):
        p = filedialog.askdirectory(title="Choisir un dossier contenant des ONIX")
        if p:
            self.path_var.set(p)

    def pick_report(self):
        p = filedialog.asksaveasfilename(
            title="Enregistrer le rapport CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")]
        )
        if p:
            self.report_path_var.set(p)

    def clear_results(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._rows = []
        self.btn_save.config(state="disabled")
        self.status_var.set("Prêt.")

    # ---------- validation ----------
    def run_validation(self):
        if onixcheck is None:
            messagebox.showerror(
                "onixcheck absent",
                "Le module 'onixcheck' n'est pas installé.\n\n"
                "Installe-le puis relance :\n"
                "  pip install onixcheck"
            )
            return

        if self._running:
            return

        path = Path(self.path_var.get().strip()).expanduser()
        if not path.exists():
            messagebox.showerror("Chemin invalide", "Choisis un fichier ou un dossier existant.")
            return

        exts = {e.strip().lower() for e in self.ext_var.get().split(",") if e.strip()}
        schemas = tuple(s.strip() for s in self.schemas_var.get().split(",") if s.strip())
        recursive = bool(self.recursive_var.get())

        files = iter_files(path, recursive=recursive, exts=exts)
        if not files:
            messagebox.showinfo("Aucun fichier", "Aucun fichier à valider (extensions / dossier).")
            return

        self.clear_results()
        self._running = True
        self.btn_validate.config(state="disabled")
        self.status_var.set(f"Validation en cours… ({len(files)} fichier(s))")

        def worker():
            try:
                total_errors = 0
                all_rows: list[ErrRow] = []
                for i, f in enumerate(files, start=1):
                    self._uiq.put(("status", f"Validation {i}/{len(files)} : {f.name}"))
                    errors = onixcheck.validate(str(f), schemas=schemas)
                    if errors:
                        total_errors += len(errors)
                        for e in errors:
                            short = getattr(e, "short", str(e))
                            all_rows.append(parse_short(short, fallback_file=str(f)))
                self._uiq.put(("done", (all_rows, total_errors, len(files))))
            except Exception as e:
                self._uiq.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _ui_pump(self):
        try:
            while True:
                kind, payload = self._uiq.get_nowait()

                if kind == "status":
                    self.status_var.set(payload)

                elif kind == "error":
                    self._running = False
                    self.btn_validate.config(state="normal")
                    self.status_var.set("Erreur.")
                    messagebox.showerror("Erreur validation", payload)

                elif kind == "done":
                    rows, total_errors, nfiles = payload
                    self._rows = rows

                    for r in rows:
                        self.tree.insert("", "end", values=(r.level, r.code, r.file, r.line, r.col, r.message))

                    self._running = False
                    self.btn_validate.config(state="normal")
                    if total_errors == 0:
                        self.status_var.set(f"✅ OK — {nfiles} fichier(s), aucune erreur.")
                        self.btn_save.config(state="disabled")
                    else:
                        self.status_var.set(f"❌ {total_errors} erreur(s) — {nfiles} fichier(s).")
                        self.btn_save.config(state="normal")

        except queue.Empty:
            pass

        self.after(120, self._ui_pump)

    # ---------- reporting ----------
    def save_report(self):
        if not self._rows:
            messagebox.showinfo("Rien à enregistrer", "Aucune erreur à exporter.")
            return

        out = self.report_path_var.get().strip()
        if not out:
            self.pick_report()
            out = self.report_path_var.get().strip()
            if not out:
                return

        outp = Path(out).expanduser()
        outp.parent.mkdir(parents=True, exist_ok=True)

        try:
            with outp.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["level", "code", "file", "line", "col", "message"])
                for r in self._rows:
                    w.writerow([r.level, r.code, r.file, r.line, r.col, r.message])

            messagebox.showinfo("Rapport enregistré", f"Rapport CSV écrit :\n{outp}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'écrire le rapport :\n{e}")


if __name__ == "__main__":
    OnixValidatorGUI().mainloop()
