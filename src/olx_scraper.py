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

try:  # FIX 2026-08-24: impersonacja TLS — patrz komentarz przy IMPERSONATE_PROFILES
    from curl_cffi import requests as impersonate_requests
except ImportError:  # środowisko bez curl_cffi — scraper zejdzie na gołe requests
    impersonate_requests = None

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

# FIX 2026-08-24: OLX (CloudFront/WAF) od 2026-08-11 odrzucał KAŻDY request
# biblioteki `requests` błędem 403 — niezależnie od nagłówków. Blokada idzie po
# fingerprincie TLS (JA3): handshake pythonowego OpenSSL nie wygląda jak
# przeglądarka. curl_cffi odtwarza handshake prawdziwego Chrome'a/Safari i ten
# sam URL wraca z kodem 200. Profile próbujemy po kolei — nowsze buildy używają
# rozszerzeń TLS, które bywają ucinane przez firmowe proxy/MITM.
IMPERSONATE_PROFILES = ('chrome131', 'chrome124', 'chrome110', 'safari17_0', 'edge101')

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


# błędy sieciowe obu warstw HTTP (requests + curl_cffi)
_FETCH_ERRORS = (requests.RequestException,)
if impersonate_requests is not None:
    _FETCH_ERRORS += (impersonate_requests.RequestsError,
                      impersonate_requests.exceptions.HTTPError)


class OLXDzialkiScraper:
    def __init__(self, delay_range=(1.0, 2.0), impersonate_profiles=IMPERSONATE_PROFILES):
        self.delay_min, self.delay_max = delay_range
        self._profiles = list(impersonate_profiles) if impersonate_requests else []
        self.impersonate = None
        self.session = self._new_session()

    def _new_session(self):
        """Sesja z kolejnym profilem impersonacji; po ich wyczerpaniu — gołe
        requests (lepsze niż nic, gdy curl_cffi nie jest zainstalowane)."""
        if self._profiles:
            self.impersonate = self._profiles.pop(0)
            return impersonate_requests.Session(impersonate=self.impersonate)
        self.impersonate = None
        session = requests.Session()
        session.headers.update(HEADERS)
        return session

    def _switch_session(self) -> bool:
        """Przełącza na kolejny profil. False = nie ma już czego próbować."""
        if not self._profiles and self.impersonate is None:
            return False
        try:
            self.session.close()
        except Exception:  # zamknięcie sesji nie może wywrócić skanu
            pass
        self.session = self._new_session()
        print(f"🔁 OLX: ponawiam jako "
              f"{self.impersonate or 'requests (bez impersonacji)'}")
        return True

    def _fetch(self, url: str) -> Optional[str]:
        while True:
            try:
                r = self.session.get(url, timeout=20)
                r.raise_for_status()
                return r.text
            except _FETCH_ERRORS as e:
                client = self.impersonate or 'requests'
                print(f"❌ OLX [{client}]: błąd pobierania {url}: {e}")
                if not self._switch_session():
                    return None

    def scrape(self, max_pages: int = 10) -> List[Dict]:
        """Pobiera wszystkie strony listingu i zwraca znormalizowane oferty."""
        print(f"🔍 OLX: scraping działek (Lublin), klient: "
              f"{self.impersonate or 'requests (bez impersonacji TLS)'}...")
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
