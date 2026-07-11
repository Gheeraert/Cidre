# actualites_editor.py — éditeur graphique de la feuille ACTUS d'un classeur Cidre
# © 2026 Tony Gheeraert - Licence MIT (voir LICENSE)
#
# Usage :
#   python actualites_editor.py [chemin/vers/classeur.xlsx]
#
# Sans argument, une boîte de dialogue permet de choisir le classeur.
# L'outil ne modifie que la feuille ACTUS ; une sauvegarde horodatée du
# classeur est créée avant la première écriture.

from __future__ import annotations

import sys
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from actualites_store import (
    ActualitesStore, Actu, ActuError, WorkbookLockedError,
    format_date_fr, parse_date_fr,
)


class EditorApp(tk.Tk):
    def __init__(self, store: ActualitesStore):
        super().__init__()
        self.store = store
        self.title(f"Actualités — {store.path.name}")
        self.geometry("980x680")
        self.minsize(820, 560)

        self.current_row: int | None = None  # ligne Excel en cours d'édition ; None = nouvelle
        self._build_ui()
        self.refresh_list()

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- Liste des actualités ---
        frame_list = ttk.LabelFrame(self, text="Actualités du classeur")
        frame_list.pack(fill="both", expand=False, **pad)

        cols = ("actif", "date", "titre", "image")
        self.tree = ttk.Treeview(frame_list, columns=cols, show="headings", height=8)
        self.tree.heading("actif", text="Active")
        self.tree.heading("date", text="Date")
        self.tree.heading("titre", text="Titre")
        self.tree.heading("image", text="Visuel")
        self.tree.column("actif", width=60, anchor="center", stretch=False)
        self.tree.column("date", width=90, anchor="center", stretch=False)
        self.tree.column("titre", width=520)
        self.tree.column("image", width=180, stretch=False)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)

        sb = ttk.Scrollbar(frame_list, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y", pady=6)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", lambda e: self.load_selected())

        # --- Boutons liste ---
        bar = ttk.Frame(self)
        bar.pack(fill="x", **pad)
        ttk.Button(bar, text="Nouvelle actualité", command=self.new_actu).pack(side="left")
        ttk.Button(bar, text="Modifier la sélection", command=self.load_selected).pack(side="left", padx=6)
        self.btn_toggle = ttk.Button(bar, text="Désactiver / Réactiver", command=self.toggle_selected)
        self.btn_toggle.pack(side="left")

        # --- Formulaire ---
        form = ttk.LabelFrame(self, text="Actualité")
        form.pack(fill="both", expand=True, **pad)
        form.columnconfigure(1, weight=1)

        r = 0
        ttk.Label(form, text="Titre :").grid(row=r, column=0, sticky="ne", **pad)
        self.var_title = tk.StringVar()
        ttk.Entry(form, textvariable=self.var_title).grid(row=r, column=1, columnspan=3, sticky="ew", **pad)

        r += 1
        ttk.Label(form, text="Texte :").grid(row=r, column=0, sticky="ne", **pad)
        self.txt_text = tk.Text(form, height=7, wrap="word", undo=True)
        self.txt_text.grid(row=r, column=1, columnspan=3, sticky="nsew", **pad)
        form.rowconfigure(r, weight=1)

        r += 1
        ttk.Label(form, text="Date (JJ/MM/AAAA) :").grid(row=r, column=0, sticky="e", **pad)
        self.var_date = tk.StringVar()
        ttk.Entry(form, textvariable=self.var_date, width=14).grid(row=r, column=1, sticky="w", **pad)

        self.var_active = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Actualité active (publiée sur le site)",
                        variable=self.var_active).grid(row=r, column=2, columnspan=2, sticky="w", **pad)

        r += 1
        ttk.Label(form, text="Livre associé — ISBN13, facultatif :").grid(row=r, column=0, sticky="e", **pad)
        self.var_isbn = tk.StringVar()
        ttk.Entry(form, textvariable=self.var_isbn, width=20).grid(row=r, column=1, sticky="w", **pad)
        ttk.Button(form, text="Rechercher le livre", command=self.lookup_book).grid(row=r, column=2, sticky="w", **pad)
        ttk.Button(form, text="Choisir la couverture comme visuel",
                   command=self.use_book_cover).grid(row=r, column=3, sticky="w", **pad)

        r += 1
        self.var_book_info = tk.StringVar(value="")
        ttk.Label(form, textvariable=self.var_book_info, foreground="#005a9c",
                  wraplength=680, justify="left").grid(row=r, column=1, columnspan=3, sticky="w", **pad)

        r += 1
        ttk.Label(form, text="Visuel de l'actualité — facultatif :").grid(row=r, column=0, sticky="e", **pad)
        self.var_image = tk.StringVar()
        ttk.Entry(form, textvariable=self.var_image, state="readonly", width=40).grid(row=r, column=1, sticky="w", **pad)
        ttk.Button(form, text="Choisir une image…", command=self.pick_image).grid(row=r, column=2, sticky="w", **pad)
        ttk.Button(form, text="Retirer le visuel",
                   command=lambda: self.var_image.set("")).grid(row=r, column=3, sticky="w", **pad)

        r += 1
        ttk.Label(form, text="Lien externe — facultatif :").grid(row=r, column=0, sticky="e", **pad)
        self.var_link = tk.StringVar()
        ttk.Entry(form, textvariable=self.var_link).grid(row=r, column=1, columnspan=3, sticky="ew", **pad)

        r += 1
        help_text = (
            "Ces trois champs sont indépendants : une actualité peut concerner un salon, un prix, un colloque… "
            "sans livre ni image. Sur la page Actualités du site, le titre et le visuel renvoient à la fiche du "
            "livre si un ISBN du catalogue est renseigné ; le lien externe (inscription, programme, article…) "
            "est affiché en plus, à la fin de l'actualité."
        )
        ttk.Label(form, text=help_text, foreground="#555", wraplength=760,
                  justify="left").grid(row=r, column=0, columnspan=4, sticky="w", **pad)

        # --- Enregistrer + statut ---
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", **pad)
        ttk.Button(bottom, text="Enregistrer", command=self.save).pack(side="left")
        self.var_status = tk.StringVar(value="Prêt.")
        ttk.Label(bottom, textvariable=self.var_status).pack(side="left", padx=12)

    # ------------------------------------------------------------------
    # Liste
    # ------------------------------------------------------------------

    def refresh_list(self, select_row: int | None = None):
        self.tree.delete(*self.tree.get_children())
        for a in self.store.list_actus():
            self.tree.insert(
                "", "end", iid=str(a.row),
                values=("✔" if a.is_active else "—",
                        format_date_fr(a.date) or a.date_raw,
                        a.title, a.image),
            )
        if select_row is not None and self.tree.exists(str(select_row)):
            self.tree.selection_set(str(select_row))
            self.tree.see(str(select_row))

    def _selected_actu(self) -> Actu | None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Sélection", "Sélectionnez d'abord une actualité dans la liste.")
            return None
        row = int(sel[0])
        for a in self.store.list_actus():
            if a.row == row:
                return a
        return None

    def load_selected(self):
        a = self._selected_actu()
        if a is None:
            return
        self.current_row = a.row
        self.var_title.set(a.title)
        self.txt_text.delete("1.0", "end")
        self.txt_text.insert("1.0", a.text)
        self.var_date.set(format_date_fr(a.date) or a.date_raw)
        self.var_active.set(a.is_active)
        self.var_isbn.set(a.id13)
        self.var_link.set(a.link)
        self.var_image.set(a.image)
        self.var_book_info.set("")
        if a.id13:
            _, book = self.store.lookup_isbn(a.id13)
            if book:
                self.var_book_info.set(f"Livre associé : {book.title}")
        self.var_status.set(f"Modification de la ligne {a.row}.")

    def new_actu(self):
        self.current_row = None
        self.var_title.set("")
        self.txt_text.delete("1.0", "end")
        self.var_date.set("")
        self.var_active.set(True)
        self.var_isbn.set("")
        self.var_link.set("")
        self.var_image.set("")
        self.var_book_info.set("")
        self.tree.selection_remove(*self.tree.selection())
        self.var_status.set("Nouvelle actualité : remplissez le formulaire puis « Enregistrer ».")

    def toggle_selected(self):
        a = self._selected_actu()
        if a is None:
            return
        new_state = not a.is_active
        verb = "réactiver" if new_state else "désactiver"
        if not messagebox.askyesno("Confirmation",
                                   f"Voulez-vous {verb} « {a.title or '(sans titre)'} » ?"):
            return
        try:
            self.store.set_active(a.row, new_state)
            self.store.save_workbook()
        except WorkbookLockedError as e:
            messagebox.showerror("Classeur ouvert", str(e))
            return
        except ActuError as e:
            messagebox.showerror("Erreur", str(e))
            return
        self.refresh_list(select_row=a.row)
        self.var_status.set(f"Actualité {'réactivée' if new_state else 'désactivée'} et classeur enregistré.")

    # ------------------------------------------------------------------
    # Livre associé
    # ------------------------------------------------------------------

    def lookup_book(self):
        raw = self.var_isbn.get().strip()
        if not raw:
            messagebox.showinfo("ISBN", "Saisissez d'abord un ISBN à 13 chiffres.")
            return None
        i13, book = self.store.lookup_isbn(raw)
        if not i13:
            messagebox.showerror(
                "ISBN invalide",
                f"« {raw} » n'est pas un ISBN valide : il faut 13 chiffres\n"
                "(les espaces et tirets sont acceptés)."
            )
            return None
        self.var_isbn.set(i13)
        if book is None:
            messagebox.showwarning(
                "Livre introuvable",
                f"L'ISBN {i13} n'existe pas dans le catalogue (feuille Master_Site).\n"
                "Vérifiez le numéro, ou continuez si l'actualité ne concerne pas un livre du catalogue."
            )
            self.var_book_info.set("")
            return None
        info = f"Livre trouvé : {book.title}"
        if book.slug:
            info += f"\nSur le site, le titre de l'actualité renverra à sa fiche (livres/{book.slug}.html)."
        if book.cover_file:
            info += (f"\nSa couverture ({book.cover_file}) peut servir de visuel si vous le souhaitez : "
                     "bouton « Choisir la couverture comme visuel ».")
        self.var_book_info.set(info)
        return book

    def use_book_cover(self):
        """Action facultative : reprendre la couverture du livre associé comme visuel."""
        raw = self.var_isbn.get().strip()
        if not raw:
            messagebox.showinfo(
                "Couverture",
                "Cette action est facultative : elle reprend la couverture d'un livre du catalogue.\n"
                "Renseignez d'abord l'ISBN13 du livre associé."
            )
            return
        i13, book = self.store.lookup_isbn(raw)
        if not book:
            messagebox.showerror(
                "Livre introuvable",
                f"L'ISBN {raw} n'a pas été trouvé dans le catalogue :\n"
                "impossible d'en récupérer la couverture."
            )
            return
        if self.var_image.get() and self.var_image.get() != book.cover_file:
            if not messagebox.askyesno(
                    "Remplacer le visuel ?",
                    f"Un visuel est déjà choisi ({self.var_image.get()}).\n"
                    f"Le remplacer par la couverture {book.cover_file} ?"):
                return
        self._apply_cover(book.cover_file)

    def _apply_cover(self, cover_file: str):
        try:
            name = self.store.use_cover(cover_file, self._ask_conflict)
        except ActuError as e:
            messagebox.showerror("Couverture", str(e))
            return
        if name:
            self.var_image.set(name)
            self.var_status.set(f"Image : {name}")

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------

    def _ask_conflict(self, name: str) -> str:
        res = messagebox.askyesnocancel(
            "Fichier déjà présent",
            f"Une image nommée {name} existe déjà dans le dossier des actualités.\n\n"
            "Oui : remplacer le fichier existant\n"
            "Non : conserver le fichier existant\n"
            "Annuler : ne rien faire"
        )
        if res is None:
            return "cancel"
        return "replace" if res else "keep"

    def pick_image(self):
        path = filedialog.askopenfilename(
            title="Choisir une image d'actualité",
            filetypes=[("Images (jpg, png, webp)", "*.jpg *.jpeg *.png *.webp"),
                       ("Tous fichiers", "*.*")],
        )
        if not path:
            return
        try:
            name = self.store.import_image(Path(path), self._ask_conflict)
        except ActuError as e:
            messagebox.showerror("Image", str(e))
            return
        if name:
            self.var_image.set(name)
            self.var_status.set(f"Image copiée dans le dossier « actu » : {name}")

    # ------------------------------------------------------------------
    # Enregistrement
    # ------------------------------------------------------------------

    def _actu_from_form(self) -> Actu | None:
        a = Actu(row=self.current_row)
        a.title = self.var_title.get().strip()
        a.text = self.txt_text.get("1.0", "end-1c").strip()
        a.link = self.var_link.get().strip()
        a.image = self.var_image.get().strip()
        a.is_active = bool(self.var_active.get())

        raw_isbn = self.var_isbn.get().strip()
        if raw_isbn:
            i13, _ = self.store.lookup_isbn(raw_isbn)
            a.id13 = i13 or raw_isbn  # gardé brut pour que la validation signale l'erreur

        try:
            a.date = parse_date_fr(self.var_date.get())
        except ValueError as e:
            messagebox.showerror("Date", str(e))
            return None
        return a

    def save(self):
        a = self._actu_from_form()
        if a is None:
            return

        issues = self.store.validate(a)
        blocking = [i for i in issues if not i.confirmable]
        confirmable = [i for i in issues if i.confirmable]
        if blocking:
            messagebox.showerror("Impossible d'enregistrer", "\n\n".join(i.message for i in blocking))
            return
        for i in confirmable:
            if not messagebox.askyesno("Confirmation", i.message):
                return

        try:
            row = self.store.save_actu(a)
            self.store.save_workbook()
        except WorkbookLockedError as e:
            messagebox.showerror("Classeur ouvert", str(e))
            return
        except ActuError as e:
            messagebox.showerror("Erreur", str(e))
            return

        self.current_row = row
        self.refresh_list(select_row=row)
        self.var_status.set(f"Actualité enregistrée (ligne {row}). Classeur sauvegardé.")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    if not path:
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Choisir le classeur Excel du site",
            filetypes=[("Classeur Excel", "*.xlsx"), ("Tous fichiers", "*.*")],
        )
        root.destroy()
        if not path:
            return
    try:
        store = ActualitesStore(Path(path))
    except ActuError as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Classeur", str(e))
        root.destroy()
        return
    EditorApp(store).mainloop()


if __name__ == "__main__":
    main()
