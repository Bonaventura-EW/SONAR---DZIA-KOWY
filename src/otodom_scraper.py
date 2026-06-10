"""Otodom Scraper — działki na sprzedaż w Lublinie.

Otodom (Next.js) osadza w HTML pełny stan JSON (`__NEXT_DATA__`):
- listing: tytuł, cena, powierzchnia, cena za m², ulica, dzielnica
  (reverseGeocoding), zdjęcia, paginacja — ale BEZ współrzędnych,
- strona szczegółów: dokładne współrzędne GPS (`ad.location.coordinates`),
  pełny opis i charakterystykę (m.in. typ działki).

Strategia: listing dla wszystkich ofert + strona szczegółów tylko dla NOWYCH
ofert (znane mają już coords w bazie — patrz `known_offers` w `scrape()`).
"""

import json
import re
import time
import random
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from cid import otodom_offer_id
from olx_scraper import strip_html  # ten sam helper czyszczenia HTML


LISTING_URL = (
    "https://www.otodom.pl/pl/wyniki/sprzedaz/dzialka/lubelskie/lublin/lublin/lublin"
    "?ownerTypeSingleSelect=ALL&limit=72"
)
OFFER_BASE_URL = "https://www.otodom.pl/pl/oferta/"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pl,en-US;q=0.7,en;q=0.3',
}

_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)

# Mapowanie `type` z charakterystyki Otodom na wspólne nazwy typów działek
PLOT_TYPE_MAP = {
    'building': 'budowlana',
    'commercial': 'inwestycyjna',
    'agriculturalBuilding': 'rolno-budowlana',
    'agricultural': 'rolna',
    'recreational': 'rekreacyjna',
    'forest': 'leśna',
    'habitat': 'siedliskowa',
}


def extract_next_data(html: str) -> Optional[dict]:
    """Wyciąga i parsuje JSON `__NEXT_DATA__` ze strony Otodom."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        print(f"⚠️ Otodom: błąd parsowania __NEXT_DATA__: {e}")
        return None


def _district_from_geocoding(location: dict) -> Optional[str]:
    """Wyciąga nazwę dzielnicy z reverseGeocoding listingu Otodom."""
    locations = ((location or {}).get('reverseGeocoding') or {}).get('locations') or []
    for loc in locations:
        if loc.get('locationLevel') == 'district':
            return loc.get('name')
    return None


def normalize_item(item: dict) -> Optional[Dict]:
    """Normalizuje pozycję listingu Otodom do wspólnego schematu."""
    numeric_id = item.get('id')
    slug = item.get('slug')
    if not numeric_id or not slug:
        return None

    total_price = (item.get('totalPrice') or {}).get('value')
    if not isinstance(total_price, (int, float)):
        return None  # oferty z ukrytą ceną pomijamy
    price = int(total_price)

    area = item.get('areaInSquareMeters') or item.get('terrainAreaInSquareMeters')
    per_m2 = (item.get('pricePerSquareMeter') or {}).get('value')
    if per_m2 is None and area:
        per_m2 = round(price / area, 2)

    location = item.get('location') or {}
    address = location.get('address') or {}
    street = ((address.get('street') or {}).get('name') or '').strip() or None
    city = ((address.get('city') or {}).get('name') or '').strip() or None

    images = item.get('images') or []
    image = images[0].get('medium') if images else None

    return {
        'id': otodom_offer_id(numeric_id),
        'source': 'otodom',
        'url': OFFER_BASE_URL + slug,
        'title': (item.get('title') or '').strip(),
        'price': price,
        'area_m2': float(area) if area else None,
        'price_per_m2': float(per_m2) if per_m2 else None,
        'plot_type': None,  # typ jest dopiero na stronie szczegółów
        'location': {
            'city': city,
            'district': _district_from_geocoding(location),
            'street': street,
            'coords': None,  # coords są dopiero na stronie szczegółów
            'coords_precision': None,
        },
        'description': (item.get('shortDescription') or '').strip(),
        'is_private_owner': bool(item.get('isPrivateOwner')),
        'image': image,
        'created_at': item.get('createdAtFirst') or item.get('dateCreated'),
    }


class OtodomDzialkiScraper:
    def __init__(self, delay_range=(0.5, 1.2), max_workers: int = 4):
        self.delay_min, self.delay_max = delay_range
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _fetch(self, url: str) -> Optional[str]:
        try:
            r = self.session.get(url, timeout=20)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            print(f"❌ Otodom: błąd pobierania {url}: {e}")
            return None

    def _scrape_listing(self, max_pages: int) -> List[Dict]:
        offers: List[Dict] = []
        seen_ids = set()
        total_pages = 1

        for page in range(1, max_pages + 1):
            if page > total_pages:
                break
            html = self._fetch(f"{LISTING_URL}&page={page}")
            if not html:
                break
            data = extract_next_data(html)
            if not data:
                print(f"⚠️ Otodom: brak __NEXT_DATA__ na stronie {page}")
                break

            search_ads = (((data.get('props') or {}).get('pageProps') or {})
                          .get('data') or {}).get('searchAds') or {}
            items = search_ads.get('items') or []
            pagination = search_ads.get('pagination') or {}
            total_pages = pagination.get('totalPages') or total_pages

            print(f"📄 Otodom strona {page}/{total_pages}: {len(items)} ogłoszeń "
                  f"(łącznie w serwisie: {pagination.get('totalItems')})")

            for item in items:
                offer = normalize_item(item)
                if not offer or offer['id'] in seen_ids:
                    continue
                seen_ids.add(offer['id'])
                offers.append(offer)

            if not items:
                break
            time.sleep(random.uniform(self.delay_min, self.delay_max))

        return offers

    def fetch_details(self, offer: Dict) -> Dict:
        """Dociąga ze strony szczegółów: dokładne coords, pełny opis, typ działki."""
        time.sleep(random.uniform(self.delay_min, self.delay_max))
        html = self._fetch(offer['url'])
        if not html:
            return offer
        data = extract_next_data(html)
        if not data:
            return offer

        ad = ((data.get('props') or {}).get('pageProps') or {}).get('ad') or {}
        location = ad.get('location') or {}

        coords = location.get('coordinates') or {}
        if coords.get('latitude') and coords.get('longitude'):
            offer['location']['coords'] = {
                'lat': coords['latitude'], 'lon': coords['longitude']
            }
            offer['location']['coords_precision'] = 'exact'

        description = strip_html(ad.get('description') or '')
        if len(description) > len(offer.get('description') or ''):
            offer['description'] = description

        for char in ad.get('characteristics') or []:
            if char.get('key') == 'type':
                # wartość bywa wielokrotna, np. "building,commercial" — bierzemy
                # pierwszy typ który umiemy zmapować
                values = (char.get('value') or '').split(',')
                offer['plot_type'] = next(
                    (PLOT_TYPE_MAP[v] for v in values if v in PLOT_TYPE_MAP), 'inna')
                break

        return offer

    def scrape(self, max_pages: int = 10, known_offers: Dict = None) -> List[Dict]:
        """Pobiera listing + szczegóły (tylko dla ofert nieznanych bazie).

        Args:
            known_offers: {offer_id: {'coords': ..., 'plot_type': ...,
                           'description': ...}} — dane z poprzednich skanów,
                           pozwalają pominąć stronę szczegółów.
        """
        known_offers = known_offers or {}
        print("🔍 Otodom: scraping działek (Lublin)...")
        offers = self._scrape_listing(max_pages)
        print(f"✅ Otodom: listing dał {len(offers)} ofert")

        to_fetch = []
        for offer in offers:
            known = known_offers.get(offer['id'])
            if known and known.get('coords'):
                offer['location']['coords'] = known['coords']
                offer['location']['coords_precision'] = known.get('coords_precision', 'exact')
                offer['plot_type'] = known.get('plot_type') or offer['plot_type']
                if known.get('description'):
                    offer['description'] = known['description']
            else:
                to_fetch.append(offer)

        if to_fetch:
            print(f"⚡ Otodom: pobieram szczegóły {len(to_fetch)} nowych ofert "
                  f"({self.max_workers} wątków)...")
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self.fetch_details, o): o for o in to_fetch}
                done = 0
                for future in as_completed(futures):
                    done += 1
                    try:
                        future.result()
                    except Exception as e:  # pojedyncza oferta nie wali skanu
                        print(f"\n⚠️ Otodom: błąd szczegółów: {e}")
                    print(f"\r   Postęp: [{done}/{len(to_fetch)}]", end='', flush=True)
            print()
        else:
            print("✅ Otodom: wszystkie oferty znane (pominięto szczegóły)")

        print(f"✅ Otodom: zebrano {len(offers)} ofert\n")
        return offers


if __name__ == "__main__":
    scraper = OtodomDzialkiScraper(delay_range=(0.3, 0.8))
    result = scraper.scrape(max_pages=1)
    print(f"Łącznie: {len(result)}")
    if result:
        for k, v in result[0].items():
            print(f"  {k}: {str(v)[:100]}")
