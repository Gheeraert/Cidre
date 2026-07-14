# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
# Module extrait de build_site.py (découpage sans changement fonctionnel).

from __future__ import annotations

import dataclasses
from typing import Any, Dict
from urllib.parse import unquote

import pandas as pd

from .utils import as_str, is_na, looks_urlencoded, norm_bool

# -------------------------
# Data models
# -------------------------

@dataclasses.dataclass
class SiteConfig:
    # Branding
    site_title: str = "Presses universitaires"
    site_subtitle: str = "Catalogue"
    site_url: str = ""
    site_description: str = ""
    social_image: str = ""
    accent_color: str = "#005a9c"
    header_bg: str = "#2e2a22"

    # Logos / favicon (fichiers copiés vers assets/)
    logo_left: str = ""  # ex: assets/logo.png
    logo_right: str = ""  # ex: assets/partner.png
    logo_left_link: str = ""
    logo_right_link: str = ""
    logo_height: int = 38
    favicon: str = ""  # ex: assets/favicon.ico

    # Contact / footer
    contact_email: str = ""
    footer_text: str = "Site généré automatiquement."
    footer_copyright: str = ""
    footer_conceptor: str = ""  # ex: "Conception : …"
    footer_legal: str = ""  # ex: "Mentions légales : …" ou URL
    footer_logo: str = ""  # ex: assets/logo-univ.png (copié dans assets/)
    footer_logo_alt: str = ""
    footer_logo_href: str = ""  # lien éventuel vers l’université

    # Excel settings
    books_sheet: str = ""  # name of catalogue sheet; if empty auto-detect
    pages_sheet: str = "PAGES"
    collections_sheet: str = "COLLECTIONS"
    revues_sheet: str = "REVUES"
    contacts_sheet: str = "CONTACTS"
    config_sheet: str = "CONFIG"

    # Home / Nouveautés
    home_feature_count: int = 12
    new_titles_count: int = 25
    new_months: int = 6

    # Display toggles
    show_price: bool = True
    show_availability: bool = True

    # Order button mode
    order_mode: str = "mailto"  # mailto | url | pdf
    order_pdf_filename: str = ""  # if pdf
    order_url_template: str = ""  # if url template, can use {id13}
    order_mail_subject: str = "Commande"
    order_mail_body: str = "Bonjour,\n\nJe souhaite commander : {title} ({id13}).\n\nMerci."

    # Menu - plusieurs actuellement inactifs mais utilisables
    menu_label_presentation: str = "Présentation"
    menu_label_soumettre: str = "Soumettre un manuscrit"
    menu_label_a_paraitre: str = "À paraître"
    menu_label_catalogue: str = "Catalogue"
    menu_label_revues: str = "Revues"
    menu_label_collections: str = "Collections"
    menu_label_open_access: str = "Open Access"
    menu_label_commandes: str = "Commandes/contacts"
    menu_label_actualites: str = "Actualités"

    # Réseaux / liens institutionnels (page Actualités)
    social_intro: str = "Suivez les PURH"
    social_1_name: str = ""
    social_1_url: str = ""
    social_1_icon: str = ""
    social_2_name: str = ""
    social_2_url: str = ""
    social_2_icon: str = ""
    social_3_name: str = ""
    social_3_url: str = ""
    social_3_icon: str = ""
    social_4_name: str = ""
    social_4_url: str = ""
    social_4_icon: str = ""
    social_5_name: str = ""
    social_5_url: str = ""
    social_5_icon: str = ""
    social_6_name: str = ""
    social_6_url: str = ""
    social_6_icon: str = ""

    # FTP publish (optionnel)
    ftp_host: str = ""
    ftp_user: str = ""
    ftp_password: str = ""
    ftp_remote_dir: str = ""  # ex: /www/site/
    ftp_port: int = 21
    ftp_tls: bool = False
    ftp_passive: bool = True
    ftp_clean: bool = False


def load_config(wb: pd.ExcelFile, sheet_name: str) -> SiteConfig:
    cfg = SiteConfig()
    if sheet_name not in wb.sheet_names:
        return cfg

    df = wb.parse(sheet_name=sheet_name)

    # accept columns: key/value or Clé/Valeur
    cols = [str(c).lower().strip() for c in df.columns]
    key_col = None
    val_col = None
    for i, c in enumerate(cols):
        if c in {"key", "cle", "clé"}:
            key_col = df.columns[i]
        if c in {"value", "valeur"}:
            val_col = df.columns[i]
    if key_col is None or val_col is None:
        if len(df.columns) >= 2:
            key_col, val_col = df.columns[0], df.columns[1]
        else:
            return cfg

    kv: Dict[str, Any] = {}
    for _, r in df.iterrows():
        k = r.get(key_col)
        v = r.get(val_col)
        k = as_str(k)
        if not k:
            continue
        kv[k] = "" if is_na(v) else v

    # Aliases (compat templates)
    # - priorité aux clés explicites "logo_file_left/right"
    # - compat pour les anciens noms de clés
    alias = {
        "brand_accent_color": "accent_color",
        "favicon_file": "favicon",
        "contact_email_default": "contact_email",
        "order_mode_default": "order_mode",
    }
    for k, v in list(kv.items()):
        if k in alias and alias[k] not in kv:
            kv[alias[k]] = v

    # Logos : priorité à logo_file_left/right, puis fallback à logo_file
    if as_str(kv.get("logo_file_left")):
        kv["logo_left"] = kv.get("logo_file_left")
    elif as_str(kv.get("logo_file")) and not as_str(kv.get("logo_left")):
        kv["logo_left"] = kv.get("logo_file")

    if as_str(kv.get("logo_file_right")):
        kv["logo_right"] = kv.get("logo_file_right")
    # Map keys to dataclass fields when possible
    for field in dataclasses.fields(cfg):
        if field.name not in kv:
            continue
        raw = kv[field.name]

        # bool
        if field.type == bool or str(field.type) in {"bool", "<class 'bool'>"}:
            setattr(cfg, field.name, norm_bool(raw))
            continue

        # int
        if field.type == int or str(field.type) in {"int", "<class 'int'>"}:
            try:
                setattr(cfg, field.name, int(float(raw)))
            except Exception:
                pass
            continue

        # str
        setattr(cfg, field.name, as_str(raw))

    # Unquote mail body if template stored URL-encoded
    if cfg.order_mail_body and looks_urlencoded(cfg.order_mail_body):
        try:
            cfg.order_mail_body = unquote(cfg.order_mail_body)
        except Exception:
            pass

    # Normalize logo paths: if value is just a filename -> assets/<filename>
    for attr in ("logo_left", "logo_right", "favicon", "footer_logo", "social_image"):
        val = getattr(cfg, attr)
        if val and "/" not in val and "\\" not in val:
            setattr(cfg, attr, f"assets/{val}")

    return cfg


