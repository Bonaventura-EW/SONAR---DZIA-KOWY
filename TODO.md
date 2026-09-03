# TODO — pomysły na przyszłość

Lista rzeczy do zrobienia w SONARZE DZIAŁKOWYM. Zrealizowane pozycje
przenoś do `CHANGELOG.md`.

## Do zrobienia

- [ ] **Przepływy przestaną przepisywać własną historię.** Indeks czyta
  mierzony `data/index_history.json` i stary punkt już się nie zmienia, ale
  wykresy odpływu / nowych ofert / reaktywacji liczą się z BIEŻĄCEGO
  `data/offers.json`. Gdy `main._cleanup_old` (548 dni) zacznie kasować
  najstarsze oferty — pierwsze pod koniec 2027 — lewy skraj tych wykresów
  zacznie się kurczyć z każdym skanem. Lekarstwo: dopisywać dzienne sumy
  zdarzeń do `index_history` (obok `active`) i czytać je tak jak Indeks,
  z rekonstrukcją jako źródłem awaryjnym. Uwaga: filtr mrugnięć
  (`trend_generator.FLAP_MAX_DAYS`) działa na parach zdarzeń jednej oferty,
  więc zapisywać trzeba liczby JUŻ po odsiewie albo same pary.

## Zrobione

- [x] **Bardziej precyzyjne lokalizacje** (2026-06-11): `location_refiner.py`
  wyciąga ulicę z tytułu/opisu (regex + polska odmiana) i geokoduje przez
  Nominatim (cache w `data/geocoding_cache.json`); precyzja `approx` →
  `street`, coords `exact` z Otodom nieruszane. Pierwsze uruchomienie
  doprecyzowało 38/52 ofert OLX (największa korekta: 8,2 km).

- [x] Mapa + scraping OLX/Otodom z deduplikacją (2026-06-10)
- [x] Monitoring, analityka, nowe logo i szata graficzna (2026-06-10)
- [x] Statyczne API `docs/api/` (2026-06-10)
