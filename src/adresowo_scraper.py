"""Adresowo.pl Scraper — działki na sprzedaż w Lublinie.

Adresowo to portal ogłoszeniowy (jak OLX/Otodom, nie agencja):
- listing: https://adresowo.pl/dzialki/lublin/ + paginacja /_l2, /_l3, ...
  (39 ofert/stronę; iterujemy aż strona nie przyniesie nic nowego)
- karty: cena, powierzchnia, snippet opisu, znacznik „bez pośredników"
- strona szczegółów (TYLKO dla nowych ofert): współrzędne GPS, pełny opis,
  ulica w tytule, typ działki
"""

import re
import time
import random
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://adresowo.pl"
LISTING_PATH = "/dzialki/lublin/"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8',
}

_OFFER_HREF_RE = re.compile(r'^/o/[a-z0-9-]+$')
_COORDS_RE = re.compile(r'(?:"lat(?:itude)?"|lat)["\':=\s]+(5[01]\.\d{3,})'
                        r'.{0,80}?(?:"l(?:o)?n(?:gitude)?"|lng)["\':=\s]+(2[123]\.\d{3,})', re.S)
_STREET_TITLE_RE = re.compile(r'((?:ul|al)\.\s*[A-ZŚĆŁŻŹÓĄĘŃ][\wąęółśżźćń\. ]+?)\s*[-–]')

PLOT_TYPE_WORDS = {
    'budowlan': 'budowlana',
    'inwestycyj': 'inwestycyjna',
    'rolno-budowlan': 'rolno-budowlana',
    'roln': 'rolna',
    'rekreacyj': 'rekreacyjna',
    'lesn': 'leśna', 'leśn': 'leśna',
    'siedliskow': 'siedliskowa',
}


def plot_type_from_text(text: str) -> str:
    t = (text or '').lower()
    for needle, label in PLOT_TYPE_WORDS.items():
        if 'działka ' + needle in t or 'dzialka-' + needle in t or needle in t.split('lublin')[0]:
            return label
    return 'inna'


def _num(text: str) -> Optional[float]:
    m = re.search(r'([\d\s]+(?:[,.]\d+)?)', (text or '').replace('\xa0', ' '))
    if not m:
        return None
    try:
        return float(m.group(1).replace(' ', '').replace(',', '.'))
    except ValueError:
        return None


class AdresowoScraper:
    def __init__(self, delay_range=(0.6, 1.2)):
        self.delay_min, self.delay_max = delay_range
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _sleep(self):
        time.sleep(random.uniform(self.delay_min, self.delay_max))

    def _fetch(self, url: str) -> Optional[str]:
        try:
            r = self.session.get(url, timeout=25)
            if r.status_code != 200:
                print(f"⚠️ Adresowo: HTTP {r.status_code} dla {url}")
                return None
            return r.text
        except requests.RequestException as e:
            print(f"❌ Adresowo: błąd pobierania {url}: {e}")
            return None

    def _parse_card(self, link_tag) -> Optional[Dict]:
        href = link_tag['href']
        offer_id = href.rsplit('-', 1)[-1]
        # karta = najbliższy przodek z ceną
        card = link_tag
        for _ in range(6):
            card = card.find_parent()
            if card is None:
                return None
            if 'zł' in card.get_text():
                break
        text = card.get_text(' | ', strip=True)

        m_price = re.search(r'([\d\s]{2,12})\s*\|?\s*zł', text)
        m_area = re.search(r'([\d\s]+(?:[,.]\d+)?)\s*\|?\s*m²', text)
        if not m_price:
            return None
        price = int(_num(m_price.group(1)) or 0)
        if price < 1000:  # śmieć / cena za m²
            return None
        area = _num(m_area.group(1)) if m_area else None

        return {
            'id': f"adresowo:{offer_id}",
            'source': 'adresowo',
            'url': BASE_URL + href,
            'title': f"Działka na sprzedaż{f' {area:.0f} m²' if area else ''} — Lublin",
            'price': price,
            'area_m2': area,
            'price_per_m2': round(price / area, 2) if area else None,
            'plot_type': plot_type_from_text(href),
            'location': {'city': 'Lublin', 'district': None, 'street': None,
                         'coords': None, 'coords_precision': None},
            'description': '',
            'is_private_owner': 'bez pośredników' in text.lower(),
            'image': None,
            'created_at': None,
        }

    def fetch_details(self, offer: Dict) -> Dict:
        """Strona szczegółów: coords, pełny opis, ulica z tytułu, zdjęcie."""
        self._sleep()
        html = self._fetch(offer['url'])
        if not html:
            return offer
        soup = BeautifulSoup(html, 'lxml')

        m = _COORDS_RE.search(html)
        if m:
            offer['location']['coords'] = {'lat': float(m.group(1)),
                                           'lon': float(m.group(2))}
            offer['location']['coords_precision'] = 'exact'

        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else ''
        if title:
            offer['title'] = title.split(' - adresowo')[0].strip() or offer['title']
            ms = _STREET_TITLE_RE.search(title)
            if ms:
                offer['location']['street'] = ms.group(1).strip()

        og_desc = soup.find('meta', property='og:description')
        desc_section = soup.find(class_=re.compile(r'description|offer-text', re.I))
        description = ''
        if desc_section:
            description = re.sub(r'\s+', ' ', desc_section.get_text(' ')).strip()
        elif og_desc and og_desc.get('content'):
            description = og_desc['content']
        if len(description) > len(offer.get('description') or ''):
            offer['description'] = description[:3000]

        if offer['plot_type'] == 'inna':
            offer['plot_type'] = plot_type_from_text(title + ' ' + description[:200])

        img = soup.find('meta', property='og:image')
        if img and img.get('content'):
            offer['image'] = img['content']
        return offer

    def scrape(self, max_pages: int = 10, known_offers: Dict = None) -> List[Dict]:
        known_offers = known_offers or {}
        print("🔍 Adresowo: scraping działek (Lublin)...")
        offers: List[Dict] = []
        seen_ids = set()

        for page in range(1, max_pages + 1):
            url = BASE_URL + LISTING_PATH + (f"_l{page}" if page > 1 else "")
            html = self._fetch(url)
            if not html:
                break
            soup = BeautifulSoup(html, 'lxml')
            links = [a for a in soup.find_all('a', href=_OFFER_HREF_RE)]
            new_on_page = 0
            for link in links:
                offer = self._parse_card(link)
                if not offer or offer['id'] in seen_ids:
                    continue
                seen_ids.add(offer['id'])
                offers.append(offer)
                new_on_page += 1
            print(f"📄 Adresowo strona {page}: {new_on_page} nowych ofert")
            # koniec paginacji: brak linków ofert; strona z samymi powtórkami
            # przerywa dopiero od 2. strony (1. zawsze ma nowe przy pustym seen)
            if not links:
                break
            if new_on_page == 0 and page > 1:
                break
            self._sleep()

        # szczegóły tylko dla ofert nieznanych bazie
        to_fetch = []
        for offer in offers:
            known = known_offers.get(offer['id'])
            # oferta znana = nie refetchujemy, nawet jeśli nie ma coords
            # (centroid miasta mógł zostać celowo usunięty przez main.py)
            if known:
                offer['location']['coords'] = known.get('coords')
                offer['location']['coords_precision'] = known.get('coords_precision')
                offer['location']['street'] = known.get('street')
                offer['description'] = known.get('description') or offer['description']
                offer['title'] = known.get('title') or offer['title']
                offer['plot_type'] = known.get('plot_type') or offer['plot_type']
                offer['image'] = known.get('image') or offer['image']
            else:
                to_fetch.append(offer)

        if to_fetch:
            print(f"⚡ Adresowo: szczegóły {len(to_fetch)} nowych ofert...")
            for i, offer in enumerate(to_fetch, 1):
                self.fetch_details(offer)
                print(f"\r   Postęp: [{i}/{len(to_fetch)}]", end='', flush=True)
            print()
        else:
            print("✅ Adresowo: wszystkie oferty znane (pominięto szczegóły)")

        print(f"✅ Adresowo: zebrano {len(offers)} ofert\n")
        return offers


if __name__ == "__main__":
    scraper = AdresowoScraper(delay_range=(0.5, 1.0))
    result = scraper.scrape(max_pages=2)
    for o in result[:5]:
        loc = o['location']
        print("  ", o['id'], o['price'], 'zł |', o['area_m2'], 'm² |',
              o['plot_type'], '|', loc.get('street'), '|', loc.get('coords'),
              '|', o['title'][:40])
