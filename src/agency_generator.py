"""Generator danych strony Agencje: data/offers.json → docs/agency_data.json.

Strona docs/agencje.html (wzorowana na profile_tracker.html z SONAR-POKOJOWY)
pokazuje śledzone agencje (ANMA, Pasjonaci, Alternatywne BN, IdsHome) w
zakładkach: lista ich ofert + statystyki + sparkline ceny.

WAŻNE: czytamy pełną bazę (PRZED deduplikacją), bo map_generator chowa oferty
agencji będące duplikatami Otodom/OLX (duplicate_of). Na stronie agencji chcemy
pokazać KOMPLET ofert danej agencji — z adnotacją „też na Otodom/OLX" (also_at).
"""

import json
from datetime import datetime
from pathlib import Path

import pytz

import paths
from agency_scrapers import AGENCY_SCRAPERS

# key → (nazwa, url) z definicji scraperów (jedno źródło prawdy)
AGENCY_META = {c.agency_key: (c.agency_name, c.base_url) for c in AGENCY_SCRAPERS}


def _compact(o: dict) -> dict:
    price = o.get('price') or {}
    loc = o.get('location') or {}
    return {
        'id': o['id'],
        'url': o.get('url'),
        'title': o.get('title'),
        'price': price.get('current'),
        'price_history': price.get('history', []),
        'price_changes': price.get('price_changes', []),
        'price_trend': price.get('price_trend'),
        'area_m2': o.get('area_m2'),
        'price_per_m2': o.get('price_per_m2'),
        'plot_type': o.get('plot_type') or 'inna',
        'district': loc.get('district'),
        'coords': loc.get('coords'),
        'coords_precision': loc.get('coords_precision'),
        'first_seen': o.get('first_seen'),
        'last_seen': o.get('last_seen'),
        'active': o.get('active', False),
        'days_active': o.get('days_active', 0),
        # gdy oferta agencji jest duplikatem (na portalu) — pokazujemy gdzie jeszcze
        'duplicate_of': o.get('duplicate_of'),
        'also_at': o.get('also_at'),
    }


def _median(xs):
    xs = sorted(v for v in xs if v is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else round((xs[m - 1] + xs[m]) / 2)


def _stats(offers):
    active = [o for o in offers if o['active']]
    perm2 = [o['price_per_m2'] for o in active if o['price_per_m2']]
    prices = [o['price'] for o in active if o['price']]
    firsts = [o['first_seen'] for o in offers if o.get('first_seen')]
    return {
        'total': len(offers),
        'active': len(active),
        'inactive': len(offers) - len(active),
        'median_per_m2': _median(perm2),
        'min_price': min(prices) if prices else None,
        'max_price': max(prices) if prices else None,
        'newest': max(firsts)[:10] if firsts else None,
        'oldest': min(firsts)[:10] if firsts else None,
        'recent_change': any((o.get('price_changes') or []) for o in active),
    }


def generate():
    with open(paths.OFFERS_JSON, 'r', encoding='utf-8') as f:
        db = json.load(f)
    all_offers = db.get('offers', [])

    agencies = {}
    for key, (name, url) in AGENCY_META.items():
        ofs = [_compact(o) for o in all_offers if o.get('source') == key]
        # aktywne najpierw, w obrębie grupy najnowsze pierwsze
        ofs.sort(key=lambda o: (o['active'], o.get('first_seen') or ''), reverse=True)
        agencies[key] = {'key': key, 'name': name, 'url': url,
                         'offers': ofs, 'stats': _stats(ofs)}

    tz = pytz.timezone('Europe/Warsaw')
    data = {
        'generated_at': datetime.now(tz).isoformat(),
        'last_scan': db.get('last_scan'),
        'next_scan': db.get('next_scan'),
        'agency_keys': list(AGENCY_META.keys()),
        'agencies': agencies,
    }

    out = Path(paths.DOCS_DIR) / 'agency_data.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    total = sum(a['stats']['total'] for a in agencies.values())
    print(f"🏢 Wygenerowano {out} ({len(agencies)} agencji, {total} ofert)")


if __name__ == "__main__":
    generate()
