# CHANGELOG

## [Niewydane]

### Dodane
- Doprecyzowanie lokalizacji (`location_refiner.py`): ulica z tytułu/opisu →
  geokodowanie Nominatim (cache, limit 100/skan), precyzja `approx`→`street`.
  Pierwszy przebieg poprawił 38/52 pinezek OLX (max korekta 8,2 km).
- Deduplikacja OLX↔Otodom: ta sama działka (cena identyczna, powierzchnia ±1%,
  dystans <5 km) pokazywana raz — zostaje pinezka Otodom z linkiem do OLX.
- Statyczne API `docs/api/` (status, offers, history, health) + `docs/API.md`.
- Workflow `pages.yml` publikujący `docs/` na GitHub Pages.
- Pierwsza wersja SONARA DZIAŁKOWEGO: scraping działek na sprzedaż w Lublinie
  z OLX (działki budowlane/inwestycyjne/rolno-budowlane) i Otodom (wszystkie),
  baza `data/offers.json` z historią cen i dezaktywacją, mapa Leaflet na
  GitHub Pages (`docs/`), workflow skanera 2×/dzień i testy pytest.
