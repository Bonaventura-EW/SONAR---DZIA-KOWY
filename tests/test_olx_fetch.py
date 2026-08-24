"""Testy warstwy HTTP scrapera OLX — impersonacja TLS i jej rotacja.

OLX (CloudFront/WAF) blokuje fingerprint TLS `requests` błędem 403, dlatego
scraper chodzi przez curl_cffi i przy błędzie przełącza się na kolejny profil
przeglądarki, a na końcu na gołe requests.
"""

import requests

import olx_scraper
from olx_scraper import OLXDzialkiScraper


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FakeSession:
    """Sesja curl_cffi: dany profil albo działa, albo leci błędem sieciowym."""

    working_profile = 'chrome110'

    def __init__(self, impersonate=None):
        self.impersonate = impersonate
        self.closed = False

    def get(self, url, timeout=None):
        if self.impersonate != self.working_profile:
            raise requests.ConnectionError(f'blokada dla {self.impersonate}')
        return FakeResponse(f'<html>{self.impersonate}</html>')

    def close(self):
        self.closed = True


class FakeCurlCffi:
    Session = FakeSession
    RequestsError = requests.RequestException

    class exceptions:
        HTTPError = requests.HTTPError


def test_domyslnie_startuje_z_impersonacja(monkeypatch):
    monkeypatch.setattr(olx_scraper, 'impersonate_requests', FakeCurlCffi)
    scraper = OLXDzialkiScraper()

    assert scraper.impersonate == olx_scraper.IMPERSONATE_PROFILES[0]


def test_rotacja_profili_do_dzialajacego(monkeypatch):
    monkeypatch.setattr(olx_scraper, 'impersonate_requests', FakeCurlCffi)
    scraper = OLXDzialkiScraper(
        impersonate_profiles=('chrome131', 'chrome124', 'chrome110'))

    html = scraper._fetch('https://www.olx.pl/listing')

    assert html == '<html>chrome110</html>'
    assert scraper.impersonate == 'chrome110'


def test_po_wyczerpaniu_profili_zostaje_gole_requests(monkeypatch):
    """Żaden profil nie działa → ostatnia próba na requests, potem None."""
    monkeypatch.setattr(olx_scraper, 'impersonate_requests', FakeCurlCffi)
    monkeypatch.setattr(FakeSession, 'working_profile', 'nie-istnieje')

    def failing_get(self, url, timeout=None):
        raise requests.ConnectionError('403')

    monkeypatch.setattr(requests.Session, 'get', failing_get)
    scraper = OLXDzialkiScraper(impersonate_profiles=('chrome131', 'chrome110'))

    assert scraper._fetch('https://www.olx.pl/listing') is None
    assert scraper.impersonate is None  # zszedł aż do gołych requests


def test_bez_curl_cffi_dziala_jak_wczesniej(monkeypatch):
    """Środowisko bez curl_cffi: zwykła sesja requests, bez rotacji."""
    monkeypatch.setattr(olx_scraper, 'impersonate_requests', None)
    scraper = OLXDzialkiScraper()

    assert scraper.impersonate is None
    assert isinstance(scraper.session, requests.Session)
    assert scraper._switch_session() is False
