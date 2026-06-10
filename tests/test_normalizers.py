"""Testy normalizacji ofert OLX i Otodom do wspólnego schematu."""

from olx_scraper import normalize_ad, strip_html, PLOT_TYPE_MAP as OLX_TYPES
from otodom_scraper import normalize_item
from cid import extract_cid, olx_offer_id, otodom_offer_id


OLX_AD = {
    'url': 'https://www.olx.pl/d/oferta/dzialka-testowa-CID3-ID1abcDE.html?reason=x',
    'title': 'Działka budowlana Lublin ',
    'isBusiness': False,
    'createdTime': '2026-06-01T10:00:00+02:00',
    'description': '<p>Ładna działka</p><p>z mediami</p>',
    'price': {'regularPrice': {'value': 300000, 'currencyCode': 'PLN'}},
    'map': {'lat': 51.25, 'lon': 22.56, 'radius': 1},
    'location': {'cityName': 'Lublin', 'cityNormalizedName': 'lublin', 'districtName': 'Sławin'},
    'photos': ['https://example.com/foto.jpg'],
    'params': [
        {'key': 'type', 'normalizedValue': 'dzialki-budowlane'},
        {'key': 'm', 'normalizedValue': '1500'},
        {'key': 'price_per_m', 'normalizedValue': '200'},
    ],
}

OTODOM_ITEM = {
    'id': 68093538,
    'slug': 'piekna-dzialka-ID4BIeS',
    'title': 'Piękna działka',
    'totalPrice': {'value': 690000},
    'pricePerSquareMeter': {'value': 575},
    'areaInSquareMeters': 1200,
    'isPrivateOwner': False,
    'shortDescription': 'Działka na Poligonowej',
    'createdAtFirst': '2026-06-10T13:32:27Z',
    'images': [{'medium': 'https://example.com/m.jpg', 'large': 'https://example.com/l.jpg'}],
    'location': {
        'address': {'street': {'name': 'ul. Poligonowa', 'number': ''},
                    'city': {'name': 'Lublin'}},
        'reverseGeocoding': {'locations': [
            {'name': 'Lublin', 'locationLevel': 'city_or_village'},
            {'name': 'Sławin', 'locationLevel': 'district'},
        ]},
    },
}


def test_extract_cid():
    assert extract_cid(OLX_AD['url']) == 'CID3-ID1abcDE'
    assert extract_cid('brak-cid') == 'brak-cid'
    assert extract_cid(None) == ''


def test_olx_normalize():
    o = normalize_ad(OLX_AD)
    assert o['id'] == 'olx:CID3-ID1abcDE'
    assert o['source'] == 'olx'
    assert o['url'].endswith('.html')  # bez query params
    assert o['title'] == 'Działka budowlana Lublin'
    assert o['price'] == 300000
    assert o['area_m2'] == 1500.0
    assert o['price_per_m2'] == 200.0
    assert o['plot_type'] == 'budowlana'
    assert o['location']['coords'] == {'lat': 51.25, 'lon': 22.56}
    assert o['location']['coords_precision'] == 'approx'
    assert o['location']['district'] == 'Sławin'
    assert o['is_private_owner'] is True
    assert 'Ładna działka' in o['description']
    assert '<p>' not in o['description']


def test_olx_normalize_no_price():
    ad = dict(OLX_AD, price={})
    assert normalize_ad(ad) is None


def test_olx_per_m2_computed_when_missing():
    ad = dict(OLX_AD)
    ad['params'] = [
        {'key': 'type', 'normalizedValue': 'dzialki-budowlane'},
        {'key': 'm', 'normalizedValue': '1500'},
    ]
    o = normalize_ad(ad)
    assert o['price_per_m2'] == 200.0


def test_otodom_normalize():
    o = normalize_item(OTODOM_ITEM)
    assert o['id'] == 'otodom:68093538'
    assert o['source'] == 'otodom'
    assert o['url'] == 'https://www.otodom.pl/pl/oferta/piekna-dzialka-ID4BIeS'
    assert o['price'] == 690000
    assert o['area_m2'] == 1200.0
    assert o['price_per_m2'] == 575.0
    assert o['location']['street'] == 'ul. Poligonowa'
    assert o['location']['district'] == 'Sławin'
    assert o['location']['coords'] is None  # coords dopiero ze strony szczegółów
    assert o['is_private_owner'] is False
    assert o['image'] == 'https://example.com/m.jpg'


def test_otodom_normalize_hidden_price():
    item = dict(OTODOM_ITEM, totalPrice=None)
    assert normalize_item(item) is None


def test_strip_html():
    assert strip_html('<p>a</p><p>b</p>') == 'a\nb'
    assert strip_html('') == ''
    assert strip_html(None) == ''


def test_plot_type_fallback():
    ad = dict(OLX_AD)
    ad['params'] = [{'key': 'type', 'normalizedValue': 'cos-nowego'}]
    assert normalize_ad(ad)['plot_type'] == 'inna'
    assert 'dzialki-rolno-budowlane' in OLX_TYPES


def test_offer_id_helpers():
    assert olx_offer_id('x-CID3-ID9z.html') == 'olx:CID3-ID9z'
    assert otodom_offer_id(123) == 'otodom:123'
