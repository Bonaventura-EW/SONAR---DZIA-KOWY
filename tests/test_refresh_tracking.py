"""Testy śledzenia daty ostatniego odświeżenia (podbicia) oferty OLX.

Pokrywa całą ścieżkę bez ruszania sieci:
  olx_scraper.normalize_ad  → last_refresh_time z __PRERENDERED_STATE__
  main._track_refresh       → historia dni (max 1/dzień, jak _track_promoted)

Propagacja z SONAR-POKOJOWY (manifest 2026-09-07-refresh-from-listing-card).
U brata sygnał trzeba parsować z tekstu karty HTML ("Odświeżono dzisiaj o
HH:MM" / "Odświeżono dnia D miesiąca") i rozróżniać dokładną godzinę od samej
daty; u nas OLX niesie gotowy, precyzyjny znacznik ISO wprost w polu
`lastRefreshTime` __PRERENDERED_STATE__ (zweryfikowane na żywym skanie
2026-09-29: pokrycie 100%, nie tylko oferty firmowe), więc reguła „nie
nadpisuj dokładnego przybliżeniem" jest tu zbędna.
"""

from olx_scraper import normalize_ad


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


def test_normalize_ad_sets_last_refresh_time():
    offer = normalize_ad(_ad(lastRefreshTime='2026-09-29T12:00:34+02:00'))
    assert offer['last_refresh_time'] == '2026-09-29T12:00:34+02:00'


def test_normalize_ad_last_refresh_time_missing():
    assert normalize_ad(_ad())['last_refresh_time'] is None


def test_track_refresh_dedupes_per_day():
    from main import SonarDzialkowy
    sonar = SonarDzialkowy.__new__(SonarDzialkowy)

    offer = {}
    sonar._track_refresh(offer, '2026-09-29T08:00:00+02:00')
    # drugi skan tego samego dnia, ogłoszenie podbite ponownie później
    sonar._track_refresh(offer, '2026-09-29T18:00:00+02:00')
    assert offer['last_refresh_time'] == '2026-09-29T18:00:00+02:00'  # najświeższy znacznik
    assert offer['refresh_dates'] == ['2026-09-29']  # max 1 wpis/dzień
    assert offer['refresh_count'] == 1

    # kolejny dzień, nowe odświeżenie
    sonar._track_refresh(offer, '2026-09-30T09:00:00+02:00')
    assert offer['refresh_dates'] == ['2026-09-29', '2026-09-30']
    assert offer['refresh_count'] == 2


def test_track_refresh_noop_without_new_event():
    from main import SonarDzialkowy
    sonar = SonarDzialkowy.__new__(SonarDzialkowy)

    offer = {}
    sonar._track_refresh(offer, '2026-09-29T08:00:00+02:00')
    # kolejny skan bez nowego odświeżenia (ten sam znacznik z OLX)
    sonar._track_refresh(offer, '2026-09-29T08:00:00+02:00')
    assert offer['refresh_dates'] == ['2026-09-29']
    assert offer['refresh_count'] == 1


def test_track_refresh_non_olx_noop():
    from main import SonarDzialkowy
    sonar = SonarDzialkowy.__new__(SonarDzialkowy)

    offer = {}
    sonar._track_refresh(offer, None)
    assert 'last_refresh_time' not in offer
    assert 'refresh_dates' not in offer
