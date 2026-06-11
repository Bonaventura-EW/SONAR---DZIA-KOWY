"""Doprecyzowanie lokalizacji ofert: ulica z tytułu/opisu → współrzędne.

OLX rozmywa pinezkę (~1 km, czasem centroid miasta), ale sprzedawcy często
podają ulicę w tytule lub opisie ogłoszenia. Ten moduł:

1. wyciąga kandydatów na ulicę z tekstu (regex po prefiksach ul./ulica/al.),
2. normalizuje polską odmianę (dopełniacz → mianownik: „Wyżynnej" → „Wyżynna"),
3. geokoduje przez Nominatim (zapytanie strukturalne street+city, cache na
   dysku, limit 1 req/s) i zwraca punkt TYLKO gdy leży w Lublinie.

Oferty z dokładnymi coords (Otodom, precision 'exact') nie są ruszane.
Po udanym geokodowaniu oferta dostaje precision 'street' (lepsze niż 'approx',
gorsze niż 'exact').
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests

import paths

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {'User-Agent': 'SONAR-DZIALKOWY/1.0 (github.com/Bonaventura-EW/SONAR---DZIA-KOWY)'}
CACHE_FILE = Path(paths.DATA_DIR) / "geocoding_cache.json"
NEGATIVE_TTL_S = 7 * 24 * 3600  # nieudane zapytania ponawiamy po tygodniu

# Granice Lublina z marginesem — wynik spoza nich odrzucamy
LUBLIN_BBOX = {'lat_min': 51.10, 'lat_max': 51.36, 'lon_min': 22.40, 'lon_max': 22.78}

# ulica musi zaczynać się wielką literą; łapiemy do 3 słów (np. "Gen. Urbanowicza",
# "H. i M. Sachsów" złapie się częściowo — trudno, walidacją jest geokoder)
_STREET_RE = re.compile(
    r'(?:\b(?:ul|al)\.\s*|\b(?:ulic[ayę]|ulicą|alei|alej[aę])\s+|\bprzy\s+ul\.?\s*)'
    r'([A-ZŚĆŁŻŹÓĄĘŃ][\wąęółśżźćń]+\.?(?:[ \-][A-ZŚĆŁŻŹÓĄĘŃ][\wąęółśżźćń\.]*){0,2})',
    re.UNICODE)

# słowa, które NIE są nazwą ulicy (ucinamy je z końca dopasowania)
_STOP_WORDS = {
    'dzielnica', 'oferta', 'lublin', 'lublinie', 'lublina', 'działka',
    'działki', 'cena', 'nr', 'obok', 'blisko', 'oraz', 'czyli', 'gmina',
    'okolice', 'najważniejsze',
}


def extract_street_candidates(text: str) -> List[str]:
    """Zwraca kandydatów na nazwę ulicy z tekstu (bez duplikatów, w kolejności)."""
    candidates = []
    for m in _STREET_RE.finditer(text or ''):
        name = m.group(1)
        # utnij na granicy zdania/linii i odetnij stop-słowa z końca
        name = re.split(r'[\n,;:|!?()"]', name)[0].strip().rstrip('.')
        words = name.split()
        while words and words[-1].lower().strip('.') in _STOP_WORDS:
            words.pop()
        name = ' '.join(words).rstrip('.')
        if len(name) >= 4 and name not in candidates:
            candidates.append(name)
    return candidates


def nominative_variants(street: str) -> List[str]:
    """Warianty mianownika dla nazwy w dopełniaczu: Wyżynnej→Wyżynna,
    Krężnickiej→Krężnicka, Zemborzyckiej→Zemborzycka."""
    variants = [street]
    last = street.split()[-1]
    prefix = street[: len(street) - len(last)]
    if last.endswith('iej') and len(last) > 4:
        variants.append(prefix + last[:-3] + 'a')
    elif last.endswith('ej') and len(last) > 3:
        variants.append(prefix + last[:-2] + 'a')
    elif last.endswith('y') and len(last) > 3:
        # „Zorzy" → „Zorza" (dopełniacz rzeczowników żeńskich na -a)
        variants.append(prefix + last[:-1] + 'a')
    return variants


class StreetGeocoder:
    def __init__(self, cache_file: str = str(CACHE_FILE), delay_s: float = 1.1):
        self.cache_file = Path(cache_file)
        self.delay_s = delay_s
        self._last_request = 0.0
        self.cache = self._load_cache()
        self.live_requests = 0

    def _load_cache(self) -> Dict:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return {}

    def save_cache(self):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=1)

    def _query(self, street: str) -> Optional[Dict]:
        """Jedno zapytanie strukturalne do Nominatim (z rate limitem)."""
        wait = self.delay_s - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(NOMINATIM_URL, params={
                'street': street, 'city': 'Lublin', 'country': 'Poland',
                'format': 'json', 'limit': 3,
            }, headers=HEADERS, timeout=15)
            self._last_request = time.time()
            self.live_requests += 1
            r.raise_for_status()
            results = r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"      ⚠️ Nominatim błąd dla '{street}': {e}")
            return None

        for res in results:
            lat, lon = float(res['lat']), float(res['lon'])
            # FIX 2026-06-11: tylko realne ulice (class=highway) — bez tego
            # zapytanie o śmieciową nazwę (np. 'Lublinie') dopasowywało samo
            # miasto i pinezka lądowała w generycznym punkcie
            if res.get('class') != 'highway':
                continue
            if 'Lublin' not in res.get('display_name', ''):
                continue
            if not (LUBLIN_BBOX['lat_min'] <= lat <= LUBLIN_BBOX['lat_max']
                    and LUBLIN_BBOX['lon_min'] <= lon <= LUBLIN_BBOX['lon_max']):
                continue
            return {'lat': lat, 'lon': lon, 'name': res.get('name') or street}
        return None

    def geocode_district(self, district: str) -> Optional[Dict]:
        """Geokoduje dzielnicę/część miasta (np. 'Zemborzyce') na centroid.

        Dla ofert agencji bez współrzędnych i bez ulicy w opisie — lepszy
        przybliżony punkt niż brak pinezki. Wynik klasy place/boundary.
        """
        key = f"district:{district.lower()}"
        if key in self.cache:
            entry = self.cache[key]
            if entry.get('result'):
                return entry['result']
            if time.time() - entry.get('ts', 0) < NEGATIVE_TTL_S:
                return None

        wait = self.delay_s - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        result = None
        try:
            r = requests.get(NOMINATIM_URL, params={
                'q': f'{district}, Lublin, Polska', 'format': 'json', 'limit': 3,
            }, headers=HEADERS, timeout=15)
            self._last_request = time.time()
            self.live_requests += 1
            r.raise_for_status()
            for res in r.json():
                lat, lon = float(res['lat']), float(res['lon'])
                if res.get('class') not in ('place', 'boundary'):
                    continue
                if 'Lublin' not in res.get('display_name', ''):
                    continue
                if not (LUBLIN_BBOX['lat_min'] <= lat <= LUBLIN_BBOX['lat_max']
                        and LUBLIN_BBOX['lon_min'] <= lon <= LUBLIN_BBOX['lon_max']):
                    continue
                result = {'lat': lat, 'lon': lon, 'name': res.get('name') or district}
                break
        except (requests.RequestException, ValueError) as e:
            print(f"      ⚠️ Nominatim błąd dla dzielnicy '{district}': {e}")
        self.cache[key] = {'result': result, 'ts': time.time()}
        return result

    def geocode_street(self, street: str) -> Optional[Dict]:
        """Geokoduje ulicę (z wariantami odmiany). Zwraca {'lat','lon','name'} lub None."""
        key = street.lower()
        if key in self.cache:
            entry = self.cache[key]
            if entry.get('result'):
                return entry['result']
            if time.time() - entry.get('ts', 0) < NEGATIVE_TTL_S:
                return None  # świeży negatywny wpis

        result = None
        for variant in nominative_variants(street):
            result = self._query(variant)
            if result:
                break
        self.cache[key] = {'result': result, 'ts': time.time()}
        return result


def refine_offer_location(offer: Dict, geocoder: StreetGeocoder) -> bool:
    """Próbuje doprecyzować lokalizację oferty (approx → street).

    Returns: True jeśli coords zostały poprawione.
    """
    loc = offer.setdefault('location', {})
    if loc.get('coords_precision') in ('exact', 'street'):
        return False  # już dobre — nie ruszamy

    # kandydaci: jawne pole street (Otodom) + ekstrakcja z tytułu i opisu
    candidates = []
    if loc.get('street'):
        candidates.append(re.sub(r'^(ul|al)\.\s*', '', loc['street']))
    text = (offer.get('title') or '') + '\n' + (offer.get('description') or '')
    candidates.extend(c for c in extract_street_candidates(text) if c not in candidates)

    for candidate in candidates:
        result = geocoder.geocode_street(candidate)
        if result:
            loc['coords'] = {'lat': result['lat'], 'lon': result['lon']}
            loc['coords_precision'] = 'street'
            loc['street'] = loc.get('street') or f"ul. {result['name']}"
            return True

    # fallback: oferta BEZ żadnych coords (agencje) → centroid dzielnicy (approx)
    if not loc.get('coords') and loc.get('district'):
        result = geocoder.geocode_district(loc['district'])
        if result:
            loc['coords'] = {'lat': result['lat'], 'lon': result['lon']}
            loc['coords_precision'] = 'approx'
            return True
    return False


if __name__ == "__main__":
    # szybki test ekstrakcji + odmiany (bez live Nominatim)
    tests = [
        ("Działka z wydaną WZ- Lublin, ul. Krężnicka", ['Krężnicka']),
        ("Działka 26 ar przy ul. Wyżynnej w Lublinie", ['Wyżynnej']),
        ("Działka budowlana 515m2 ul. Kosynierów. Dzielnica:Ponikwoda", ['Kosynierów']),
        ("Świetna lokalizacja przy alei Kraśnickiej, media", ['Kraśnickiej']),
        ("Działka bez ulicy w tekście", []),
    ]
    ok = 0
    for text, expected in tests:
        got = extract_street_candidates(text)
        status = "OK " if got == expected else "FAIL"
        ok += got == expected
        print(f"{status} {text[:50]!r} → {got}")
    print(f"\n{ok}/{len(tests)} OK")
    print("warianty 'Krężnickiej':", nominative_variants('Krężnickiej'))
    print("warianty 'Wyżynnej':", nominative_variants('Wyżynnej'))
