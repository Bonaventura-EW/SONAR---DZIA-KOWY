# TODO — pomysły na przyszłość

Lista rzeczy do zrobienia w SONARZE DZIAŁKOWYM. Zrealizowane pozycje
przenoś do `CHANGELOG.md`.

## Do zrobienia

(pusto — dopisuj kolejne pomysły tutaj)

## Zrobione

- [x] **Bardziej precyzyjne lokalizacje** (2026-06-11): `location_refiner.py`
  wyciąga ulicę z tytułu/opisu (regex + polska odmiana) i geokoduje przez
  Nominatim (cache w `data/geocoding_cache.json`); precyzja `approx` →
  `street`, coords `exact` z Otodom nieruszane. Pierwsze uruchomienie
  doprecyzowało 38/52 ofert OLX (największa korekta: 8,2 km).

- [x] Mapa + scraping OLX/Otodom z deduplikacją (2026-06-10)
- [x] Monitoring, analityka, nowe logo i szata graficzna (2026-06-10)
- [x] Statyczne API `docs/api/` (2026-06-10)
