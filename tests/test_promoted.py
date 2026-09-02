"""Testy detekcji PŁATNIE WYRÓŻNIONYCH ofert OLX (metryka „promoted").

Pokrywa całą ścieżkę bez ruszania sieci:
  olx_scraper._is_promoted / normalize_ad  → flaga z __PRERENDERED_STATE__
  main._track_promoted                      → historia dni (max 1/dzień)
  map_generator.build_promoted              → dzienny szereg + bieżący udział

Propagacja z SONAR-POKOJOWY (manifest 2026-08-26-promoted-listings-metric).
U brata sygnał czytany z href-a karty HTML; u nas wprost z JSON (searchReason).
"""

from datetime import datetime

import pytz

from olx_scraper import _is_promoted, normalize_ad
from map_generator import build_promoted


BASE_AD = {
    'url': 'https://www.olx.pl/d/oferta/dzialka-CID3-ID1abcDE.html?reason=x',
    'title': 'Działka budowlana Lublin',
    'isBusiness': True,
    'price': {'regularPrice': {'value': 300000, 'currencyCode': 'PLN'}},
    'location': {'cityName': 'Lublin', 'cityNormalizedName': 'lublin'},
    'params': [{'key': 'm', 'normalizedValue': '1000'}],
}


def _ad(**over):
    ad = dict(BASE_AD)
    ad.update(over)
    return ad


def test_is_promoted_search_reason():
    assert _is_promoted({'searchReason': 'promoted'}) is True
    assert _is_promoted({'searchReason': 'organic'}) is False
    # searchReason ma pierwszeństwo nawet przy niespójnym isPromoted
    assert _is_promoted({'searchReason': 'organic', 'isPromoted': True}) is False


def test_is_promoted_fallback_is_promoted():
    # brak pola searchReason → fallback na booleana isPromoted
    assert _is_promoted({'isPromoted': True}) is True
    assert _is_promoted({'isPromoted': False}) is False
    assert _is_promoted({}) is False


def test_normalize_ad_sets_promoted():
    assert normalize_ad(_ad(searchReason='promoted'))['promoted'] is True
    assert normalize_ad(_ad(searchReason='organic'))['promoted'] is False
    # oferta bez atrybucji, ale z booleanem promocji
    assert normalize_ad(_ad(isPromoted=True))['promoted'] is True


def test_track_promoted_dedupes_per_day():
    from main import SonarDzialkowy
    sonar = SonarDzialkowy.__new__(SonarDzialkowy)
    sonar.tz = pytz.timezone('Europe/Warsaw')
    today = datetime.now(sonar.tz).strftime('%Y-%m-%d')

    offer = {}
    sonar._track_promoted(offer, True)
    sonar._track_promoted(offer, True)  # drugi skan tego samego dnia
    assert offer['promoted'] is True
    assert offer['promoted_dates'] == [today]  # max 1 wpis/dzień
    assert offer['promoted_count'] == 1

    # zniknięcie wyróżnienia gasi flagę, ale historia dni zostaje
    sonar._track_promoted(offer, False)
    assert offer['promoted'] is False
    assert offer['promoted_dates'] == [today]


def test_track_promoted_non_olx_noop():
    from main import SonarDzialkowy
    sonar = SonarDzialkowy.__new__(SonarDzialkowy)
    sonar.tz = pytz.timezone('Europe/Warsaw')
    offer = {}
    sonar._track_promoted(offer, False)
    assert offer['promoted'] is False
    assert offer['promoted_dates'] == []
    assert offer['promoted_count'] == 0


def test_build_promoted_series_and_share():
    offers = [
        # aktywna OLX wyróżniona dziś + wczoraj
        {'source': 'olx', 'active': True, 'promoted': True,
         'promoted_dates': ['2026-08-30', '2026-08-31']},
        # aktywna OLX niewyróżniona
        {'source': 'olx', 'active': True, 'promoted': False, 'promoted_dates': []},
        # nieaktywna OLX, historycznie wyróżniona (liczy się do szeregu, nie do „teraz")
        {'source': 'olx', 'active': False, 'promoted': False,
         'promoted_dates': ['2026-08-30']},
        # Otodom nie niesie sygnału
        {'source': 'otodom', 'active': True, 'promoted': False},
    ]
    scan_days = {'2026-08-30', '2026-08-31', '2026-09-01'}
    out = build_promoted(offers, scan_days)

    daily = dict(out['daily'])
    assert daily['2026-08-30'] == 2   # dwie oferty wyróżnione 30.08
    assert daily['2026-08-31'] == 1
    assert daily['2026-09-01'] == 0   # skan był, brak wyróżnień → realne zero
    # bieżący udział: 1 wyróżniona z 2 aktywnych ofert OLX
    assert out['current'] == 1
    assert out['current_share'] == 50.0
    assert out['start'] == '2026-08-30'


def test_build_promoted_marks_unscanned_days_as_gap():
    offers = [{'source': 'olx', 'active': False, 'promoted': False,
               'promoted_dates': ['2026-08-30', '2026-09-01']}]
    # brak 2026-08-31 w dniach skanu → luka (None), nie zero
    out = build_promoted(offers, {'2026-08-30', '2026-09-01'})
    daily = dict(out['daily'])
    assert daily['2026-08-30'] == 1
    assert daily['2026-08-31'] is None
    assert daily['2026-09-01'] == 1


def test_build_promoted_none_without_history():
    offers = [{'source': 'olx', 'active': True, 'promoted': False, 'promoted_dates': []}]
    assert build_promoted(offers, set()) is None
