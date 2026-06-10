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


def _offer(id_, source, price, area, coords=None, active=True):
    return {
        'id': id_, 'source': source, 'active': active, 'area_m2': area,
        'price': {'current': price},
        'url': f'https://example.com/{id_}',
        'location': {'coords': coords},
        'first_seen': '2026-06-01T10:00:00+02:00',
        'last_seen': '2026-06-10T10:00:00+02:00',
    }


def test_cross_portal_dedup_tagging(tmp_path):
    from main import SonarDzialkowy
    sonar = SonarDzialkowy(data_file=str(tmp_path / 'offers.json'),
                           removed_file=str(tmp_path / 'removed.json'))
    near = {'lat': 51.25, 'lon': 22.56}
    near2 = {'lat': 51.26, 'lon': 22.57}      # ~1.3 km
    far = {'lat': 51.35, 'lon': 22.80}        # ~20 km
    sonar.database['offers'] = [
        _offer('olx:CID3-ID1', 'olx', 300000, 1500, near),
        _offer('otodom:1', 'otodom', 300000, 1505, near2),   # duplikat (±1%, blisko)
        _offer('olx:CID3-ID2', 'olx', 300000, 1500, near),
        _offer('otodom:2', 'otodom', 300000, 1500, far),     # za daleko — nie duplikat
    ]
    sonar._tag_cross_portal_duplicates()
    offers = {o['id']: o for o in sonar.database['offers']}
    assert offers['olx:CID3-ID1']['duplicate_of'] == 'otodom:1'
    assert offers['otodom:1']['also_at'] == offers['olx:CID3-ID1']['url']
    # otodom:1 jest już sparowany (max 1 duplikat), a otodom:2 odpada po
    # dystansie (>5 km) — więc ID2 zostaje na mapie bez duplicate_of
    assert 'duplicate_of' not in offers['olx:CID3-ID2']
