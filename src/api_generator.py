"""Generator statycznego API: data/offers.json → docs/api/*.json.

Endpointy (GitHub Pages, konwencja z SONAR-MIESZKANIOWY):
- api/status.json  — statystyki bieżącego stanu bazy + czas skanów
- api/offers.json  — kompaktowa lista aktywnych ofert (dedup OLX↔Otodom)
- api/history.json — historia skanów (z data/scan_history.json)
- api/health.json  — healthcheck: świeżość skanu + ALARMY awarii źródeł
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pytz

import paths
from map_generator import build_map_offer
from source_health import (build_source_alerts, group_active_by_source,
                           health_status, summarize_sources)

API_DIR = Path(paths.DOCS_DIR) / "api"
STALE_AFTER_HOURS = 26  # 2 skany/dzień → >26 h bez skanu = problem
HISTORY_SCANS = 6       # api/history.json trzyma 6 ostatnich skanów


def generate():
    tz = pytz.timezone('Europe/Warsaw')
    now = datetime.now(tz)

    with open(paths.OFFERS_JSON, 'r', encoding='utf-8') as f:
        db = json.load(f)

    all_offers = db.get('offers', [])
    active_ids = {o['id'] for o in all_offers if o.get('active')}
    active = [o for o in all_offers
              if o.get('active')
              and not (o.get('duplicate_of') and o['duplicate_of'] in active_ids)]

    per_m2 = sorted(o.get('price_per_m2') for o in active if o.get('price_per_m2'))
    by_source = {}
    by_type = {}
    for o in active:
        by_source[o['source']] = by_source.get(o['source'], 0) + 1
        t = o.get('plot_type') or 'inna'
        by_type[t] = by_type.get(t, 0) + 1

    API_DIR.mkdir(parents=True, exist_ok=True)

    def write(name, payload):
        with open(API_DIR / name, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))

    # historia skanów — jedno wczytanie: status, alarmy źródeł i history.json
    raw_scans = []
    history_path = Path(paths.SCAN_HISTORY_JSON)
    if history_path.exists():
        with open(history_path, 'r', encoding='utf-8') as f:
            raw_scans = json.load(f).get('scans', [])
    last_entry = raw_scans[-1] if raw_scans else {}

    # FIX 2026-08-24: ALARM gdy źródło przestaje zwracać oferty. Skan z
    # martwym OLX-em (403 CloudFront od 2026-08-11) kończył się jako
    # 'completed', a health.json raportował 'ok' przez 26 skanów z rzędu.
    sources = summarize_sources(raw_scans, group_active_by_source(all_offers))
    alerts = build_source_alerts(sources)

    write('status.json', {
        'generated_at': now.isoformat(),
        'last_scan': db.get('last_scan'),
        'next_scan': db.get('next_scan'),
        'last_scan_status': last_entry.get('status', 'completed') if last_entry else None,
        'last_scan_success': last_entry.get('status', 'completed') == 'completed' if last_entry else None,
        'last_scan_new_offers': last_entry.get('new'),
        'last_scan_disappeared_offers': last_entry.get('deactivated'),
        'last_scan_duration_s': last_entry.get('duration_s'),
        'alerts': alerts,
        'active_offers': len(active),
        'total_in_db': len(all_offers),
        'median_price_per_m2': per_m2[len(per_m2) // 2] if per_m2 else None,
        'by_source': by_source,
        'by_plot_type': by_type,
    })

    write('offers.json', {
        'generated_at': now.isoformat(),
        'count': len(active),
        'offers': [build_map_offer(o) for o in active],
    })

    # history.json — 6 ostatnich skanów (nowe nadpisują stare), format
    # analogiczny do SONAR-POKOJOWY/MIESZKANIOWY: status skanu + bilans ofert
    def format_duration(seconds):
        if seconds is None:
            return None
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s" if m else f"{s}s"

    api_scans = []
    # od najnowszego; do bilansu aktywnych potrzebny poprzedni skan
    for i in range(len(raw_scans) - 1, max(len(raw_scans) - 1 - HISTORY_SCANS, -1), -1):
        scan = raw_scans[i]
        prev = raw_scans[i - 1] if i > 0 else None
        status = scan.get('status', 'completed')
        success = status == 'completed'
        new = scan.get('new', 0)
        disappeared = scan.get('deactivated', 0)
        active_count = scan.get('active')
        # zmiana liczby aktywnych vs poprzedni udany skan
        delta = None
        if success and prev and prev.get('status', 'completed') == 'completed' \
           and active_count is not None and prev.get('active') is not None:
            delta = active_count - prev['active']

        scan_time = ''
        try:
            scan_time = datetime.fromisoformat(scan['timestamp']).strftime('%H:%M')
        except (KeyError, ValueError):
            pass

        if success:
            title = f"✅ Skan {scan_time} — +{new} nowych / -{disappeared} znikło"
            body = (f"Pojawiło się {new} nowych, zniknęło {disappeared} "
                    f"ofert działek w Lublinie")
        else:
            title = f"❌ Skan {scan_time} — NIEUDANY"
            body = scan.get('error') or 'Skan zakończony błędem'

        api_scans.append({
            'timestamp': scan.get('timestamp'),
            'scanTimeFormatted': scan_time,
            'uiStatus': 'success' if success else 'failure',
            'rawStatus': status,
            'failureReason': scan.get('error') if not success else None,
            'durationSeconds': scan.get('duration_s'),
            'durationFormatted': format_duration(scan.get('duration_s')),
            'notification': {'title': title, 'body': body},
            'offers': {
                'new': new,
                'disappeared': disappeared,
                'updated': scan.get('updated', 0),
                'active': active_count,
                'activeDelta': delta,
                'totalInDb': scan.get('total_in_db'),
                'bySource': {
                    'olx': scan.get('scraped_olx'),
                    'otodom': scan.get('scraped_otodom'),
                    'adresowo': scan.get('scraped_adresowo'),
                    'agencies': scan.get('scraped_agencies'),
                },
            },
        })

    write('history.json', {
        'system': 'sonar-dzialkowy',
        'generated_at': now.isoformat(),
        'count': len(api_scans),
        'scans': api_scans,
    })

    last_scan = db.get('last_scan')
    hours_since = None
    if last_scan:
        hours_since = (now - datetime.fromisoformat(last_scan)).total_seconds() / 3600
    fresh = hours_since is not None and hours_since < STALE_AFTER_HOURS
    last_ok = last_entry.get('status', 'completed') == 'completed' if last_entry else True
    write('health.json', {
        'status': health_status(fresh, last_ok, alerts),
        'generated_at': now.isoformat(),
        'last_scan': last_scan,
        'last_scan_status': last_entry.get('status') if last_entry else None,
        'hours_since_last_scan': round(hours_since, 1) if hours_since is not None else None,
        'alerts': alerts,
        'sources': sources,
    })

    print(f"🔌 Wygenerowano API: {API_DIR} (status, offers[{len(active)}], history, health)")
    _report_alerts(alerts)


def _report_alerts(alerts):
    """Alarmy na stdout, a w GitHub Actions też jako annotacje runa — awaria
    źródła ma być widoczna bez zaglądania w JSON."""
    if not alerts:
        return
    in_actions = os.environ.get('GITHUB_ACTIONS') == 'true'
    for alert in alerts:
        icon = '🚨' if alert['severity'] == 'critical' else '⚠️'
        print(f"{icon} ALARM [{alert['source']}]: {alert['message']}")
        if in_actions:
            level = 'error' if alert['severity'] == 'critical' else 'warning'
            print(f"::{level} title=SONAR: awaria źródła {alert['source']}::"
                  f"{alert['message']}")


if __name__ == "__main__":
    generate()
