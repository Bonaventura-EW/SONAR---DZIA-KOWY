"""Testy alarmów o awarii źródeł (source_health) — API ma krzyczeć, gdy
scraper jednego portalu przestaje zwracać oferty, mimo że skan „się udał".
"""

from source_health import (build_source_alerts, group_active_by_source,
                           health_status, summarize_sources)


def scan(timestamp, olx=50, otodom=170, adresowo=190, agencies=200,
         status='completed'):
    """Wpis scan_history; None = pola nie było w tym skanie."""
    entry = {'timestamp': timestamp, 'status': status, 'scraped_olx': olx,
             'scraped_otodom': otodom, 'scraped_adresowo': adresowo,
             'scraped_agencies': agencies}
    return {k: v for k, v in entry.items() if v is not None}


def history(*counts, base_day=10):
    """Historia skanów z podaną liczbą ofert OLX (reszta źródeł zdrowa)."""
    return [scan(f'2026-08-{base_day + i:02d}T09:00:00+02:00', olx=c)
            for i, c in enumerate(counts)]


def test_zdrowe_zrodla_bez_alarmu():
    summary = summarize_sources(history(50, 52, 48, 51))
    assert summary['olx']['status'] == 'ok'
    assert build_source_alerts(summary) == []


def test_jeden_pusty_skan_to_ostrzezenie():
    summary = summarize_sources(history(50, 52, 48, 0))
    assert summary['olx']['status'] == 'down'
    assert summary['olx']['zero_scans_in_row'] == 1

    alerts = build_source_alerts(summary)
    assert len(alerts) == 1
    assert alerts[0]['severity'] == 'warning'
    assert alerts[0]['code'] == 'source_down'
    # ostrzeżenie nie psuje jeszcze statusu całego API
    assert health_status(fresh=True, last_scan_ok=True, alerts=alerts) == 'ok'


def test_dwa_puste_skany_to_alarm_krytyczny():
    summary = summarize_sources(history(50, 52, 48, 0, 0, 0))
    alert = build_source_alerts(summary)[0]

    assert alert['severity'] == 'critical'
    assert alert['source'] == 'olx'
    assert alert['scans_affected'] == 3
    assert alert['baseline'] == 50
    # w komunikacie data ostatnich ofert — od kiedy portal milczy
    assert alert['last_offers_at'] == '2026-08-12T09:00:00+02:00'
    assert '2026-08-12' in alert['message']
    assert health_status(fresh=True, last_scan_ok=True, alerts=[alert]) == 'degraded'


def test_czesciowa_blokada_to_ostrzezenie():
    """Źródło odpowiada, ale zwraca ułamek swojej normy (throttling)."""
    summary = summarize_sources(history(50, 52, 48, 5))
    alert = build_source_alerts(summary)[0]

    assert summary['olx']['status'] == 'degraded'
    assert alert['code'] == 'source_degraded'
    assert alert['severity'] == 'warning'
    assert alert['last_scan_count'] == 5


def test_nieudane_skany_nie_licza_sie_do_zdrowia_zrodla():
    """Skan, który padł w całości, nic nie mówi o pojedynczym źródle."""
    scans = history(50, 52, 48)
    scans.append(scan('2026-08-13T09:00:00+02:00', olx=0, otodom=0,
                      adresowo=0, agencies=0, status='failed'))
    summary = summarize_sources(scans)

    assert summary['olx']['status'] == 'ok'
    assert build_source_alerts(summary) == []


def test_zrodlo_bez_historii_nie_alarmuje():
    """Świeżo dodane źródło (za mało udanych skanów) = 'unknown', bez alarmu."""
    summary = summarize_sources(history(0, 0))
    assert summary['olx']['status'] == 'unknown'
    assert build_source_alerts(summary) == []


def test_brak_pola_w_historii_to_unknown():
    """Stare wpisy nie mają pola źródła — nie zgadujemy, że dało 0 ofert."""
    scans = [scan(f'2026-08-{10 + i:02d}T09:00:00+02:00', olx=None)
             for i in range(5)]
    summary = summarize_sources(scans)

    assert summary['olx']['status'] == 'unknown'
    assert summary['otodom']['status'] == 'ok'
    assert build_source_alerts(summary) == []


def test_alarmy_sortowane_krytyczne_najpierw():
    scans = [scan('2026-08-10T09:00:00+02:00'),
             scan('2026-08-11T09:00:00+02:00'),
             scan('2026-08-12T09:00:00+02:00'),
             scan('2026-08-13T09:00:00+02:00', olx=0, adresowo=5),
             scan('2026-08-14T09:00:00+02:00', olx=0, adresowo=5)]
    alerts = build_source_alerts(summarize_sources(scans))

    assert [a['source'] for a in alerts] == ['olx', 'adresowo']
    assert alerts[0]['severity'] == 'critical'
    assert alerts[1]['severity'] == 'warning'


def test_liczenie_aktywnych_per_zrodlo():
    offers = [
        {'source': 'olx', 'active': True},
        {'source': 'olx', 'active': False},
        {'source': 'otodom', 'active': True},
        {'source': 'adresowo', 'active': True},
        {'source': 'anma', 'active': True},
        {'source': 'alternatywne', 'active': True},
    ]
    counts = group_active_by_source(offers)

    assert counts == {'olx': 1, 'otodom': 1, 'adresowo': 1, 'agencies': 2}


def test_hierarchia_statusu_health():
    critical = [{'severity': 'critical'}]
    assert health_status(fresh=False, last_scan_ok=True, alerts=[]) == 'stale'
    assert health_status(fresh=False, last_scan_ok=False, alerts=critical) == 'stale'
    assert health_status(fresh=True, last_scan_ok=False, alerts=critical) == 'failing'
    assert health_status(fresh=True, last_scan_ok=True, alerts=critical) == 'degraded'
    assert health_status(fresh=True, last_scan_ok=True, alerts=[]) == 'ok'


def test_alarm_niesie_stan_bazy_dla_zrodla():
    summary = summarize_sources(history(50, 52, 48, 0, 0),
                                active_by_source={'olx': 57})
    alert = build_source_alerts(summary)[0]

    assert alert['active_in_db'] == 57
    assert 'nieaktualne' in alert['message']


def test_norma_przezywa_dluga_awarie_zrodla():
    """Po powrocie źródła norma nie znika pod stertą zer — inaczej kolejna
    blokada byłaby cicha przez kilka skanów (regresja z 2026-08-24)."""
    scans = history(*([50, 52, 48, 51] + [0] * 12 + [64]))
    summary = summarize_sources(scans)

    assert summary['olx']['status'] == 'ok'
    assert summary['olx']['baseline'] >= 50  # norma sprzed awarii, nie samo 64

    # ponowna blokada nazajutrz — alarm ma pójść od pierwszego pustego skanu
    scans.append(scan('2026-09-01T09:00:00+02:00', olx=0))
    alerts = build_source_alerts(summarize_sources(scans))

    assert [a['code'] for a in alerts] == ['source_down']
    assert alerts[0]['source'] == 'olx'
