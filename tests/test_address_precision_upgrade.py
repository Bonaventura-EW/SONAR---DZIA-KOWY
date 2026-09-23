"""Testy rotacji doprecyzowania adresu (bez live requestów).

Propagacja z SONAR-POKOJOWY (manifest 2026-09-07-address-precision-upgrade):
`known_offers` w otodom_scraper.py / adresowo_scraper.py zamraża
title/description/coords na zawsze po pierwszym pobraniu, więc doprecyzowanie
adresu wpisane przez ogłoszeniodawcę PO pierwszym skanie (np. dopisany numer
budynku) nigdy nie trafiało do bazy. `main._apply_rotation` usuwa z indeksu
`known_offers` budżet najdawniej czytanych ofert z nieprecyzyjnym markerem,
wymuszając ponowne pobranie strony szczegółów.

U brata rotacja żyje w scraper.py (jeden portal, jeden mechanizm inteligentnego
skanowania po cenie/tytule). U nas Otodom/Adresowo mają odrębne scrapery z
mechanizmem `known_offers` — rotacja wpięta jest więc w main.py (jedno miejsce
dla obu źródeł), a scrapery tylko niosą `details_fetched_at` przez cache.
"""

from datetime import datetime, timedelta, timezone

import pytz

from main import SonarDzialkowy, ROTATION_MIN_AGE_DAYS


def _sonar(offers):
    sonar = SonarDzialkowy.__new__(SonarDzialkowy)
    sonar.tz = pytz.timezone('Europe/Warsaw')
    sonar.database = {'offers': offers}
    return sonar


def _iso_days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _otodom_offer(offer_id, precision, fetched_days_ago=None):
    return {
        'id': offer_id,
        'source': 'otodom',
        'location': {'coords': {'lat': 51.25, 'lon': 22.55},
                     'coords_precision': precision},
        'description': 'opis',
        'plot_type': None,
        'details_fetched_at': (_iso_days_ago(fetched_days_ago)
                                if fetched_days_ago is not None else None),
    }


def test_apply_rotation_skips_precise_markers():
    sonar = _sonar([])
    known = {
        'a': {'coords_precision': 'exact', 'details_fetched_at': _iso_days_ago(100)},
        'b': {'coords_precision': 'street', 'details_fetched_at': _iso_days_ago(100)},
    }
    out = sonar._apply_rotation(dict(known), budget=10)
    assert set(out) == {'a', 'b'}  # nic do zyskania — nie ruszamy


def test_apply_rotation_respects_min_age():
    sonar = _sonar([])
    known = {
        'fresh': {'coords_precision': 'approx',
                  'details_fetched_at': _iso_days_ago(ROTATION_MIN_AGE_DAYS - 1)},
        'stale': {'coords_precision': 'approx',
                  'details_fetched_at': _iso_days_ago(ROTATION_MIN_AGE_DAYS + 1)},
    }
    out = sonar._apply_rotation(dict(known), budget=10)
    assert 'fresh' in out   # za świeże, jeszcze nie do rotacji
    assert 'stale' not in out  # usunięte z known → scraper je odświeży


def test_apply_rotation_oldest_first_within_budget():
    sonar = _sonar([])
    known = {
        f'o{i}': {'coords_precision': 'approx', 'details_fetched_at': _iso_days_ago(i)}
        for i in range(10, 16)  # wieki 10..15 dni, wszystkie >= MIN_AGE
    }
    out = sonar._apply_rotation(dict(known), budget=2)
    # dwie NAJSTARSZE (14, 15 dni) usunięte, reszta zostaje "znana"
    assert set(known) - set(out) == {'o14', 'o15'}


def test_apply_rotation_missing_timestamp_is_oldest():
    sonar = _sonar([])
    known = {
        'no_ts': {'coords_precision': 'approx', 'details_fetched_at': None},
        'old': {'coords_precision': 'approx', 'details_fetched_at': _iso_days_ago(30)},
    }
    out = sonar._apply_rotation(dict(known), budget=1)
    assert 'no_ts' not in out  # brak znacznika = potraktowany jako najstarszy
    assert 'old' in out


def test_known_otodom_offers_excludes_rotated():
    offers = [
        _otodom_offer('otodom:1', 'approx', fetched_days_ago=30),
        _otodom_offer('otodom:2', 'exact', fetched_days_ago=30),
    ]
    sonar = _sonar(offers)
    known = sonar._known_otodom_offers()
    assert 'otodom:2' in known       # precyzyjna — zostaje "znana"
    assert 'otodom:1' not in known   # approx + stara → wraca do pobierania


def test_update_existing_sets_details_fetched_at_only_when_present():
    sonar = SonarDzialkowy.__new__(SonarDzialkowy)
    sonar.tz = pytz.timezone('Europe/Warsaw')

    existing = {
        'id': 'otodom:1', 'url': 'https://x', 'title': 't',
        'price': {'current': 100, 'history': [100]},
        'location': {}, 'details_fetched_at': 'old-ts',
    }
    # oferta pominięta przez known_offers (skip branch) — details_fetched_at
    # jest niesione z cache, nie znika, ale też się nie zmienia bez powodu
    new_from_cache = {'url': 'https://x', 'title': 't', 'price': 100,
                       'location': {}, 'details_fetched_at': 'old-ts'}
    sonar._update_existing(existing, new_from_cache)
    assert existing['details_fetched_at'] == 'old-ts'

    # realne pobranie (rotacja albo nowa oferta) niesie świeży znacznik
    new_fetched = {'url': 'https://x', 'title': 't', 'price': 100,
                   'location': {}, 'details_fetched_at': 'fresh-ts'}
    sonar._update_existing(existing, new_fetched)
    assert existing['details_fetched_at'] == 'fresh-ts'

    # źródło bez fetch_details (OLX/agencje) nie niesie tego pola w ogóle —
    # stary znacznik zostaje nietknięty
    new_no_field = {'url': 'https://x', 'title': 't', 'price': 100, 'location': {}}
    sonar._update_existing(existing, new_no_field)
    assert existing['details_fetched_at'] == 'fresh-ts'


def test_otodom_scrape_known_skip_carries_details_fetched_at(monkeypatch):
    from otodom_scraper import OtodomDzialkiScraper

    scraper = OtodomDzialkiScraper(delay_range=(0, 0))
    listing_offer = {
        'id': 'otodom:1', 'source': 'otodom', 'url': 'https://x', 'title': 't',
        'price': 100, 'area_m2': 500, 'price_per_m2': 0.2, 'plot_type': None,
        'location': {'city': 'Lublin', 'district': None, 'street': None,
                     'coords': None, 'coords_precision': None},
        'description': '', 'is_private_owner': False, 'image': None,
        'created_at': None,
    }
    monkeypatch.setattr(scraper, '_scrape_listing', lambda max_pages: [listing_offer])

    known_offers = {'otodom:1': {
        'coords': {'lat': 51.2, 'lon': 22.5}, 'coords_precision': 'exact',
        'plot_type': 'budowlana', 'description': 'stary opis',
        'details_fetched_at': 'cached-ts',
    }}
    result = scraper.scrape(max_pages=1, known_offers=known_offers)
    assert result[0]['details_fetched_at'] == 'cached-ts'


def test_otodom_fetch_details_sets_timestamp(monkeypatch):
    import json as _json
    from otodom_scraper import OtodomDzialkiScraper

    next_data = {'props': {'pageProps': {'ad': {
        'location': {'coordinates': {'latitude': 51.25, 'longitude': 22.55},
                     'mapDetails': {'radius': 0}},
        'description': 'Pełny opis oferty', 'characteristics': [],
    }}}}
    html = f'<script id="__NEXT_DATA__">{_json.dumps(next_data)}</script>'

    scraper = OtodomDzialkiScraper(delay_range=(0, 0))
    monkeypatch.setattr(scraper, '_fetch', lambda url: html)
    offer = {'id': 'otodom:1', 'url': 'https://x', 'description': '',
              'location': {'coords': None, 'coords_precision': None}}
    before = datetime.now(timezone.utc)
    result = scraper.fetch_details(offer)
    assert result['details_fetched_at'] is not None
    fetched_at = datetime.fromisoformat(result['details_fetched_at'])
    assert fetched_at >= before


def test_adresowo_scrape_known_skip_carries_details_fetched_at(monkeypatch):
    from adresowo_scraper import AdresowoScraper

    scraper = AdresowoScraper(delay_range=(0, 0))
    monkeypatch.setattr(scraper, '_sleep', lambda: None)
    card_offer = {
        'id': 'adresowo:1', 'source': 'adresowo', 'url': 'https://x',
        'title': 'Działka na sprzedaż — Lublin', 'price': 100, 'area_m2': 500,
        'price_per_m2': 0.2, 'plot_type': 'inna',
        'location': {'city': 'Lublin', 'district': None, 'street': None,
                     'coords': None, 'coords_precision': None},
        'description': '', 'is_private_owner': False, 'image': None,
        'created_at': None,
    }
    monkeypatch.setattr(scraper, '_fetch', lambda url: '<html></html>')
    monkeypatch.setattr(scraper, '_parse_card', lambda link: card_offer)

    class _FakeSoup:
        def find_all(self, *a, **k):
            return [object()]  # jedna "oferta" na stronie 1

    monkeypatch.setattr('adresowo_scraper.BeautifulSoup', lambda html, parser: _FakeSoup())

    known_offers = {'adresowo:1': {
        'coords': None, 'coords_precision': None, 'street': None,
        'description': 'stary opis', 'title': 'stary tytuł', 'plot_type': 'inna',
        'image': None, 'details_fetched_at': 'cached-ts',
    }}
    result = scraper.scrape(max_pages=1, known_offers=known_offers)
    assert result[0]['details_fetched_at'] == 'cached-ts'


def test_adresowo_fetch_details_sets_timestamp(monkeypatch):
    from adresowo_scraper import AdresowoScraper

    html = ('<html><head><title>Działka Lublin, ul. Testowa - adresowo</title></head>'
            '<body>{"lat": 51.27884, "lon": 22.591202}</body></html>')
    scraper = AdresowoScraper(delay_range=(0, 0))
    monkeypatch.setattr(scraper, '_fetch', lambda url: html)
    offer = {'id': 'adresowo:1', 'url': 'https://x', 'title': 't',
              'description': '', 'plot_type': 'inna',
              'location': {'coords': None, 'coords_precision': None, 'street': None}}
    before = datetime.now(timezone.utc)
    result = scraper.fetch_details(offer)
    assert result['details_fetched_at'] is not None
    fetched_at = datetime.fromisoformat(result['details_fetched_at'])
    assert fetched_at >= before
