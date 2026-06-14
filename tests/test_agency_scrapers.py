"""Testy parserów agencji (bez live requestów)."""

from agency_scrapers import (
    AnmaScraper, PasjonaciScraper, AlternatywneScraper, IdsHomeScraper,
    _VIRGO_SLUG_RE,
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


# IdsHome to Virgo — slug ofert siedzi w korzeniu domeny (jak ANMA: sufiks -o{id})
IDSHOME_LISTING_HTML = '''
<a href="https://www.idshome.pl/dzialki-na-sprzedaz-450000zl-1200m2-lublin-slawinek-o7129999" class="overlay-link">Działka Sławinek</a>
<a href="https://www.idshome.pl/mieszkania-na-sprzedaz-980000zl-55m2-lublin-czechow-poludniowy-o7129660">Mieszkanie (ignorować)</a>
<a href="https://www.idshome.pl/dzialki-na-sprzedaz-300000zl-900m2-niemce-o7120000">Działka poza Lublinem</a>
'''


def test_idshome_parse_listing_only_dzialki_lublin():
    offers = IdsHomeScraper()._parse_listing(IDSHOME_LISTING_HTML)
    # tylko działka w Lublinie — mieszkanie i działka spoza Lublina odrzucone
    assert {o['id'] for o in offers} == {'idshome:7129999'}
    o = offers[0]
    assert o['agency_name'] == 'IdsHome'
    assert o['price'] == 450000 and o['area_m2'] == 1200.0
    assert o['location']['district'] == 'Slawinek'  # district ze slugu = ASCII
    assert o['url'] == ('https://www.idshome.pl/'
                        'dzialki-na-sprzedaz-450000zl-1200m2-lublin-slawinek-o7129999')


def test_idshome_details_extract_coords():
    offer = IdsHomeScraper()._base_offer('7129999', 'http://x')
    html = ('<h1>Działka na sprzedaż - Lublin, Sławinek</h1>'
            '<div class="offer-description">Piękna działka.</div>'
            '<script>var gmap_params = eval({"center_lat":"51.276","center_long":"22.520",'
            '"zoom":13,"markers":[{"lat":"51.276","long":"22.520"}]});</script>')
    soup = BeautifulSoup(html, 'lxml')
    IdsHomeScraper()._parse_details(offer, soup, html)
    assert offer['location']['coords'] == {'lat': 51.276, 'lon': 22.520}
    assert offer['location']['coords_precision'] == 'street'
    assert offer['title'] == 'Działka na sprzedaż - Lublin, Sławinek'
    assert 'Piękna' in offer['description']


def test_idshome_rejects_coords_outside_region():
    # pusta tablica markers / centroid spoza Lubelszczyzny → coords zostają puste
    offer = IdsHomeScraper()._base_offer('1', 'http://x')
    html = '<script>var gmap_params = eval({"markers":[{"lat":"52.229","long":"21.012"}]});</script>'
    IdsHomeScraper()._parse_details(offer, BeautifulSoup(html, 'lxml'), html)
    assert offer['location']['coords'] is None
