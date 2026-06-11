"""Testy parserów agencji (bez live requestów)."""

from agency_scrapers import (
    AnmaScraper, PasjonaciScraper, AlternatywneScraper, _VIRGO_SLUG_RE,
)
from bs4 import BeautifulSoup


VIRGO_LISTING_HTML = '''
<a href="dzialki-na-sprzedaz-4281540zl-24252m2-lublin-zemborzyce-o6677851">Działka Zemborzyce</a>
<a href="dzialki-na-sprzedaz-275000zl-1000m2-konopnica-motycz-o6988570">Motycz (poza Lublinem)</a>
<a href="https://www.pasjonacinieruchomosci.pl/dzialki-na-sprzedaz-119000zl-3760m2-policzna-teodorow/7128365">Teodorów</a>
<a href="dzialki-na-sprzedaz-500000zl-800m2-lublin-slawin-o7000001">Sławin</a>
<a href="dzialki-na-sprzedaz-500000zl-800m2-lublin-slawin-o7000001">duplikat Sławin</a>
'''


def test_virgo_slug_regex():
    m = _VIRGO_SLUG_RE.search('dzialki-na-sprzedaz-4281540zl-24252m2-lublin-zemborzyce-o6677851"')
    assert m.group(1) == '4281540' and m.group(2) == '24252'
    assert m.group(3) == 'lublin-zemborzyce' and m.group(4) == '6677851'
    # wariant Pasjonatów: /ID zamiast -oID
    m2 = _VIRGO_SLUG_RE.search('dzialki-na-sprzedaz-119000zl-3760m2-policzna-teodorow/7128365"')
    assert m2.group(3) == 'policzna-teodorow' and m2.group(5) == '7128365'


def test_virgo_parse_listing_filters_lublin():
    offers = AnmaScraper()._parse_listing(VIRGO_LISTING_HTML)
    ids = {o['id'] for o in offers}
    # tylko Lublin, bez duplikatów
    assert ids == {'anma:6677851', 'anma:7000001'}
    zemborzyce = next(o for o in offers if o['id'] == 'anma:6677851')
    assert zemborzyce['price'] == 4281540
    assert zemborzyce['area_m2'] == 24252.0
    assert zemborzyce['location']['district'] == 'Zemborzyce'
    assert zemborzyce['is_agency'] is True
    assert zemborzyce['agency_name'] == 'ANMA'
    assert zemborzyce['is_private_owner'] is False
    assert zemborzyce['price_per_m2'] == round(4281540 / 24252, 2)


def test_pasjonaci_ids_have_own_prefix():
    offers = PasjonaciScraper()._parse_listing(
        'href="dzialki-na-sprzedaz-100000zl-1000m2-lublin-wrotkow/711111"')
    assert offers[0]['id'] == 'pasjonaci:711111'
    assert offers[0]['agency_name'] == 'Pasjonaci Nieruchomości'


ALT_CARD_HTML = '''
<div class="row">
  <a href="https://alternatywnebn.pl/offer/dzialka-sprzedaz-7122183/"><h3>Ładna działka</h3></a>
  <div><span>Gmina:</span><span>Lublin</span></div>
  <div><span>Miejscowość:</span><span>Lublin</span></div>
  <div><span>Powierzchnia:</span><span>3 521,00 m</span></div>
  <div><span>Cena:</span><span>179 000 PLN</span></div>
</div>
'''


def test_alternatywne_parse_card():
    scraper = AlternatywneScraper()
    card = BeautifulSoup(ALT_CARD_HTML, 'lxml').find('div', class_='row')
    offer = scraper._parse_card(
        card, 'https://alternatywnebn.pl/offer/dzialka-sprzedaz-7122183/', '7122183')
    assert offer['id'] == 'alternatywne:7122183'
    assert offer['price'] == 179000
    assert offer['area_m2'] == 3521.0
    assert offer['title'] == 'Ładna działka'
    assert offer['is_agency'] is True


def test_alternatywne_rejects_outside_lublin():
    html = ALT_CARD_HTML.replace('<span>Miejscowość:</span><span>Lublin</span>',
                                 '<span>Miejscowość:</span><span>Bogucin</span>')
    card = BeautifulSoup(html, 'lxml').find('div', class_='row')
    assert AlternatywneScraper()._parse_card(card, 'x', '1') is None
