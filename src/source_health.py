"""Alarmy o awarii źródeł (scraperów) — dane dla API i monitoringu.

FIX 2026-08-24: OLX od 2026-08-11 odpowiada 403 (CloudFront/WAF) na requesty
z runnerów GitHub Actions. Skan mimo to kończył się statusem 'completed'
(pozostałe źródła działały), a ochrona z `main.py::_mark_inactive` słusznie
pomijała dezaktywację — przez co awaria była NIEWIDOCZNA na zewnątrz:
`api/health.json` przez 26 kolejnych skanów raportował `"status": "ok"`.

Ten moduł liczy z `data/scan_history.json` stan zdrowia KAŻDEGO źródła
(ile ofert dało w ostatnim skanie vs ile dawało wcześniej) i zamienia go
na alarmy, które `api_generator` wystawia w `health.json` / `status.json`,
a `monitoring_generator` w danych dashboardu.
"""

from statistics import median
from typing import Dict, List, Optional

# klucz źródła w API → pole w data/scan_history.json (main.py::_log_scan)
SOURCE_FIELDS = {
    'olx': 'scraped_olx',
    'otodom': 'scraped_otodom',
    'adresowo': 'scraped_adresowo',
    'agencies': 'scraped_agencies',
}
SOURCE_LABELS = {
    'olx': 'OLX',
    'otodom': 'Otodom',
    'adresowo': 'Adresowo',
    'agencies': 'Agencje',
}
# źródła portalowe mają własne pole w historii; reszta (anma, pasjonaci,
# alternatywne, idshome…) sumuje się do 'agencies'
PORTAL_SOURCES = ('olx', 'otodom', 'adresowo')

# 2 kolejne skany bez ofert (~1 doba przy 2 skanach/dzień) = awaria, nie wpadka
DOWN_AFTER_SCANS = 2
# <30% typowej liczby ofert = źródło odpowiada, ale częściowo (throttling/blokada)
DEGRADED_RATIO = 0.3
# okno, z którego liczymy "normalną" liczbę ofert źródła
BASELINE_SCANS = 10
# bez kilku udanych skanów w historii nie ma podstaw do alarmu (nowe źródło)
MIN_BASELINE_SAMPLES = 3


def _completed(scans: List[Dict]) -> List[Dict]:
    """Tylko skany zakończone sukcesem — nieudany skan nic nie mówi o źródle."""
    return [s for s in scans if s.get('status', 'completed') == 'completed']


def group_active_by_source(offers: List[Dict]) -> Dict[str, int]:
    """Liczba AKTYWNYCH ofert w bazie per klucz źródła (przed deduplikacją —
    zdrowie źródła mierzymy jego własnym stanem, nie tym co zostaje na mapie).
    """
    counts = {key: 0 for key in SOURCE_FIELDS}
    for offer in offers:
        if not offer.get('active'):
            continue
        source = offer.get('source')
        key = source if source in PORTAL_SOURCES else 'agencies'
        counts[key] = counts.get(key, 0) + 1
    return counts


def _stats_for_field(done: List[Dict], field: str) -> Dict:
    """Streak zerowych skanów + typowa liczba ofert sprzed streaka."""
    zero_scans = 0
    last_offers_at = None
    for scan in reversed(done):
        value = scan.get(field)
        if value is None:
            break  # źródła nie było jeszcze w tym skanie — nie zgadujemy
        if value == 0:
            zero_scans += 1
            continue
        last_offers_at = scan.get('timestamp')
        break

    before_streak = done[:len(done) - zero_scans] if zero_scans else done
    window = [s.get(field) for s in before_streak[-BASELINE_SCANS:]]
    non_zero = [v for v in window if v]
    return {
        'zero_scans': zero_scans,
        'last_offers_at': last_offers_at,
        'baseline': int(median(non_zero)) if non_zero else None,
        'samples': len(non_zero),
    }


def summarize_sources(scans: List[Dict],
                      active_by_source: Optional[Dict[str, int]] = None) -> Dict[str, Dict]:
    """Stan każdego źródła: 'ok' | 'degraded' | 'down' | 'unknown'.

    - `down`     — źródło nie zwróciło ANI JEDNEJ oferty w ostatnim skanie,
                   choć wcześniej regularnie zwracało (blokada/zmiana HTML),
    - `degraded` — zwróciło <30% swojej normy (throttling, częściowa blokada),
    - `unknown`  — brak danych w historii albo za krótka historia.
    """
    done = _completed(scans)
    active_by_source = active_by_source or {}
    summary: Dict[str, Dict] = {}

    for source, field in SOURCE_FIELDS.items():
        last_count = done[-1].get(field) if done else None
        stats = _stats_for_field(done, field) if done else {
            'zero_scans': 0, 'last_offers_at': None, 'baseline': None, 'samples': 0}
        baseline = stats['baseline']
        enough_history = baseline is not None and stats['samples'] >= MIN_BASELINE_SAMPLES

        if last_count is None or not enough_history:
            status = 'unknown'
        elif stats['zero_scans']:
            status = 'down'
        elif last_count < baseline * DEGRADED_RATIO:
            status = 'degraded'
        else:
            status = 'ok'

        summary[source] = {
            'label': SOURCE_LABELS[source],
            'status': status,
            'last_scan_count': last_count,
            'baseline': baseline,
            'zero_scans_in_row': stats['zero_scans'],
            'last_offers_at': stats['last_offers_at'],
            'active_in_db': active_by_source.get(source),
        }
    return summary


def build_source_alerts(summary: Dict[str, Dict]) -> List[Dict]:
    """Alarmy z podsumowania źródeł — najpierw krytyczne, potem ostrzeżenia."""
    alerts = []
    for source, info in summary.items():
        label, baseline = info['label'], info['baseline']
        if info['status'] == 'down':
            zero_scans = info['zero_scans_in_row']
            critical = zero_scans >= DOWN_AFTER_SCANS
            since = (info['last_offers_at'] or '')[:16].replace('T', ' ')
            message = (f"{label}: {zero_scans} "
                       f"{'kolejnych skanów' if zero_scans > 1 else 'skan'} "
                       f"bez ani jednej oferty (norma ~{baseline}/skan)")
            if since:
                message += f", ostatnie oferty {since}"
            message += ('. Prawdopodobna blokada źródła — dane tego portalu '
                        'na mapie są nieaktualne.' if critical
                        else '. Jeśli powtórzy się w kolejnym skanie — blokada źródła.')
            alerts.append({
                'source': source,
                'severity': 'critical' if critical else 'warning',
                'code': 'source_down',
                'message': message,
                'scans_affected': zero_scans,
                'last_scan_count': 0,
                'baseline': baseline,
                'last_offers_at': info['last_offers_at'],
                'active_in_db': info['active_in_db'],
            })
        elif info['status'] == 'degraded':
            alerts.append({
                'source': source,
                'severity': 'warning',
                'code': 'source_degraded',
                'message': (f"{label}: {info['last_scan_count']} ofert w ostatnim "
                            f"skanie przy normie ~{baseline} — źródło odpowiada "
                            f"tylko częściowo."),
                'scans_affected': 1,
                'last_scan_count': info['last_scan_count'],
                'baseline': baseline,
                'last_offers_at': info['last_offers_at'],
                'active_in_db': info['active_in_db'],
            })

    severity_order = {'critical': 0, 'warning': 1}
    alerts.sort(key=lambda a: (severity_order[a['severity']], a['source']))
    return alerts


def health_status(fresh: bool, last_scan_ok: bool, alerts: List[Dict]) -> str:
    """Status dla api/health.json — najpoważniejszy problem wygrywa.

    stale (brak skanów) > failing (skan padł) > degraded (padło źródło) > ok.
    """
    if not fresh:
        return 'stale'
    if not last_scan_ok:
        return 'failing'
    if any(a['severity'] == 'critical' for a in alerts):
        return 'degraded'
    return 'ok'
