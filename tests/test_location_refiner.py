"""Testy ekstrakcji ulic i doprecyzowania lokalizacji (bez live Nominatim)."""

from location_refiner import (
    extract_street_candidates, nominative_variants, refine_offer_location,
    StreetGeocoder,
)


def test_extract_street_basic():
    assert extract_street_candidates(
        "Działka z wydaną WZ- Lublin, ul. Krężnicka") == ['Krężnicka']
    assert extract_street_candidates(
        "Działka 26 ar przy ul. Wyżynnej w Lublinie") == ['Wyżynnej']
    assert extract_street_candidates(
        "Świetna lokalizacja przy alei Kraśnickiej, media") == ['Kraśnickiej']


def test_extract_street_cuts_garbage():
    # stop-słowa i granice zdań ucinane z dopasowania
    assert extract_street_candidates(
        "Działka 515m2 ul. Kosynierów. Dzielnica:Ponikwoda") == ['Kosynierów']
    assert extract_street_candidates("ulica Makowa. Oferta bez prowizji") == ['Makowa']


def test_extract_street_multiword():
    assert extract_street_candidates(
        "przy ul. Gen. Urbanowicza, blisko lasu") == ['Gen. Urbanowicza']


def test_extract_street_none():
    assert extract_street_candidates("Działka bez ulicy w tekście") == []
    assert extract_street_candidates("") == []
    assert extract_street_candidates(None) == []


def test_nominative_variants():
    assert 'Krężnicka' in nominative_variants('Krężnickiej')
    assert 'Wyżynna' in nominative_variants('Wyżynnej')
    assert 'Zorza' in nominative_variants('Zorzy')
    assert nominative_variants('Makowa') == ['Makowa']  # już mianownik


class FakeGeocoder:
    """Atrapa geokodera — zwraca punkt dla znanych ulic, None dla reszty."""
    KNOWN = {'krężnicka': {'lat': 51.19, 'lon': 22.52, 'name': 'Krężnicka'}}

    def geocode_street(self, street):
        for variant in nominative_variants(street):
            hit = self.KNOWN.get(variant.lower())
            if hit:
                return hit
        return None


def test_refine_upgrades_approx():
    offer = {
        'title': 'Działka budowlana Lublin, ul. Krężnickiej',
        'description': '',
        'location': {'coords': {'lat': 51.25, 'lon': 22.57},
                     'coords_precision': 'approx', 'street': None},
    }
    assert refine_offer_location(offer, FakeGeocoder()) is True
    assert offer['location']['coords_precision'] == 'street'
    assert offer['location']['coords'] == {'lat': 51.19, 'lon': 22.52}
    assert offer['location']['street'] == 'ul. Krężnicka'


def test_refine_keeps_exact_untouched():
    offer = {
        'title': 'Działka ul. Krężnicka',
        'description': '',
        'location': {'coords': {'lat': 51.28, 'lon': 22.53},
                     'coords_precision': 'exact', 'street': 'ul. Poligonowa'},
    }
    assert refine_offer_location(offer, FakeGeocoder()) is False
    assert offer['location']['coords'] == {'lat': 51.28, 'lon': 22.53}


def test_refine_no_street_found():
    offer = {
        'title': 'Działka przy ul. Nieistniejącej',
        'description': '',
        'location': {'coords': {'lat': 51.25, 'lon': 22.57},
                     'coords_precision': 'approx', 'street': None},
    }
    assert refine_offer_location(offer, FakeGeocoder()) is False
    assert offer['location']['coords_precision'] == 'approx'


def test_geocoder_negative_cache(tmp_path):
    g = StreetGeocoder(cache_file=str(tmp_path / 'cache.json'))
    g.cache['nieistniejąca'] = {'result': None, 'ts': 9e12}  # świeży negatyw
    assert g.geocode_street('Nieistniejąca') is None
    assert g.live_requests == 0  # nie strzelał do Nominatim


def test_stop_words_block_city_as_street():
    # 'Lublinie'/'Lublin' nie mogą być kandydatem na ulicę
    assert extract_street_candidates("Działka przy ul. Lublinie atrakcyjna") == []
    assert extract_street_candidates("ulica Lublin bez sensu") == []
