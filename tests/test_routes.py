import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cidre import routes
from cidre.validation import _published_pages


def test_book_slug_candidates():
    assert routes.book_slug_candidate("Mon Livre !", "Titre ignore", "9782877750001") == "mon-livre"
    assert routes.book_slug_origin("Mon Livre !", "9782877750001") == "explicit"
    assert routes.book_slug_candidate("", "Mon Livre", "9782877750001") == "mon-livre-9782877750001"
    assert routes.book_slug_origin("", "9782877750001") == "fallback_title_isbn"
    assert routes.book_slug_candidate("", "Mon Livre", "") == "mon-livre"
    assert routes.book_slug_origin("", "") == "fallback_title"


def test_public_paths_are_posix():
    assert routes.book_public_path("un-livre") == "livres/un-livre.html"
    assert routes.book_href("un-livre", ".") == "./livres/un-livre.html"
    assert routes.collection_public_path("une-collection") == "collections/une-collection.html"
    assert routes.collection_href("une-collection", rel_prefix="..") == "../collections/une-collection.html"
    assert routes.revue_public_path("une-revue") == "revues/une-revue.html"
    assert routes.revue_href("une-revue", rel_prefix="..") == "../revues/une-revue.html"


def test_collection_slug_rules():
    assert routes.collection_public_slug("Slug Public", "id-col") == "slug-public"
    assert routes.collection_public_slug("", "id-col") == "id-col"


def test_revue_slug_rules():
    assert routes.revue_public_slug("Slug Revue", "Titre", "jid") == "slug-revue"
    assert routes.revue_public_slug("", "Titre Revue", "jid") == "titre-revue"
    assert routes.revue_public_slug("", "", "jid") == "jid"
    assert routes.revue_public_slug("", "", "") == "revue"


def test_pages_publiees_et_exclusions():
    pages = pd.DataFrame([
        {"slug": "presentation", "is_published": 1},
        {"slug": "brouillon", "is_published": 0},
        {"slug": "actualites", "is_published": 1},
        {"slug": "actus", "is_published": 1},
    ])
    df = _published_pages(pages)
    assert df["_validation_slug"].tolist() == ["presentation"]
    assert routes.editorial_page_public_path("presentation") == "presentation.html"


def test_actualite_anchor_candidate_fallback():
    assert routes.actualite_anchor_candidate("!!!") == "actu"
    assert routes.actualite_anchor_candidate("") == "actu"
