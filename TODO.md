# TODO — pomysły na przyszłość

Lista rzeczy do zrobienia w SONARZE DZIAŁKOWYM. Zrealizowane pozycje
przenoś do `CHANGELOG.md`.

## Do zrobienia

- [ ] **Bardziej precyzyjne lokalizacje.** Część ogłoszeń ma w tytule/opisie
  nazwę ulicy (np. „Działka ul. Wólczańska"), a pinezka stoi w centroidzie
  dzielnicy / przybliżonym punkcie OLX (~1 km). Pomysł: wyciągać ulicę
  regexem z tytułu+opisu i geokodować (Nominatim z cache, jak w
  SONAR-MIESZKANIOWY — `geocoder.py` z polską fleksją), ale TYLKO gdy
  poprawia to precyzję (`approx` → `street`); nie nadpisywać dokładnych
  coords z Otodom (`exact`).

## Zrobione

- [x] Mapa + scraping OLX/Otodom z deduplikacją (2026-06-10)
- [x] Monitoring, analityka, nowe logo i szata graficzna (2026-06-10)
- [x] Statyczne API `docs/api/` (2026-06-10)
