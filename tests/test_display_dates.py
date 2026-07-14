from datetime import date, datetime

import pandas as pd

from cidre.build import _book_card_html
from cidre.data_models import SiteConfig
from cidre.utils import fmt_display_date


def test_fmt_display_date_supprime_toute_composante_horaire_textuelle_iso():
    assert fmt_display_date("2026-04-10") == "2026-04-10"
    assert fmt_display_date("2026-04-10 00:00") == "2026-04-10"
    assert fmt_display_date("2026-04-10 00:00:00") == "2026-04-10"
    assert fmt_display_date("2026-04-10T00:00") == "2026-04-10"
    assert fmt_display_date("2026-04-10T00:00:00") == "2026-04-10"
    assert fmt_display_date("2026-04-10T00:00:00Z") == "2026-04-10"
    assert fmt_display_date("2026-04-10 14:30") == "2026-04-10"
    assert fmt_display_date("2026-04-10 14:30:00") == "2026-04-10"
    assert fmt_display_date("2026-04-10T14:30:00") == "2026-04-10"
    assert fmt_display_date("Rendez-vous à 00:00") == "Rendez-vous à 00:00"


def test_fmt_display_date_supprime_toute_composante_horaire_des_objets():
    assert fmt_display_date(date(2026, 4, 10)) == "2026-04-10"
    assert fmt_display_date(datetime(2026, 4, 10, 0, 0)) == "2026-04-10"
    assert fmt_display_date(datetime(2026, 4, 10, 14, 30)) == "2026-04-10"
    assert fmt_display_date(pd.Timestamp(2026, 4, 10, 0, 0)) == "2026-04-10"
    assert fmt_display_date(pd.Timestamp(2026, 4, 10, 14, 30)) == "2026-04-10"


def test_rendu_carte_affiche_la_parution_sans_heure():
    card = _book_card_html(
        pd.Series({
            "slug": "livre-test",
            "titre_norm": "Livre test",
            "date_parution_norm": "2026-04-10 14:30:00",
        }),
        ".",
        SiteConfig(),
    )
    assert "Parution : 2026-04-10" in card
    assert "14:30" not in card
