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
from datetime import datetime, date, timedelta

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
    assert days['2026-06-13']['scans'] == 2   # dzień miał dwa skany, nie jeden
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
    # przerwa dłuższa niż FLAP_MAX_DAYS — realne zniknięcie, nie zacięcie scrapera
    offer = {'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
             'last_seen': '2026-06-20T08:00:00+02:00', 'active': True,
             'deactivation_dates': ['2026-06-13'], 'reactivation_dates': ['2026-06-19']}
    (_, intervals), = tg.build_spans([offer])[0]

    assert tg._alive(intervals, date(2026, 6, 12)) is True
    assert tg._alive(intervals, date(2026, 6, 16)) is False   # w środku przerwy
    assert tg._alive(intervals, date(2026, 6, 20)) is True


def test_mrugniecie_pipelinu_wypada_z_obu_serii():
    """Zniknęła i wróciła w 3 dni = częściowy scrape, nie ruch na rynku.

    Regresja z realnych danych: 06.07.2026 scraper agencji oddał 229 ofert
    zamiast ~265, przez co 23 żywe oferty zdezaktywowano, a następny skan je
    wskrzesił — i wykresy pokazywały „rekord odpływu 27" oraz „rekord
    reaktywacji 26" jako fakty rynkowe.
    """
    flap = {'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
            'last_seen': '2026-06-20T08:00:00+02:00', 'active': True,
            'deactivation_dates': ['2026-06-14'], 'reactivation_dates': ['2026-06-16']}
    real = {'id': 'b', 'first_seen': '2026-06-12T08:00:00+02:00',
            'last_seen': '2026-06-20T08:00:00+02:00', 'active': True,
            'deactivation_dates': ['2026-06-14'], 'reactivation_dates': ['2026-06-19']}

    assert tg.life_events(flap) == ([], [], 1)                       # obie strony pary znikają
    assert tg.life_events(real) == ([date(2026, 6, 14)], [date(2026, 6, 19)], 0)

    days = tg._daily_range(date(2026, 6, 12), date(2026, 6, 20))
    series = [[tg._day_ms(d), 100] for d in days]   # rynek 100 ofert: pojedyncze
    assert sum(v for _, v in tg.build_outflow([flap, real], series)['daily']) == 1
    assert sum(v for _, v in tg.build_inflow([flap, real], series)['react']['daily']) == 1


def test_mrugniecie_nie_dzieli_zycia_oferty_na_kawalki():
    """Skoro powrót w 3 dni to zacięcie scrapera, oferta w tym czasie żyła —
    inaczej pasmo „recykling" liczyłoby zacięcia jako recykling rynkowy."""
    flap = {'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
            'last_seen': '2026-06-20T08:00:00+02:00', 'active': True,
            'deactivation_dates': ['2026-06-14'], 'reactivation_dates': ['2026-06-16']}
    (_, intervals), = tg.build_spans([flap])[0]

    assert tg._alive(intervals, date(2026, 6, 15)) is True
    series = [[tg._day_ms(d), 1] for d in tg._daily_range(date(2026, 6, 12), date(2026, 6, 20))]
    assert all(v == 0 for _, v in tg.build_bands([flap], series)['react'])


def test_dzien_powrotu_zrodla_nie_ustanawia_rekordu(repo):
    """Po blokadzie źródło zrzuca do bazy zaległości z wielu dni naraz.

    Regresja z danych: 24.08.2026, w dniu powrotu OLX po 12 dniach milczenia,
    wpadło 15 „nowych" ofert OLX — i to był rekord napływu na wykresie, choć
    to dorobek dwunastu dni. Słupek zostaje, ale nie liczy się do średniej
    ani do rekordu.
    """
    _write_scan_history(repo, [
        {'timestamp': '2026-06-12T08:40:00+02:00', 'status': 'completed', 'scraped_olx': 20},
        {'timestamp': '2026-06-13T08:40:00+02:00', 'status': 'completed', 'scraped_olx': 0},
        {'timestamp': '2026-06-14T08:40:00+02:00', 'status': 'completed', 'scraped_olx': 0},
        {'timestamp': '2026-06-15T08:40:00+02:00', 'status': 'completed', 'scraped_olx': 20},
    ])

    assert tg.recovery_days(repo) == {date(2026, 6, 15): ['olx']}

    days = tg._daily_range(date(2026, 6, 12), date(2026, 6, 15))
    counts = {date(2026, 6, 12): 3, date(2026, 6, 15): 40}
    metric = tg._flow_metric(counts, days, uncounted=set(tg.recovery_days(repo)))

    assert metric['daily'][-1][1] == 40      # słupek zostaje
    assert metric['max_day'] == 3            # ale rekordem jest zwykły dzień
    assert metric['total'] == 3

    (rng,) = tg.blind_ranges(repo)
    assert rng['days'] == 2                   # ślepota to 13-14.06
    assert rng['to'] > _ms(2026, 6, 15)       # pas obejmuje też dzień nadrabiania


def test_slepe_zrodlo_to_luka_w_wyroznieniach_nie_zero(repo):
    """Dzień, w którym OLX nie oddał ANI JEDNEJ oferty, nie może rysować
    „0 wyróżnionych" — skan się odbył, ale nie było czego zliczyć."""
    _write_scan_history(repo, [
        {'timestamp': '2026-06-12T08:40:00+02:00', 'status': 'completed',
         'active': 100, 'scraped_olx': 20},
        {'timestamp': '2026-06-13T08:40:00+02:00', 'status': 'completed',
         'active': 100, 'scraped_olx': 0},     # blokada OLX
        {'timestamp': '2026-06-13T18:40:00+02:00', 'status': 'completed',
         'active': 100, 'scraped_olx': 0},
        {'timestamp': '2026-06-14T08:40:00+02:00', 'status': 'completed',
         'active': 100, 'scraped_olx': 20},
    ])
    offers = [{'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
               'last_seen': '2026-06-14T08:00:00+02:00', 'active': True,
               'promoted_dates': ['2026-06-12', '2026-06-14']}]
    series = [[_ms(2026, 6, d), 100] for d in (12, 13, 14)]

    assert tg.blind_source_days(repo) == {date(2026, 6, 13): ['olx']}
    promoted = tg.build_promoted(offers, series, tg.load_scan_days(repo), repo)
    assert [v for _, v in promoted['daily']] == [1, None, 1]

    (rng,) = tg.blind_ranges(repo)
    assert rng['source'] == 'olx' and rng['days'] == 1
    assert rng['from'] < _ms(2026, 6, 13) < rng['to']
    assert rng['to'] > _ms(2026, 6, 14)   # pas obejmuje dzień nadrabiania zaległości


def test_zrodlo_nieraportowane_nie_jest_slepe(repo):
    """Starsze wpisy scan_history nie mają pola `scraped_adresowo` — brak pola
    znaczy „nie wiemy", nie „zero ofert"."""
    _write_scan_history(repo, [
        {'timestamp': '2026-06-12T08:40:00+02:00', 'status': 'completed',
         'active': 100, 'scraped_olx': 20},
    ])
    assert tg.blind_source_days(repo) == {}


def test_build_outflow_liczy_dzienny_odplyw_i_srednia():
    series = [[_ms(2026, 6, 12), 100], [_ms(2026, 6, 13), 100], [_ms(2026, 6, 14), 100]]
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
    days = [12, 13, 14, 15, 16, 17, 18, 19]
    series = [[_ms(2026, 6, d), 100] for d in days]
    offers = [
        # powrót po 6 dniach — realna reaktywacja, nie mrugnięcie pipeline'u
        {'id': 'a', 'first_seen': '2026-06-12T08:00:00+02:00',
         'last_seen': '2026-06-19T08:00:00+02:00', 'active': True,
         'deactivation_dates': ['2026-06-13'], 'reactivation_dates': ['2026-06-19']},
        {'id': 'b', 'first_seen': '2026-06-13T08:00:00+02:00',
         'last_seen': '2026-06-19T08:00:00+02:00', 'active': True},
    ]
    inflow = tg.build_inflow(offers, series)

    assert [v for _, v in inflow['new']['daily']] == [1, 1, 0, 0, 0, 0, 0, 0]
    assert [v for _, v in inflow['react']['daily']] == [0, 0, 0, 0, 0, 0, 0, 1]
    assert [v for _, v in inflow['new_react']['daily']] == [1, 1, 0, 0, 0, 0, 0, 1]


def test_dzien_artefakt_reaktywacji_jest_luka_nie_pikiem():
    """Hurtowy powrót po częściowym scrape'ie to artefakt pipeline'u, nie rynek.

    Próg jest względny: 20 powrotów przy rynku 100 ofert (20% w dobę) to
    zacięcie, te same 20 przy rynku 1000 byłoby normalnym dniem.
    """
    series = [[_ms(2026, 6, 12), 100], [_ms(2026, 6, 13), 100]]
    offers = [
        {'id': str(i), 'first_seen': '2026-06-12T08:00:00+02:00',
         'last_seen': '2026-06-13T08:00:00+02:00', 'active': True,
         'reactivation_dates': ['2026-06-13']}
        for i in range(20)
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


def test_dzien_w_toku_nie_wchodzi_do_sredniej_ani_rekordu(repo):
    """Pół dnia to nie spadek. Dopóki dziś nie zamknie wszystkich skanów,
    słupek zostaje na wykresie, ale średnia krocząca i rekordy go nie widzą —
    inaczej prawy koniec każdego wykresu zawsze opadał."""
    today = datetime.now(tg.TZ).date()
    days = tg._daily_range(today - timedelta(days=3), today)
    series = [[tg._day_ms(d), 100] for d in days]
    index_history.record(100, datetime.now(tg.TZ).isoformat(), base_dir=repo)  # 1 z 2 skanów

    assert tg.provisional_day(series, repo) == today

    counts = {d: 10 for d in days[:-1]}
    counts[today] = 1                      # dopiero poranny skan
    metric = tg._flow_metric(counts, days, uncounted={today})

    assert metric['daily'][-1][1] == 1     # słupek zostaje — to prawdziwa liczba
    assert metric['avg'][-1][1] == 10.0    # ale średnia liczy tylko dni zamknięte
    assert metric['max_day'] == 10 and metric['total'] == 30


def test_dzien_zamkniety_nie_jest_prowizoryczny(repo):
    today = datetime.now(tg.TZ).date()
    series = [[tg._day_ms(today), 100]]
    for _ in range(tg.SCANS_PER_DAY):
        index_history.record(100, datetime.now(tg.TZ).isoformat(), base_dir=repo)

    assert tg.provisional_day(series, repo) is None


def test_wczorajszy_koniec_serii_nie_jest_prowizoryczny(repo):
    wczoraj = datetime.now(tg.TZ).date() - timedelta(days=1)
    assert tg.provisional_day([[tg._day_ms(wczoraj), 100]], repo) is None


def test_compute_deltas_pomija_dni_bez_skanu():
    series = [[_ms(2026, 6, 12), 480], [_ms(2026, 6, 13), None], [_ms(2026, 6, 14), 470]]
    deltas = tg.compute_deltas(series)

    assert deltas['1D'] == -10   # 13.06 to luka → porównanie do 12.06
    assert deltas['1M'] is None  # brak tak starej historii
    assert deltas['1Y'] is None


def test_prog_artefaktu_jest_wzgledny_do_wielkosci_rynku():
    """12% rynku w jedną dobę to zacięcie, nie ruch — ale „12%" znaczy co innego
    przy 100 ofertach niż przy 1000, więc próg nie może być sztywną liczbą."""
    days = tg._daily_range(date(2026, 6, 12), date(2026, 6, 13))
    maly = [[tg._day_ms(d), 100] for d in days]
    duzy = [[tg._day_ms(d), 1000] for d in days]
    counts = {days[1]: 50}

    assert tg._artifact_days(counts, maly) == {days[1]}   # 50% rynku → artefakt
    assert tg._artifact_days(counts, duzy) == set()       # 5% rynku → normalny dzień


def test_delta_nie_siega_po_wartosc_sprzed_dlugiej_awarii():
    """Porównanie „1M" ma dotyczyć dnia sprzed miesiąca, a nie ostatniego dnia
    ze skanem sprzed pięciu tygodni."""
    swiezy = [[tg._day_ms(date(2026, 6, 10)), 400], [tg._day_ms(date(2026, 6, 12)), 410]]
    assert tg._value_at_or_before(swiezy, tg._day_ms(date(2026, 6, 12))) == 410
    assert tg._value_at_or_before(swiezy, tg._day_ms(date(2026, 6, 11))) == 400  # 1 dzień wstecz
    assert tg._value_at_or_before(swiezy, tg._day_ms(date(2026, 6, 20))) is None  # 10 dni → za stare


def test_day_ms_nie_zalezy_od_strefy_procesu():
    """Punkty mają lądować w to samo miejsce niezależnie od tego, czy plik
    powstał na Actions (UTC), czy na laptopie (CEST)."""
    assert tg._day_ms(date(2026, 6, 12)) == 1781265600000  # 12.06.2026 12:00 UTC


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
