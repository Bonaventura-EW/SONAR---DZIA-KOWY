"""Testy parsera Adresowo (bez live requestów)."""

from bs4 import BeautifulSoup

from adresowo_scraper import (
    AdresowoScraper, plot_type_from_text, _STREET_TITLE_RE, _COORDS_RE,
)


def test_plot_type_from_text():
    assert plot_type_from_text('/o/dzialka-budowlana-lublin-ul-dozynkowa-f7b2c6') == 'budowlana'
    assert plot_type_from_text('Działka rekreacyjna Lublin') == 'rekreacyjna'
    assert plot_type_from_text('Działka Lublin, bez pośrednika') == 'inna'


def test_street_from_title():
    m = _STREET_TITLE_RE.search('Działka Lublin, ul. Dożynkowa - 1 000 m² - 799 000 zł')
    assert m.group(1) == 'ul. Dożynkowa'
    m2 = _STREET_TITLE_RE.search('Działka Lublin, al. Kraśnicka – 2 000 m²')
    assert m2.group(1) == 'al. Kraśnicka'
    assert _STREET_TITLE_RE.search('Działka Lublin - 300 m²') is None


def test_coords_regex():
    html = '{"latitude": 51.27884, "longitude": 22.591202}'
    m = _COORDS_RE.search(html)
    assert float(m.group(1)) == 51.27884
    assert float(m.group(2)) == 22.591202


CARD_HTML = '''
<div><div><a href="/o/dzialka-budowlana-lublin-ul-tezowa-n5u7o4">x</a>
<div><span>340 000</span> <span>zł</span> <span>1 040</span> <span>m²</span>
<p>Lublin | Działka na sprzedaż | bez pośredników | opis...</p></div></div></div>
'''


def test_parse_card():
    soup = BeautifulSoup(CARD_HTML, 'lxml')
    link = soup.find('a')
    offer = AdresowoScraper()._parse_card(link)
    assert offer['id'] == 'adresowo:n5u7o4'
    assert offer['source'] == 'adresowo'
    assert offer['price'] == 340000
    assert offer['area_m2'] == 1040.0
    assert offer['price_per_m2'] == round(340000 / 1040, 2)
    assert offer['plot_type'] == 'budowlana'
    assert offer['is_private_owner'] is True
    assert offer['url'] == 'https://adresowo.pl/o/dzialka-budowlana-lublin-ul-tezowa-n5u7o4'
