"""Testy szeregów czasowych rynku (Indeks podaży + przepływy).

Pokrywa bez ruszania sieci i bez dotykania prawdziwej bazy:
  index_history.record / daily_series / backfill_from_scan_history
  trend_generator.collect_dates    → listy dat + stare pola pojedyncze
  trend_generator.build_series     → mierzony Indeks, luka w dniu bez skanu
  trend_generator.build_outflow    → dzienny odpływ + średnia 7 dni
  trend_generator.build_inflow     → nowe / reaktywacje / suma
  trend_generator.build_bands      → suma pasm == Indeks
  trend_generator.compute_deltas   → 1D/1M, brak danych → None

Wzorowane na trend.html z SONAR-POKOJOWY (patrz .propagation/changes).
"""

import json
from datetime import date

import pytest

import index_history
import trend_generator as tg


def _ms(y, m, d):
    return tg._day_ms(date(y, m, d))


@pytest.fixture
def repo(tmp_path):
    """Minimalne repo na dysku: data/ + docs/, bez ani jednego prawdziwego pliku."""
    (tmp_path / 'data').mkdir()
    (tmp_path / 'docs').mkdir()
    return tmp_path


def _write_scan_history(repo, scans):
    (repo / 'data' / 'scan_history.json').write_text(
        json.dumps({'scans': scans}), encoding='utf-8')


# --- index_history -----------------------------------------------------------

def test_record_bierze_maksimum_z_dnia(repo):
    """Skan częściowy (blokada portalu) nie może obniżyć zapisanego stanu dnia."""
    index_history.record(480, '2026-06-12T08:40:00+02:00', base_dir=repo,
                        extra={'active_dedup': 380, 'active_olx': 60})
    index_history.record(300, '2026-06-12T18:40:00+02:00', base_dir=repo,
                        extra={'active_dedup': 240, 'active_olx': 30})

    days = index_history.load(base_dir=repo)['days']
    assert days['2026-06-12']['active'] == 480
    assert days['2026-06-12']['active_dedup'] == 380
    assert days['2026-06-12']['active_olx'] == 60  # liczniki z tego samego, pełnego skanu
    assert days['2026-06-12']['scans'] == 2  # oba odczyty policzone


def test_daily_series_zwraca_none_dla_dnia_bez_skanu(repo):
    index_history.record(480, timestamp='2026-06-12T08:40:00+02:00', base_dir=repo)
    index_history.record(470, timestamp='2026-06-14T08:40:00+02:00', base_dir=repo)

    assert index_history.daily_series(base_dir=repo) == [
        (date(2026, 6, 12), 480),
        (date(2026, 6, 13), None),   # luka, nie zmyślone zero
        (date(2026, 6, 14), 470),
    ]


def test_backfill_nie_nadpisuje_dni_z_zywego_skanu(repo):
    index_history.record(480, timestamp='2026-06-12T08:40:00+02:00', base_dir=repo)
    _write_scan_history(repo, [
        {'timestamp': '2026-06-12T18:40:00+02:00', 'status': 'completed', 'active': 999},
        {'timestamp': '2026-06-13T08:40:00+02:00', 'status': 'completed', 'active': 470},
        {'timestamp': '2026-06-13T18:40:00+02:00', 'status': 'completed', 'active': 475},
        {'timestamp': '2026-06-14T08:40:00+02:00', 'status': 'failed', 'error': 'boom'},
        # starsze wpisy nie mają pola `status` — muszą wejść
        {'timestamp': '2026-06-15T08:40:00+02:00', 'active': 460},
    ])

    added = index_history.backfill_from_scan_history(base_dir=repo)

    days = index_history.load(base_dir=repo)['days']
    assert added == 2                       # 13.06 i 15.06; 12.06 już był, 14.06 failed
    assert days['2026-06-12']['active'] == 480   # żywy zapis nietknięty
    assert days['2026-06-13']['active'] == 475   # maksimum z dnia
    assert '2026-06-14' not in days
    assert days['2026-06-15']['active'] == 460


# --- trend_generator ---------------------------------------------------------

def test_collect_dates_scala_liste_i_stare_pole():
    offer = {'deactivation_dates': ['2026-07-01', '2026-07-05'],
             'deactivated_at': '2026-07-05T11:00:00+02:00'}
    assert tg.collect_dates(offer, 'deactivation_dates', 'deactivated_at') == [
        date(2026, 7, 1), date(2026, 7, 5)]  # bez powtórki


def test_collect_dates_sama_historia_sprzed_wdrozenia_list():
    offer = {'reactivated_at': '2026-07-09T12:06:51+02:00'}
    assert tg.collect_dates(offer, 'reactivation_dates', 'reactivated_at') == [date(2026, 7, 9)]


def test_build_series_czyta_mierzony_stan_bazy(repo, monkeypatch):
    monkeypatch.setattr(tg, 'RELIABLE_START', date(2026, 6, 12))
    index_history.record(485, timestamp='2026-06-11T08:40:00+02:00', base_dir=repo)  # przed startem
    index_history.record(480, timestamp='2026-06-12T08:40:00+02:00', base_dir=repo)
    index_history.record(470, timestamp='2026-06-14T08:40:00+02:00', base_dir=repo)

    assert tg.build_series([], base_dir=repo) == [
        [_ms(2026, 6, 12), 480],
        [_ms(2026, 6, 13), None],
        [_ms(2026, 6, 14), 470],
    ]


def test_build_series_awaryjnie_rekonstruuje_bez_historii(repo):
    offers = [
        {'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
         'last_seen': '2026-06-14T08:00:00+02:00', 'active': True},
        {'id': 'b', 'first_seen': '2026-06-13T08:00:00+02:00',
         'last_seen': '2026-06-13T08:00:00+02:00', 'active': False},
    ]
    series = tg.build_series(offers, base_dir=repo)  # brak index_history.json
    assert series == [[_ms(2026, 6, 12), 1], [_ms(2026, 6, 13), 2], [_ms(2026, 6, 14), 1]]


def test_przerwa_w_zyciu_oferty_nie_liczy_sie_jako_zywa():
    offer = {'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
             'last_seen': '2026-06-16T08:00:00+02:00', 'active': True,
             'deactivation_dates': ['2026-06-13'], 'reactivation_dates': ['2026-06-15']}
    (_, intervals), = tg.build_spans([offer])[0]

    assert tg._alive(intervals, date(2026, 6, 12)) is True
    assert tg._alive(intervals, date(2026, 6, 14)) is False   # w środku przerwy
    assert tg._alive(intervals, date(2026, 6, 16)) is True


def test_build_outflow_liczy_dzienny_odplyw_i_srednia():
    series = [[_ms(2026, 6, 12), 3], [_ms(2026, 6, 13), 2], [_ms(2026, 6, 14), 2]]
    offers = [
        {'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
         'last_seen': '2026-06-13T08:00:00+02:00', 'active': False,
         'deactivated_at': '2026-06-13T20:00:00+02:00'},
        # oferta bez zapisanej daty deaktywacji → odpływ z last_seen
        {'id': 'b', 'first_seen': '2026-06-12T08:00:00+02:00',
         'last_seen': '2026-06-13T08:00:00+02:00', 'active': False},
        {'id': 'c', 'first_seen': '2026-06-12T08:00:00+02:00',
         'last_seen': '2026-06-14T08:00:00+02:00', 'active': True},
    ]
    out = tg.build_outflow(offers, series)

    assert [v for _, v in out['daily']] == [0, 2, 0]
    assert out['total'] == 2
    assert out['max_day'] == 2 and out['max_label'] == '13.06'
    assert [v for _, v in out['avg']] == [0.0, 1.0, round(2 / 3, 1)]


def test_build_inflow_rozdziela_nowe_od_reaktywacji():
    series = [[_ms(2026, 6, 12), 1], [_ms(2026, 6, 13), 2], [_ms(2026, 6, 14), 2]]
    offers = [
        {'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
         'last_seen': '2026-06-14T08:00:00+02:00', 'active': True,
         'deactivation_dates': ['2026-06-13'], 'reactivation_dates': ['2026-06-14']},
        {'id': 'b', 'first_seen': '2026-06-13T08:00:00+02:00',
         'last_seen': '2026-06-14T08:00:00+02:00', 'active': True},
    ]
    inflow = tg.build_inflow(offers, series)

    assert [v for _, v in inflow['new']['daily']] == [1, 1, 0]
    assert [v for _, v in inflow['react']['daily']] == [0, 0, 1]
    assert [v for _, v in inflow['new_react']['daily']] == [1, 1, 1]


def test_dzien_artefakt_reaktywacji_jest_luka_nie_pikiem(monkeypatch):
    """Hurtowy powrót po częściowym scrape'ie to artefakt pipeline'u, nie rynek."""
    monkeypatch.setattr(tg, 'REACT_ARTIFACT_THRESHOLD', 2)
    series = [[_ms(2026, 6, 12), 3], [_ms(2026, 6, 13), 3]]
    offers = [
        {'id': str(i), 'first_seen': '2026-06-12T08:00:00+02:00',
         'last_seen': '2026-06-13T08:00:00+02:00', 'active': True,
         'reactivation_dates': ['2026-06-13']}
        for i in range(3)
    ]
    react = tg.build_inflow(offers, series)['react']

    assert [v for _, v in react['daily']] == [0, None]  # pik wycięty
    assert react['total'] == 0 and react['max_day'] == 0


def test_suma_pasm_rowna_sie_indeksowi():
    series = [[_ms(2026, 6, 12), 100], [_ms(2026, 6, 13), 90]]
    offers = [
        {'id': 'a', 'first_seen': '2026-06-10T08:00:00+02:00',
         'last_seen': '2026-06-13T08:00:00+02:00', 'active': True,
         'reactivation_dates': ['2026-06-11']},           # recykling od 11.06
        {'id': 'b', 'first_seen': '2026-06-10T08:00:00+02:00',
         'last_seen': '2026-06-13T08:00:00+02:00', 'active': True},
    ]
    bands = tg.build_bands(offers, series)

    for i, (_, index_value) in enumerate(series):
        assert bands['new'][i][1] + bands['react'][i][1] == index_value
    assert bands['react'][0][1] == 50  # połowa żywych ofert to recykling


def test_pasma_pusta_dla_dnia_bez_skanu():
    series = [[_ms(2026, 6, 12), 10], [_ms(2026, 6, 13), None]]
    offers = [{'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
               'last_seen': '2026-06-13T08:00:00+02:00', 'active': True}]
    bands = tg.build_bands(offers, series)

    assert bands['new'][1][1] is None and bands['react'][1][1] is None


def test_compute_deltas_pomija_dni_bez_skanu():
    series = [[_ms(2026, 6, 12), 480], [_ms(2026, 6, 13), None], [_ms(2026, 6, 14), 470]]
    deltas = tg.compute_deltas(series)

    assert deltas['1D'] == -10   # 13.06 to luka → porównanie do 12.06
    assert deltas['1M'] is None  # brak tak starej historii
    assert deltas['1Y'] is None


def test_count_dedup_active_chowa_duplikaty_aktywnej_oferty():
    offers = [
        {'id': 'otodom:1', 'active': True},
        {'id': 'olx:1', 'active': True, 'duplicate_of': 'otodom:1'},
        {'id': 'olx:2', 'active': True, 'duplicate_of': 'otodom:9'},  # kanoniczna nieaktywna
        {'id': 'olx:3', 'active': False, 'duplicate_of': 'otodom:1'},
    ]
    assert tg.count_dedup_active(offers) == 2


def test_udzial_wyroznien_liczony_do_ofert_OLX_nie_calej_bazy(repo):
    """Wyróżnić może się tylko oferta OLX — mianownik musi być OLX-owy.

    Regresja: mianownikiem był cały Indeks (6 źródeł), przez co udział wychodził
    kilkukrotnie za niski i przeczył liczbie z map_generator.build_promoted.
    """
    _write_scan_history(repo, [
        {'timestamp': '2026-06-12T08:40:00+02:00', 'status': 'completed',
         'active': 100, 'scraped_olx': 20, 'scraped_otodom': 80},
    ])
    index_history.record(100, '2026-06-12T08:40:00+02:00', base_dir=repo,
                         extra={'active_olx': 20})
    offers = [{'id': str(i), 'first_seen': '2026-06-12T08:00:00+02:00',
               'last_seen': '2026-06-12T08:00:00+02:00', 'active': True,
               'promoted_dates': ['2026-06-12']} for i in range(5)]
    series = [[_ms(2026, 6, 12), 100]]

    promoted = tg.build_promoted(offers, series, tg.load_scan_days(repo), repo)

    assert promoted['current'] == 5
    assert promoted['current_share'] == 25.0     # 5 z 20 ofert OLX, nie 5 ze 100
    assert promoted['share'][0][1] == 25.0


def test_udzial_wyroznien_bez_znanego_mianownika_to_luka(repo):
    (repo / 'data' / 'scan_history.json').write_text('{"scans": []}', encoding='utf-8')
    offers = [{'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
               'last_seen': '2026-06-12T08:00:00+02:00', 'active': True,
               'promoted_dates': ['2026-06-12']}]
    promoted = tg.build_promoted(offers, [[_ms(2026, 6, 12), 100]], set(), repo)

    assert promoted['share'][0][1] is None       # zero byłoby zmyślone
    assert promoted['current_share'] is None


def test_generate_zapisuje_komplet_serii(repo):
    (repo / 'data' / 'offers.json').write_text(json.dumps({'offers': [
        {'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
         'last_seen': '2026-06-13T08:00:00+02:00', 'active': True,
         'promoted_dates': ['2026-06-13']},
    ]}), encoding='utf-8')
    _write_scan_history(repo, [
        {'timestamp': '2026-06-12T08:40:00+02:00', 'status': 'completed', 'active': 1},
        {'timestamp': '2026-06-13T08:40:00+02:00', 'status': 'completed', 'active': 1},
    ])
    index_history.record(1, '2026-06-12T08:40:00+02:00', base_dir=repo,
                        extra={'active_dedup': 1, 'active_olx': 1})
    index_history.record(1, '2026-06-13T08:40:00+02:00', base_dir=repo,
                        extra={'active_dedup': 1, 'active_olx': 1})

    assert tg.generate(base_dir=repo) is True

    data = json.loads((repo / 'docs' / 'trend_data.json').read_text(encoding='utf-8'))
    assert data['index_source'] == 'measured'
    assert data['current'] == 1 and data['current_dedup'] == 1
    assert len(data['series']) == 2
    assert data['promoted']['current'] == 1
    assert set(data['inflow']) == {'new', 'react', 'new_react'}


def test_generate_bez_zadnych_danych_nie_wywraca_sie(repo):
    (repo / 'data' / 'offers.json').write_text(json.dumps({'offers': []}), encoding='utf-8')
    assert tg.generate(base_dir=repo) is False
    assert not (repo / 'docs' / 'trend_data.json').exists()
