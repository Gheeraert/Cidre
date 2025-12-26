#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Export ONIX 3.0 (reference tags) depuis un Excel PURH.

Objectifs :
- Produire un ONIX conforme au schéma ONIX 3.0 (XSD reference).
- Rester robuste face aux masters incomplets (prix manquants, mesures vides, etc.).

Notes de conformité (points souvent bloquants) :
- DescriptiveDetail : ordre strict (mesures AVANT titres / contributeurs).
- Authorship : au moins un <Contributor> OU <NoContributor/>.
- SupplyDetail : <Supplier> attendu avant <ProductAvailability>.
- SupplyDetail : un item doit être "priced" (<Price>) OU "unpriced" (<UnpricedItemType>).
- Price : si <Tax> présent, il doit être placé AVANT <CurrencyCode> et contenir
  soit <TaxAmount>, soit <TaxRatePercent> (cf. XSD).
- SupportingResource/ResourceLink : URI sans espaces.

© 2025 Tony Gheeraert - Licence MIT (voir LICENSE)
"""

from __future__ import annotations

import math
import re
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from xml.etree import ElementTree as ET


NS = "http://ns.editeur.org/onix/3.0/reference"
ET.register_namespace("", NS)


def q(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def is_nan(x: Any) -> bool:
    return isinstance(x, float) and math.isnan(x)


def truthy(x: Any) -> bool:
    if x is None:
        return False
    if isinstance(x, (int, float)):
        return x != 0 and not (isinstance(x, float) and math.isnan(x))
    s = str(x).strip().lower()
    return s in {"1", "true", "yes", "y", "vrai", "oui", "x"}


def clean_text(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def isbn13_digits(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()

    # scientific notation
    if "e+" in s.lower():
        try:
            s = str(int(float(s)))
        except Exception:
            pass

    # trailing .0
    if s.endswith(".0"):
        s = s[:-2]

    s = re.sub(r"\D", "", s)
    return s if len(s) == 13 else None


def date_to_yyyymmdd(x: Any) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, dt.datetime):
        return x.strftime("%Y%m%d")
    if isinstance(x, dt.date):
        return x.strftime("%Y%m%d")
    s = str(x).strip()
    if not s or s.lower() == "nan":
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y%m%d"):
        try:
            return dt.datetime.strptime(s, fmt).strftime("%Y%m%d")
        except Exception:
            pass
    try:
        ts = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.strftime("%Y%m%d")
    except Exception:
        return None


def add_text(parent: ET.Element, tag: str, text: Any) -> Optional[ET.Element]:
    t = clean_text(text)
    if t is None:
        return None
    el = ET.SubElement(parent, q(tag))
    el.text = t
    return el


def split_codes(s: Any) -> List[str]:
    s = clean_text(s)
    if not s:
        return []
    parts = re.split(r"[;,]\s*", s)
    return [p.strip() for p in parts if p.strip()]


def parse_contributors(raw: Any) -> List[Dict[str, Any]]:
    """Format attendu :

    "Atherton, Stan, B01; Leclaire, Jacques, B01" -> PersonNameInverted + ContributorRole(s)
    """
    raw = clean_text(raw)
    if not raw:
        return []
    items = [i.strip() for i in raw.split(";") if i.strip()]
    out: List[Dict[str, Any]] = []
    for it in items:
        bits = [b.strip() for b in it.split(",")]
        role = None
        if len(bits) >= 3:
            role = bits[-1].strip()
            name_inverted = ", ".join(bits[:-1]).strip()
        else:
            name_inverted = it.strip()
        roles = [r.strip() for r in re.split(r"[+/ ]+", role or "") if r.strip()] or ["A01"]
        out.append({"name_inverted": name_inverted, "roles": roles})
    return out


def availability_to_code(label: Any) -> str:
    """Mapping “humain” -> ONIX List 65 (simple)."""
    s = (clean_text(label) or "").lower()

    if not s:
        return "20"  # Available
    if "para" in s:
        return "10"  # Not yet available
    if "stock" in s:
        return "21"  # In stock
    if "commande" in s:
        return "22"  # To order
    if "pod" in s or "impression" in s:
        return "23"  # POD
    if "épuis" in s or "epuis" in s or "plus fourni" in s:
        return "43"  # No longer supplied by supplier
    if "retir" in s:
        return "46"  # Withdrawn
    if "indis" in s:
        return "40"  # Not available (unspecified)

    return "40"


def indent(elem: ET.Element, level: int = 0) -> None:
    i = "\n" + level * "  "
    if len(elem):
        if not (elem.text or "").strip():
            elem.text = i + "  "
        for e in elem:
            indent(e, level + 1)
        if not (e.tail or "").strip():
            e.tail = i
    if level and not (elem.tail or "").strip():
        elem.tail = i


def read_config(excel_path: str, sheet: str = "CONFIG") -> Dict[str, Any]:
    try:
        cfg_df = pd.read_excel(excel_path, sheet_name=sheet)
    except Exception:
        return {}

    cols = [str(c).strip().lower() for c in cfg_df.columns]

    key_col = None
    val_col = None
    for i, c in enumerate(cols):
        if c in {"key", "cle", "clé"}:
            key_col = cfg_df.columns[i]
        if c in {"value", "valeur"}:
            val_col = cfg_df.columns[i]

    # fallback : 2 premières colonnes
    if key_col is None or val_col is None:
        if len(cfg_df.columns) >= 2:
            key_col, val_col = cfg_df.columns[0], cfg_df.columns[1]
        else:
            return {}

    cfg: Dict[str, Any] = {}
    for _, r in cfg_df.iterrows():
        k = clean_text(r.get(key_col))
        if not k:
            continue
        cfg[k] = r.get(val_col)
    return cfg


def export_onix_from_excel(
    excel_path: str,
    out_xml_path: str,
    sheet_master: str = "Master_Site",
    strict: bool = False,
    report_csv_path: Optional[str] = None,
) -> Tuple[str, List[Tuple[int, str, str, str]]]:
    cfg = read_config(excel_path)
    df = pd.read_excel(excel_path, sheet_name=sheet_master)

    # Defaults (depuis CONFIG)
    release = str(clean_text(cfg.get("onix_release")) or "3.0")
    sender_name = clean_text(cfg.get("onix_sender_name")) or "Publisher"
    publisher_name = clean_text(cfg.get("onix_publisher_name")) or sender_name
    imprint_name = clean_text(cfg.get("onix_imprint_name")) or publisher_name
    lang = clean_text(cfg.get("onix_default_language_of_text")) or "fre"
    currency = clean_text(cfg.get("onix_default_currency")) or "EUR"
    price_type = clean_text(cfg.get("onix_default_price_type")) or "04"  # FRP including tax

    # TVA : si non renseignée, on OMIT le bloc <Tax> (et on reste conforme XSD)
    tax_type = clean_text(cfg.get("onix_default_tax_type")) or "01"
    tax_rate_code = clean_text(cfg.get("onix_default_tax_rate_code")) or "R"
    tax_rate_percent = cfg.get("onix_default_tax_rate_percent")

    market_countries = clean_text(cfg.get("onix_default_market_countries_included")) or "FR"
    country_pub = clean_text(cfg.get("onix_country_of_publication")) or "FR"

    # UnpricedItemType par défaut : 02 = "price to be announced" (honête si prix manquant)
    unpriced_default = clean_text(cfg.get("onix_default_unpriced_item_type")) or "02"

    root = ET.Element(q("ONIXMessage"), {"release": release})

    header = ET.SubElement(root, q("Header"))
    sender = ET.SubElement(header, q("Sender"))
    add_text(sender, "SenderName", sender_name)
    add_text(header, "SentDateTime", dt.datetime.now().strftime("%Y%m%dT%H%M"))

    errors: List[Tuple[int, str, str, str]] = []

    for idx, row in df.iterrows():
        # activation
        active_raw = row.get("active_onix")
        if clean_text(active_raw) is None:
            active_raw = row.get("active_site")
        if clean_text(active_raw) is None:
            active_raw = True  # défaut si rien n’est renseigné

        if not truthy(active_raw):
            continue

        isbn = isbn13_digits(row.get("id13"))
        title = clean_text(row.get("titre_norm"))

        if not isbn or not title:
            errors.append((idx, isbn or "", title or "", "missing id13/title"))
            if strict:
                continue
            else:
                continue

        prod = ET.SubElement(root, q("Product"))
        add_text(prod, "RecordReference", isbn)
        add_text(prod, "NotificationType", "03")  # update

        pid = ET.SubElement(prod, q("ProductIdentifier"))
        add_text(pid, "ProductIDType", "15")  # ISBN-13
        add_text(pid, "IDValue", isbn)

        # ---------------------
        # DescriptiveDetail (ordre XSD!)
        # ---------------------
        desc = ET.SubElement(prod, q("DescriptiveDetail"))
        add_text(desc, "ProductComposition", "00")
        add_text(desc, "ProductForm", clean_text(row.get("Code support")) or "BC")

        pfd = clean_text(row.get("Product form detail"))
        if pfd:
            for code in split_codes(pfd):
                add_text(desc, "ProductFormDetail", code)

        # Mesures (à ce stade : AVANT les titres / contributeurs)
        def add_measure(mtype: str, val: Any, unit: str) -> None:
            if val is None or is_nan(val):
                return
            try:
                v = float(val)
            except Exception:
                return
            if v <= 0:
                return
            m = ET.SubElement(desc, q("Measure"))
            add_text(m, "MeasureType", mtype)
            txt = str(int(v)) if v.is_integer() else str(v).rstrip("0").rstrip(".")
            add_text(m, "Measurement", txt)
            add_text(m, "MeasureUnitCode", unit)

        # vos valeurs sont en cm / gr
        add_measure("02", row.get("Largeur"), "cm")
        add_measure("01", row.get("Hauteur"), "cm")
        add_measure("03", row.get("Epaisseur"), "cm")
        add_measure("08", row.get("Poids"), "gr")

        # Titre
        td = ET.SubElement(desc, q("TitleDetail"))
        add_text(td, "TitleType", "01")
        te = ET.SubElement(td, q("TitleElement"))
        add_text(te, "TitleElementLevel", "01")
        add_text(te, "TitleText", title)
        add_text(te, "Subtitle", clean_text(row.get("sous_titre_norm")))

        # Contributeurs : priorité à contributeurs_onix, sinon agrégation
        contribs: List[Dict[str, Any]] = []
        if clean_text(row.get("contributeurs_onix")):
            contribs = parse_contributors(row.get("contributeurs_onix"))
        else:
            for col in ("auteurs_onix", "direction_onix", "traduction_onix", "compilation_onix"):
                if clean_text(row.get(col)):
                    contribs.extend(parse_contributors(row.get(col)))

        if contribs:
            for seq, c in enumerate(contribs, start=1):
                ce = ET.SubElement(desc, q("Contributor"))
                add_text(ce, "SequenceNumber", str(seq))
                for rcode in c["roles"]:
                    add_text(ce, "ContributorRole", rcode)
                add_text(ce, "PersonNameInverted", c["name_inverted"])
        else:
            # Conformité XSD : pas de contributeurs -> expliciter
            ET.SubElement(desc, q("NoContributor"))

        # Langue
        lg = ET.SubElement(desc, q("Language"))
        add_text(lg, "LanguageRole", "01")
        add_text(lg, "LanguageCode", lang)

        # Pages
        pages = row.get("Nombre de pages (pages totales imprimées)")
        if pages is not None and not is_nan(pages):
            try:
                pages_int = int(float(pages))
                if pages_int > 0:
                    ext = ET.SubElement(desc, q("Extent"))
                    add_text(ext, "ExtentType", "00")
                    add_text(ext, "ExtentValue", str(pages_int))
                    add_text(ext, "ExtentUnit", "03")  # pages
            except Exception:
                pass

        # Sujets (Thema / CLIL / BISAC) + MainSubject sur le 1er trouvé
        subjects: List[Tuple[str, str]] = []
        if clean_text(row.get("Sujet THEMA principal")):
            subjects.append(("93", clean_text(row.get("Sujet THEMA principal"))))
        if clean_text(row.get("Sujet CLIL principal")):
            subjects.append(("29", clean_text(row.get("Sujet CLIL principal"))))
        if clean_text(row.get("Sujet BISAC principal")):
            subjects.append(("10", clean_text(row.get("Sujet BISAC principal"))))

        for i, (scheme, code) in enumerate(subjects):
            se = ET.SubElement(desc, q("Subject"))
            if i == 0:
                ET.SubElement(se, q("MainSubject"))
            add_text(se, "SubjectSchemeIdentifier", scheme)
            add_text(se, "SubjectCode", code)

        # ---------------------
        # CollateralDetail
        # ---------------------
        coll = ET.SubElement(prod, q("CollateralDetail"))

        def add_textcontent(ttype: str, txt: Any) -> None:
            t = clean_text(txt)
            if not t:
                return
            tc = ET.SubElement(coll, q("TextContent"))
            add_text(tc, "TextType", ttype)       # 02/03/04
            add_text(tc, "ContentAudience", "00")
            add_text(tc, "Text", t)

        add_textcontent("02", row.get("Description courte"))
        add_textcontent("03", row.get("Description longue"))
        add_textcontent("04", row.get("Table des matières"))

        cover_url = clean_text(row.get("URL image de couverture"))
        if cover_url:
            ok = cover_url.startswith(("http://", "https://")) and (" " not in cover_url)
            if ok:
                sr = ET.SubElement(coll, q("SupportingResource"))
                add_text(sr, "ResourceContentType", "01")  # front cover
                add_text(sr, "ContentAudience", "00")
                add_text(sr, "ResourceMode", "03")         # image
                rv = ET.SubElement(sr, q("ResourceVersion"))
                add_text(rv, "ResourceForm", "02")         # downloadable file
                add_text(rv, "ResourceLink", cover_url)
            else:
                errors.append((idx, isbn, title, f"invalid cover URL (skip): {cover_url}"))

        # ---------------------
        # PublishingDetail
        # ---------------------
        pubd = ET.SubElement(prod, q("PublishingDetail"))
        impr = ET.SubElement(pubd, q("Imprint"))
        add_text(impr, "ImprintName", imprint_name)

        pub = ET.SubElement(pubd, q("Publisher"))
        add_text(pub, "PublishingRole", "01")
        add_text(pub, "PublisherName", publisher_name)

        add_text(pubd, "CountryOfPublication", country_pub)

        pub_date = date_to_yyyymmdd(row.get("date_parution_norm"))
        if pub_date:
            pdx = ET.SubElement(pubd, q("PublishingDate"))
            add_text(pdx, "PublishingDateRole", "01")
            add_text(pdx, "Date", pub_date)

        # ---------------------
        # ProductSupply
        # ---------------------
        ps = ET.SubElement(prod, q("ProductSupply"))
        market = ET.SubElement(ps, q("Market"))
        terr = ET.SubElement(market, q("Territory"))
        add_text(terr, "CountriesIncluded", market_countries)

        sd = ET.SubElement(ps, q("SupplyDetail"))

        # Supplier attendu AVANT ProductAvailability
        sup = ET.SubElement(sd, q("Supplier"))
        add_text(sup, "SupplierRole", "09")
        add_text(sup, "SupplierName", publisher_name)

        avail_raw = row.get("availability")
        if clean_text(avail_raw) is None:
            avail_raw = row.get("availability_label")
        avail_code = availability_to_code(avail_raw)
        add_text(sd, "ProductAvailability", avail_code)

        # si “pas encore dispo” et date connue -> SupplyDateRole 08
        # -------------------------
        # Prix : Price (si valide) sinon QA (et éventuellement UnpricedItemType)
        # -------------------------
        # -------------------------
        # Prix : Price OU UnpricedItemType (ne bloque pas l'export)
        # -------------------------
        price_val = row.get("price")
        if price_val is None or (isinstance(price_val, float) and math.isnan(price_val)):
            price_val = row.get("prix_ttc")  # compat anciens masters

        amt = None
        if price_val is not None and not (isinstance(price_val, float) and math.isnan(price_val)):
            try:
                s = str(price_val).strip().replace("\u00a0", " ").replace(" ", "").replace(",", ".")
                amt = float(s)
                if math.isnan(amt) or amt <= 0:
                    amt = None
            except Exception:
                amt = None

        if amt is None:
            # 1) ONIX toujours valide : on marque “prix à venir”
            add_text(sd, "UnpricedItemType", "02")  # 02 = price to be announced

            # 2) QA : on prévient sans bloquer
            errors.append((idx, isbn, title, "WARN: missing/invalid price -> UnpricedItemType=02"))
        else:
            pe = ET.SubElement(sd, q("Price"))
            add_text(pe, "PriceType", price_type)
            add_text(pe, "PriceAmount", f"{amt:.2f}".rstrip("0").rstrip("."))

            # Tax optionnel : si présent, XSD attend TaxAmount OU TaxRatePercent
            if tax_rate_percent is not None and not is_nan(tax_rate_percent):
                tax = ET.SubElement(pe, q("Tax"))
                add_text(tax, "TaxType", tax_type)
                add_text(tax, "TaxRateCode", tax_rate_code)
                add_text(tax, "TaxRatePercent", str(tax_rate_percent))

            # CurrencyCode après Tax
            add_text(pe, "CurrencyCode", currency)

    indent(root)
    ET.ElementTree(root).write(out_xml_path, encoding="utf-8", xml_declaration=True)

    if report_csv_path:
        pd.DataFrame(errors, columns=["row_index", "isbn13", "title", "issue"]).to_csv(report_csv_path, index=False)

    return out_xml_path, errors
