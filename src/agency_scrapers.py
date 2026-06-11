"""Scrapery stron lubelskich agencji nieruchomości (działki na sprzedaż).

Agencje i ich silniki:
- ANMA (anma.lublin.pl) — CMS Galactica Virgo
- Pasjonaci Nieruchomości (pasjonacinieruchomosci.pl) — CMS Galactica Virgo
  (specjalizują się w działkach; agresywna ochrona antybotowa → scraper
  toleruje 503 i po prostu zwraca to, co udało się pobrać)
- Alternatywne Biuro Nieruchomości (alternatywnebn.pl) — WordPress
  (wymaga rozgrzania sesji wejściem na stronę główną)

Wspólne cechy:
- Virgo koduje cenę/powierzchnię/lokalizację W SLUGU oferty:
  `dzialki-na-sprzedaz-{cena}zl-{powierzchnia}m2-{gmina}-{miejscowosc}(-o){id}`
- żadna agencja nie publikuje współrzędnych → oferty dostają coords z
  location_refiner (ulica z opisu) albo trafiają do listy „bez lokalizacji"
- bierzemy WYŁĄCZNIE oferty z Lublina (miasto), jak w OLX/Otodom
- strony szczegółów pobieramy tylko dla ofert nieznanych bazie (known_offers)
"""

import re
import time
import random
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8',
}

# slug Virgo: dzialki-na-sprzedaz-275000zl-1000m2-konopnica-motycz-o6988570
# (Pasjonaci kończą /1234567 zamiast -o1234567)
_VIRGO_SLUG_RE = re.compile(
    r'dzialki-na-sprzedaz-(\d+)zl-(\d+)m2-([a-z0-9\-]+?)(?:-o(\d+)|/(\d+))(?:$|["\?])')

_WS_RE = re.compile(r'\s+')


def _clean(text: str) -> str:
    return _WS_RE.sub(' ', text or '').strip()


class BaseAgencyScraper:
    """Wspólne: sesja HTTP, delay, normalizacja schematu oferty."""

    agency_key = ''     # np. 'anma' (prefiks ID i klucz źródła)
    agency_name = ''    # np. 'ANMA' (etykieta na mapie)
    base_url = ''

    def __init__(self, delay_range=(2.0, 4.0)):
        self.delay_min, self.delay_max = delay_range
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _sleep(self):
        time.sleep(random.uniform(self.delay_min, self.delay_max))

    def _fetch(self, url: str) -> Optional[str]:
        try:
            r = self.session.get(url, timeout=25)
            if r.status_code != 200:
                print(f"⚠️ {self.agency_name}: HTTP {r.status_code} dla {url}")
                return None
            return r.text
        except requests.RequestException as e:
            print(f"❌ {self.agency_name}: błąd pobierania {url}: {e}")
            return None

    def _base_offer(self, offer_id: str, url: str) -> Dict:
        return {
            'id': f"{self.agency_key}:{offer_id}",
            'source': self.agency_key,
            'is_agency': True,
            'agency_name': self.agency_name,
            'url': url,
            'title': '',
            'price': None,
            'area_m2': None,
            'price_per_m2': None,
            'plot_type': 'inna',
            'location': {'city': 'Lublin', 'district': None, 'street': None,
                         'coords': None, 'coords_precision': None},
            'description': '',
            'is_private_owner': False,  # agencja z definicji
            'image': None,
            'created_at': None,
        }

    def scrape(self, max_pages: int = 10, known_offers: Dict = None) -> List[Dict]:
        raise NotImplementedError


class VirgoAgencyScraper(BaseAgencyScraper):
    """Galactica Virgo (ANMA, Pasjonaci): listing ?page=N, dane w slugu."""

    listing_path = '/oferty/dzialki/sprzedaz/'

    def _parse_listing(self, html: str) -> List[Dict]:
        offers = []
        seen = set()
        for m in _VIRGO_SLUG_RE.finditer(html):
            price, area, loc_slug = int(m.group(1)), float(m.group(2)), m.group(3)
            offer_id = m.group(4) or m.group(5)
            if offer_id in seen:
                continue
            seen.add(offer_id)
            loc_parts = loc_slug.split('-')
            # tylko miasto Lublin (slug: gmina-miejscowosc, np. 'lublin-zemborzyce')
            if 'lublin' not in loc_parts:
                continue
            district = ' '.join(p.capitalize() for p in loc_parts if p != 'lublin') or None
            full_slug = m.group(0).rstrip('"?').rstrip('/')
            url = f"{self.base_url}/{full_slug}" if not full_slug.startswith('http') else full_slug
            offer = self._base_offer(offer_id, url)
            offer['price'] = price
            offer['area_m2'] = area
            offer['price_per_m2'] = round(price / area, 2) if area else None
            offer['location']['district'] = district
            offer['title'] = f"Działka na sprzedaż {area:.0f} m² — Lublin"
            offers.append(offer)
        return offers

    def fetch_details(self, offer: Dict) -> Dict:
        self._sleep()
        html = self._fetch(offer['url'])
        if not html:
            return offer
        soup = BeautifulSoup(html, 'lxml')
        h1 = soup.find('h1')
        if h1 and len(_clean(h1.get_text())) > 5:
            offer['title'] = _clean(h1.get_text())
        # opis TYLKO z kontenera opisu — stopka zawiera adres biura (ul. Lipowa),
        # który zatrułby geokodowanie ulicy przez location_refiner
        desc = soup.find(class_=re.compile(r'description|offer-desc|opis', re.I))
        if desc:
            offer['description'] = _clean(desc.get_text(' '))[:3000]
        img = soup.find('meta', property='og:image')
        if img and img.get('content'):
            offer['image'] = img['content']
        return offer

    def scrape(self, max_pages: int = 10, known_offers: Dict = None) -> List[Dict]:
        known_offers = known_offers or {}
        print(f"🔍 {self.agency_name}: scraping działek...")
        offers: List[Dict] = []
        seen_ids = set()
        for page in range(0, max_pages):  # Virgo numeruje od 0
            url = f"{self.base_url}{self.listing_path}?page={page}"
            html = self._fetch(url)
            if html is None:
                break
            # FIX 2026-06-11: przerywamy dopiero gdy strona nie ma ŻADNYCH
            # slugów ofert — strona z samymi powtórkami (karuzele "oferty
            # specjalne" na każdej stronie) nie może ucinać paginacji
            raw_offers = self._parse_listing(html)
            if not _VIRGO_SLUG_RE.search(html):
                break
            new_offers = [o for o in raw_offers if o['id'] not in seen_ids]
            for o in new_offers:
                seen_ids.add(o['id'])
            offers.extend(new_offers)
            self._sleep()

        new = [o for o in offers if o['id'] not in known_offers]
        for o in offers:
            known = known_offers.get(o['id'])
            if known:
                o['description'] = known.get('description') or o['description']
                o['title'] = known.get('title') or o['title']
                o['image'] = known.get('image') or o['image']
        if new:
            print(f"⚡ {self.agency_name}: szczegóły {len(new)} nowych ofert...")
            for o in new:
                self.fetch_details(o)
        print(f"✅ {self.agency_name}: {len(offers)} ofert (Lublin)\n")
        return offers


class AnmaScraper(VirgoAgencyScraper):
    agency_key = 'anma'
    agency_name = 'ANMA'
    base_url = 'https://www.anma.lublin.pl'


class PasjonaciScraper(VirgoAgencyScraper):
    agency_key = 'pasjonaci'
    agency_name = 'Pasjonaci Nieruchomości'
    base_url = 'https://www.pasjonacinieruchomosci.pl'
    listing_path = '/oferty/dzialki/sprzedaz'


class AlternatywneScraper(BaseAgencyScraper):
    """Alternatywne BN (WordPress): /baza-nieruchomosci/?pg=N, karty .row."""

    agency_key = 'alternatywne'
    agency_name = 'Alternatywne BN'
    base_url = 'https://alternatywnebn.pl'

    _OFFER_URL_RE = re.compile(r'/offer/dzialka-sprzedaz-(\d+)/')

    def _card_field(self, card, label: str) -> Optional[str]:
        """Pola karty mają postać 'Etykieta:' + wartość w sąsiednim elemencie."""
        node = card.find(string=re.compile(rf'^\s*{label}\s*:?\s*$'))
        if not node:
            return None
        parent = node.find_parent()
        sibling = parent.find_next_sibling() if parent else None
        return _clean(sibling.get_text()) if sibling else None

    def _parse_card(self, card, url: str, offer_id: str) -> Optional[Dict]:
        city = self._card_field(card, 'Miejscowość')
        if (city or '').lower() != 'lublin':
            return None
        offer = self._base_offer(offer_id, url)
        title_link = card.find('a', href=self._OFFER_URL_RE)
        offer['title'] = _clean(title_link.get_text()) if title_link else ''
        if not offer['title']:
            heading = card.find(re.compile('^h[1-4]$'))
            if heading:
                offer['title'] = _clean(heading.get_text())

        price_txt = self._card_field(card, 'Cena') or ''
        m = re.search(r'([\d\s]+)', price_txt.replace('\xa0', ' '))
        if not m:
            return None
        offer['price'] = int(m.group(1).replace(' ', ''))

        area_txt = self._card_field(card, 'Powierzchnia') or ''
        m = re.search(r'([\d\s]+(?:[,.]\d+)?)', area_txt.replace('\xa0', ' '))
        if m:
            offer['area_m2'] = float(m.group(1).replace(' ', '').replace(',', '.'))
            offer['price_per_m2'] = round(offer['price'] / offer['area_m2'], 2)
        return offer

    def fetch_details(self, offer: Dict) -> Dict:
        self._sleep()
        html = self._fetch(offer['url'])
        if not html:
            return offer
        soup = BeautifulSoup(html, 'lxml')
        if not offer.get('title'):
            og_title = soup.find('meta', property='og:title')
            h1 = soup.find('h1')
            raw = (og_title.get('content') if og_title else '') or (h1.get_text() if h1 else '')
            offer['title'] = _clean(raw.split(' - Alternatywne')[0]) or f"Działka {offer['area_m2']:.0f} m² — Lublin"
        content = soup.find(class_=re.compile(r'entry-content|offer|content', re.I))
        if content:
            offer['description'] = _clean(content.get_text(' '))[:3000]
        img = soup.find('meta', property='og:image')
        if img and img.get('content'):
            offer['image'] = img['content']
        return offer

    def scrape(self, max_pages: int = 25, known_offers: Dict = None) -> List[Dict]:
        known_offers = known_offers or {}
        print(f"🔍 {self.agency_name}: scraping działek...")
        # WP wymaga cookies ze strony głównej, inaczej listing zwraca 403
        self._fetch(self.base_url + '/')
        self._sleep()

        offers: List[Dict] = []
        seen_ids = set()
        for page in range(1, max_pages + 1):
            html = self._fetch(f"{self.base_url}/baza-nieruchomosci/?pg={page}")
            if html is None:
                break
            soup = BeautifulSoup(html, 'lxml')
            links = soup.find_all('a', href=self._OFFER_URL_RE)
            found_new = 0
            for link in links:
                offer_id = self._OFFER_URL_RE.search(link['href']).group(1)
                if offer_id in seen_ids:
                    continue
                seen_ids.add(offer_id)
                card = link
                for _ in range(6):
                    card = card.find_parent()
                    if card and self._card_field(card, 'Cena'):
                        break
                if not card:
                    continue
                offer = self._parse_card(card, link['href'], offer_id)
                if offer:
                    offers.append(offer)
                    found_new += 1
            if not links:
                break
            self._sleep()

        new = [o for o in offers if o['id'] not in known_offers]
        for o in offers:
            known = known_offers.get(o['id'])
            if known:
                o['description'] = known.get('description') or o['description']
                o['image'] = known.get('image') or o['image']
        if new:
            print(f"⚡ {self.agency_name}: szczegóły {len(new)} nowych ofert...")
            for o in new:
                self.fetch_details(o)
        print(f"✅ {self.agency_name}: {len(offers)} ofert (Lublin)\n")
        return offers


AGENCY_SCRAPERS = [AnmaScraper, PasjonaciScraper, AlternatywneScraper]


if __name__ == "__main__":
    for cls in AGENCY_SCRAPERS:
        scraper = cls(delay_range=(1.0, 2.0))
        result = scraper.scrape(max_pages=3)
        for o in result[:3]:
            print("  ", o['id'], o['price'], 'zł |', o['area_m2'], 'm² |',
                  o['location']['district'], '|', o['title'][:50])
