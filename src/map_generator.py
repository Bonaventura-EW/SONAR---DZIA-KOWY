"""Generator danych mapy: data/offers.json → docs/data.json.

Frontend (docs/index.html + assets/script.js) czyta docs/data.json
serwowany przez GitHub Pages.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytz

import paths

DESCRIPTION_LIMIT = 1200  # frontend pokazuje skrót, pełny opis jest pod linkiem
TZ = pytz.timezone('Europe/Warsaw')


def build_map_offer(offer: dict) -> dict:
    """Kompaktowa wersja oferty dla frontendu."""
    loc = offer.get('location') or {}
    price = offer.get('price') or {}
    description = (offer.get('description') or '')[:DESCRIPTION_LIMIT]
    return {
        'id': offer['id'],
        'source': offer.get('source'),
        'url': offer.get('url'),
        'title': offer.get('title'),
        'price': price.get('current'),
        'previous_price': price.get('previous_price'),
        'price_trend': price.get('price_trend'),
        'price_history': price.get('history', []),
        # FIX 2026-06-14: znaczniki czasu zmian ceny (do wykresu „cena w czasie"
        # na docs/oferty.html). history to same wartości — bez dat nie da się
        # narysować osi czasu.
        'price_changes': price.get('price_changes', []),
        'price_changed_at': price.get('price_changed_at'),
        'area_m2': offer.get('area_m2'),
        'price_per_m2': offer.get('price_per_m2'),
        'plot_type': offer.get('plot_type') or 'inna',
        'district': loc.get('district'),
        'street': loc.get('street'),
        'coords': loc.get('coords'),
        'coords_precision': loc.get('coords_precision'),
        'description': description,
        'is_private_owner': offer.get('is_private_owner'),
        'is_agency': offer.get('is_agency', False),
        'agency_name': offer.get('agency_name'),
        'image': offer.get('image'),
        'first_seen': offer.get('first_seen'),
        'last_seen': offer.get('last_seen'),
        'active': offer.get('active', False),
        'days_active': offer.get('days_active', 0),
        'also_at': offer.get('also_at'),
        'promoted': offer.get('promoted', False),  # płatne wyróżnienie na listingu OLX
    }


def _scan_days() -> set:
    """Dni z ZAKOŃCZONYM skanem wg data/scan_history.json.

    Dzień bez skanu (awaria Actions, blokada OLX) miałby zero wyróżnień i
    rysowałby się jak realne załamanie metryki — takie dni oznaczamy jako lukę,
    nie zero. Brak/uszkodzony plik = pusty zbiór (wtedy lukami są tylko dni
    spoza dni z wyróżnieniami).
    """
    try:
        with open(paths.SCAN_HISTORY_JSON, 'r', encoding='utf-8') as f:
            history = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    return {(scan.get('timestamp') or '')[:10]
            for scan in history.get('scans', [])
            if scan.get('status') == 'completed' and scan.get('timestamp')}


def build_promoted(all_offers: list, scan_days: set) -> dict:
    """Dzienny szereg płatnie wyróżnionych ofert OLX (płatne 'promoted').

    Źródło: `promoted_dates` w offers.json (main._track_promoted, max 1/dzień).
    To metryka STANU — ile ofert jest danego dnia wyróżnianych — więc suma po
    dniach nie ma sensu; front pokazuje serię dzienną i bieżący udział w rynku.
    Historia zaczyna się w dniu wdrożenia detekcji (wyróżnienia nie da się
    odtworzyć wstecz), więc seria startuje od pierwszego dnia z danymi, nie od
    początku bazy. Dni bez skanu = luka (None), nie zero.

    Zwraca None, gdy nie ma jeszcze żadnej daty wyróżnienia (świeżo po wdrożeniu).
    """
    counts: dict = {}
    for o in all_offers:
        for pd in o.get('promoted_dates') or []:
            key = str(pd)[:10]
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None

    today = datetime.now(TZ).strftime('%Y-%m-%d')
    start = date.fromisoformat(min(counts))
    end = date.fromisoformat(max(today, max(counts)))
    scanned = set(scan_days) | set(counts)  # dzień z wyróżnieniem był skanowany

    daily = []
    day = start
    while day <= end:
        key = day.isoformat()
        daily.append([key, counts.get(key, 0) if key in scanned else None])
        day += timedelta(days=1)

    # udział „teraz": wyróżnione wśród AKTYWNYCH ofert OLX (tylko one to niosą)
    olx_active = [o for o in all_offers
                  if o.get('active') and o.get('source') == 'olx']
    promoted_now = sum(1 for o in olx_active if o.get('promoted'))
    current_share = (round(100 * promoted_now / len(olx_active), 1)
                     if olx_active else None)
    return {
        'daily': daily,
        'current': promoted_now,
        'current_share': current_share,
        'start': start.isoformat(),
    }


def generate():
    with open(paths.OFFERS_JSON, 'r', encoding='utf-8') as f:
        db = json.load(f)

    all_offers = db.get('offers', [])
    # Deduplikacja OLX↔Otodom: ukrywamy ofertę OLX gdy jej odpowiednik z Otodom
    # (duplicate_of) jest aktywny — na mapie zostaje jedna pinezka z oboma linkami
    active_ids = {o['id'] for o in all_offers if o.get('active')}
    deduped = [o for o in all_offers
               if not (o.get('duplicate_of') and o['duplicate_of'] in active_ids)]
    hidden = len(all_offers) - len(deduped)
    if hidden:
        print(f"🔗 Ukryto {hidden} duplikatów (ta sama działka w kilku źródłach)")

    offers = [build_map_offer(o) for o in deduped]
    active = [o for o in offers if o['active']]
    per_m2_values = sorted(o['price_per_m2'] for o in active if o['price_per_m2'])

    def percentile(values, p):
        if not values:
            return None
        idx = min(len(values) - 1, int(round(p * (len(values) - 1))))
        return values[idx]

    data = {
        'generated_at': datetime.now(TZ).isoformat(),
        'last_scan': db.get('last_scan'),
        'next_scan': db.get('next_scan'),
        'promoted': build_promoted(all_offers, _scan_days()),
        'stats': {
            'total': len(offers),
            'active': len(active),
            'active_with_coords': sum(1 for o in active if o['coords']),
            'median_price_per_m2': percentile(per_m2_values, 0.5),
            # progi do kolorowania pinezek wg ceny za m² — 9 decyli = 10 stopni
            # (zielony→fioletowy); QUANTILE_COLORS w script.js musi mieć 10 kolorów
            'per_m2_quantiles': [percentile(per_m2_values, q)
                                 for q in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)],
        },
        'offers': offers,
    }

    out = Path(paths.DOCS_DATA_JSON)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    print(f"🗺️ Wygenerowano {out} ({len(active)} aktywnych / {len(offers)} łącznie)")
    promo = data['promoted']
    if promo:
        share = f" ({promo['current_share']}% ofert OLX)" if promo['current_share'] is not None else ""
        print(f"   ⭐ Płatnie wyróżnione teraz: {promo['current']}{share}; "
              f"historia od {promo['start']}")


if __name__ == "__main__":
    generate()
