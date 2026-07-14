# Générateur de site statique de maison d'édition scientifique et / ou indépendante
# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
# Crédits : PURH + Chaire d'excellence édition numérique de l'université de Rouen
# build_site = fichier principal du projet
#
# !/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Générateur statique : Excel -> site HTML (sans backend)
- Lit : CONFIG, PAGES, COLLECTIONS, REVUES, CONTACTS + un onglet catalogue
- Génère : index.html, catalogue.html, nouveautes.html, a-paraitre.html,
           collections/, revues/, pages statiques et assets/ dans le dossier de sortie choisi
- Catalogue HTML autonome ; recherche et filtres (collection / format / année)
  activés progressivement côté navigateur

Usage:
  python build_site.py --excel gabarit/purh_site_excel_gabarit.xlsx --out site-sortie --covers-dir covers --assets-dir assets-source
  python build_site.py --excel gabarit/purh_site_excel_gabarit.xlsx --out site-sortie --publish-ftp
  (--tableur est accepté comme ancien alias de --excel)

Notes:
- Les couvertures (images) sont attendues dans --covers-dir et copiées dans covers/
- Les assets déclarés dans CONFIG (logos, favicon, PDF bon de commande) sont copiés automatiquement vers assets/
- Le nom de l’onglet catalogue peut être donné par CONFIG.books_sheet (sinon auto-détection)
"""

# Ce fichier est désormais une façade : le code vit dans le paquet cidre/
# (découpage de l'ancien build_site.py monolithique, sans changement
# fonctionnel). Toutes les fonctions et constantes historiques restent
# importables depuis build_site, et `python build_site.py` fonctionne
# comme avant.

from cidre.utils import (  # noqa: F401
    md,
    render_contacts_block,
    ALLOWED_COVER_EXTS,
    AVAILABLE_COVERS,
    compute_available_covers,
    is_na,
    as_str,
    OOXML_CR_RE,
    BLOCK_TAG_TRANSITION_RE,
    normalize_excel_text,
    normalize_editorial_columns,
    fmt_display_date,
    parse_pub_date,
    months_ago,
    pretty_person_name,
    format_credit_line,
    clean_json_value,
    e,
    MD_LINK_RE,
    normalize_external_url,
    _href_with_rel,
    footer_rich,
    to_float,
    fmt_eur,
    fmt_cm_guess,
    fmt_int,
    slugify,
    norm_bool,
    normalize_id13,
    parse_year,
    md_to_html,
    TAG_STRIP_RE,
    sanitize_html_fragment,
    _ACTU_A_OPEN_RE,
    _ACTU_SPAN_OPEN_RE,
    _ACTU_HREF_RE,
    _ACTU_CLASS_RE,
    sanitize_actu_html,
    html_to_text,
    toc_to_html,
    ensure_unique_slug,
    looks_urlencoded,
    write_file,
    resolve_asset_source,
)
from cidre.default_assets import (  # noqa: F401
    DEFAULT_CSS,
    CARD_PAGE_SIZE,
    DEFAULT_JS,
    PROGRESSIVE_CARDS_JS,
    NEWS_CAROUSEL_JS,
    LIGHTBOX_HTML,
)
from cidre.data_models import (  # noqa: F401
    SiteConfig,
    load_config,
)
from cidre.html_templates import (  # noqa: F401
    page_shell,
    order_pdf_rel,
    book_order_block,
    book_retailers_block,
)
from cidre.excel_data import (  # noqa: F401
    detect_books_sheet,
    load_pages,
    load_collections,
    detect_revues_sheet,
    load_revues,
    build_revue_slug_map,
    build_collection_slug_map,
    load_contacts,
    detect_actualites_sheet,
    load_actualites,
    resolve_actu_image_source,
    copy_actualites_images,
    build_actualites_json,
    get_social_links,
    resolve_social_icon_source,
    find_social_icon_public_path,
    render_social_strip,
    build_actualites_page,
    load_books,
)
from cidre.build import (  # noqa: F401
    copy_covers,
    copy_declared_assets,
    build_catalogue_json,
    _book_card_html,
    _progressive_cards_html,
    build_home,
    build_catalogue_page,
    build_new_titles,
    build_upcoming_page,
    build_book_pages,
    build_collections,
    build_revues,
    build_contacts,
    build_pages,
    build_validation_report,
)
from cidre.validation import (  # noqa: F401
    ValidationIssue,
    ValidationReport,
    ValidationBlockingError,
    ValidationAlertError,
    format_validation_summary,
    validate_site_data,
    write_validation_csv,
)
from cidre.ftp_publish import (  # noqa: F401
    publish_ftp,
)
from cidre.orchestrator import (  # noqa: F401
    AssetSourceError,
    build_site,
    copy_assets_tree,
    ignored_reserved_asset_json,
    make_arg_parser,
    main,
    validate_assets_source,
)


if __name__ == "__main__":
    main()
