"""OLX Scraper — działki na sprzedaż w Lublinie.

W odróżnieniu od SONAR-MIESZKANIOWY/POKOJOWY nie parsuje HTML kart ogłoszeń:
OLX osadza w listingu pełny stan JSON (`window.__PRERENDERED_STATE__`),
który zawiera dla każdego ogłoszenia m.in.:
- przybliżone współrzędne GPS (`map.lat/lon`, radius ~1 km),
- cenę (`price.regularPrice.value`),
- powierzchnię i cenę za m² (`params`),
- typ działki (budowlana / inwestycyjna / rolno-budowlana),
- pełny opis (HTML).

Dzięki temu nie potrzebujemy wchodzić w strony szczegółów ani geokodować.
"""

import json
import re
import time
import random
from typing import Dict, List, Optional

import requests

from cid import olx_offer_id


LISTING_URL = (
    "https://www.olx.pl/nieruchomosci/dzialki/sprzedaz/lublin/q-dzia%C5%82ka/"
    "?search%5Bfilter_enum_type%5D%5B0%5D=dzialki-budowlane"
    "&search%5Bfilter_enum_type%5D%5B1%5D=dzialki-inwestycyjne"
    "&search%5Bfilter_enum_type%5D%5B2%5D=dzialki-rolno-budowlane"
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pl,en-US;q=0.7,en;q=0.3',
}

_STATE_RE = re.compile(r'window\.__PRERENDERED_STATE__\s*=\s*"(.*)";')
_TAG_RE = re.compile(r'<[^>]+>')

# Mapowanie normalizedValue z OLX na wspólne nazwy typów działek
PLOT_TYPE_MAP = {
    'dzialki-budowlane': 'budowlana',
    'dzialki-inwestycyjne': 'inwestycyjna',
    'dzialki-rolno-budowlane': 'rolno-budowlana',
    'dzialki-rolne': 'rolna',
    'dzialki-rekreacyjne': 'rekreacyjna',
    'dzialki-lesne': 'leśna',
    'dzialki-siedliskowe': 'siedliskowa',
}


def strip_html(text: str) -> str:
    """Usuwa tagi HTML z opisu (OLX trzyma opis jako HTML)."""
    if not text:
        return ''
    text = text.replace('</p>', '\n').replace('<br>', '\n').replace('<br/>', '\n')
    return _TAG_RE.sub('', text).strip()


def decode_prerendered_state(html: str) -> Optional[dict]:
    """Wyciąga i dekoduje `window.__PRERENDERED_STATE__` z HTML listingu.

    Stan jest zapisany jako escapowany string JS. Po unicode_escape polskie
    znaki są zepsute (bajty UTF-8 zinterpretowane jako latin-1) — naprawiamy
    re-enkodowaniem latin-1 → utf-8.
    """
    m = _STATE_RE.search(html)
    if not m:
        return None
    raw = m.group(1).encode('utf-8').decode('unicode_escape')
    try:
        raw = raw.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass  # stan był już poprawnym tekstem
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"⚠️ OLX: nie udało się sparsować __PRERENDERED_STATE__: {e}")
        return None


def _param(ad: dict, key: str) -> Optional[str]:
    """Zwraca normalizedValue parametru ogłoszenia OLX o danym kluczu."""
    for p in ad.get('params') or []:
        if p.get('key') == key:
            return p.get('normalizedValue') or p.get('value')
    return None


def normalize_ad(ad: dict) -> Optional[Dict]:
    """Normalizuje ogłoszenie OLX do wspólnego schematu SONARA DZIAŁKOWEGO."""
    url = ad.get('url') or ''
    if not url:
        return None

    price = None
    price_info = ad.get('price') or {}
    regular = price_info.get('regularPrice') or {}
    if isinstance(regular.get('value'), (int, float)):
        price = int(regular['value'])
    if not price:
        return None  # bez ceny oferta jest bezużyteczna

    area = None
    raw_area = _param(ad, 'm')
    try:
        area = float(raw_area) if raw_area else None
    except ValueError:
        area = None

    per_m2 = None
    raw_per_m2 = _param(ad, 'price_per_m')
    try:
        per_m2 = float(raw_per_m2) if raw_per_m2 else None
    except ValueError:
        pass
    if per_m2 is None and area:
        per_m2 = round(price / area, 2)

    plot_type = PLOT_TYPE_MAP.get(_param(ad, 'type') or '', 'inna')

    coords = None
    ad_map = ad.get('map') or {}
    if ad_map.get('lat') and ad_map.get('lon'):
        coords = {'lat': ad_map['lat'], 'lon': ad_map['lon']}

    location = ad.get('location') or {}
    photos = ad.get('photos') or []

    return {
        'id': olx_offer_id(url),
        'source': 'olx',
        'url': url.split('?')[0],
        'title': ad.get('title', '').strip(),
        'price': price,
        'area_m2': area,
        'price_per_m2': per_m2,
        'plot_type': plot_type,
        'location': {
            'city': location.get('cityName'),
            'district': location.get('districtName'),
            'street': None,  # OLX nie podaje ulicy w listingu
            'coords': coords,
            'coords_precision': 'approx',  # OLX rozmywa pinezkę (radius ~1 km)
        },
        'description': strip_html(ad.get('description', '')),
        'is_private_owner': not ad.get('isBusiness', False),
        'image': photos[0] if photos else None,
        'created_at': ad.get('createdTime'),
    }


class OLXDzialkiScraper:
    def __init__(self, delay_range=(1.0, 2.0)):
        self.delay_min, self.delay_max = delay_range
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _fetch(self, url: str) -> Optional[str]:
        try:
            r = self.session.get(url, timeout=20)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            print(f"❌ OLX: błąd pobierania {url}: {e}")
            return None

    def scrape(self, max_pages: int = 10) -> List[Dict]:
        """Pobiera wszystkie strony listingu i zwraca znormalizowane oferty."""
        print("🔍 OLX: scraping działek (Lublin)...")
        offers: List[Dict] = []
        seen_ids = set()

        for page in range(1, max_pages + 1):
            url = LISTING_URL if page == 1 else f"{LISTING_URL}&page={page}"
            html = self._fetch(url)
            if not html:
                break

            state = decode_prerendered_state(html)
            if not state:
                print(f"⚠️ OLX: brak stanu JSON na stronie {page}")
                break

            listing = (state.get('listing') or {}).get('listing') or {}
            ads = listing.get('ads') or []
            total = listing.get('totalElements')
            print(f"📄 OLX strona {page}: {len(ads)} ogłoszeń (łącznie w serwisie: {total})")

            new_on_page = 0
            for ad in ads:
                # OLX dokleja na końcu wyniki "z okolicy" — pilnujemy miasta
                city = ((ad.get('location') or {}).get('cityNormalizedName') or '').lower()
                if city and city != 'lublin':
                    continue
                offer = normalize_ad(ad)
                if not offer or offer['id'] in seen_ids:
                    continue
                seen_ids.add(offer['id'])
                offers.append(offer)
                new_on_page += 1

            # FIX 2026-06-11: koniec paginacji TYLKO gdy strona jest pusta —
            # strona z samymi powtórkami/wynikami "z okolicy" nie może ucinać
            # kolejnych stron (limit max_pages i tak zamyka pętlę)
            if not ads:
                break
            if total and len(seen_ids) >= total:
                break
            if new_on_page == 0 and page > 1:
                # strona 2+ bez żadnej nowej oferty = koniec (OLX powtarza
                # ostatnią stronę dla page > max)
                break

            time.sleep(random.uniform(self.delay_min, self.delay_max))

        print(f"✅ OLX: zebrano {len(offers)} ofert\n")
        return offers


if __name__ == "__main__":
    scraper = OLXDzialkiScraper(delay_range=(0.5, 1.0))
    result = scraper.scrape(max_pages=5)
    print(f"Łącznie: {len(result)}")
    if result:
        sample = result[0]
        for k, v in sample.items():
            print(f"  {k}: {str(v)[:100]}")
