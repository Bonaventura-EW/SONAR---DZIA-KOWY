"""Generator statycznego API: data/offers.json → docs/api/*.json.

Endpointy (GitHub Pages, konwencja z SONAR-MIESZKANIOWY):
- api/status.json  — statystyki bieżącego stanu bazy + czas skanów
- api/offers.json  — kompaktowa lista aktywnych ofert (dedup OLX↔Otodom)
- api/history.json — historia skanów (z data/scan_history.json)
- api/health.json  — prosty healthcheck (świeżość ostatniego skanu)
"""

import json
from datetime import datetime
from pathlib import Path

import pytz

import paths
from map_generator import build_map_offer

API_DIR = Path(paths.DOCS_DIR) / "api"
STALE_AFTER_HOURS = 26  # 2 skany/dzień → >26 h bez skanu = problem


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

    write('status.json', {
        'generated_at': now.isoformat(),
        'last_scan': db.get('last_scan'),
        'next_scan': db.get('next_scan'),
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

    history = {}
    history_path = Path(paths.SCAN_HISTORY_JSON)
    if history_path.exists():
        with open(history_path, 'r', encoding='utf-8') as f:
            history = json.load(f)
    write('history.json', {
        'generated_at': now.isoformat(),
        'scans': history.get('scans', [])[-50:],
    })

    last_scan = db.get('last_scan')
    hours_since = None
    if last_scan:
        hours_since = (now - datetime.fromisoformat(last_scan)).total_seconds() / 3600
    write('health.json', {
        'status': 'ok' if hours_since is not None and hours_since < STALE_AFTER_HOURS else 'stale',
        'generated_at': now.isoformat(),
        'last_scan': last_scan,
        'hours_since_last_scan': round(hours_since, 1) if hours_since is not None else None,
    })

    print(f"🔌 Wygenerowano API: {API_DIR} (status, offers[{len(active)}], history, health)")


if __name__ == "__main__":
    generate()
