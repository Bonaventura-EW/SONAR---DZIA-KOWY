# CHANGELOG

## [Niewydane]

### Wydajność
- Płynność mapy: memoizacja ikon markerów (jeden `L.divIcon` współdzielony przez
  pinezki o identycznym wyglądzie zamiast ~380 unikalnych stringów SVG na każde
  przeliczenie filtrów; tooltip przeniesiony do opcji markera), `preferCanvas`
  oraz `updateWhenZooming:false`/`keepBuffer:2` na kafelkach (mniej przerysowań
  przy zoomie). Filtry cena/powierzchnia już wcześniej debounce'owane (300 ms).

### Dodane
- Podstrona **🔄 Ruch** (`docs/zmiany.html`) — dwukolumnowy widok ruchu na rynku:
  po lewej oferty **zniknięte** (nieaktywne, czerwone), po prawej **nowe**
  (świeży `first_seen`, zielone). Każda karta ma miniaturę, cenę + cena/m²,
  trend ceny, datę względną („3 dni temu"), a zniknięte dodatkowo czas życia
  („była X dni"). Pasek bilansu (KPI: nowe / zniknięte / bilans netto / mediana
  ceny/m² nowych / śr. czas życia), filtry okna czasu (1–90 dni / cały czas),
  źródła, „tylko od właściciela", sortowanie i wyszukiwarka. Przycisk 📍 **Mapa**
  przenosi do mapy z fokusem oferty (`index.html#offer=<id>`): `script.js`
  czyta hash, włącza potrzebne warstwy/filtry, wyśrodkowuje mapę i otwiera popup
  (działa też dla nieaktywnych i bez GPS). Wpięta w nawigację wszystkich podstron.
  10 propozycji wizualizacji w `mockups/zmiany_mockups.html` (dwie kolumny,
  oś czasu, bilans, karty+segment, tabela ruchu, lista+mini-mapa, kafelki dzienne,
  feed mobilny, bilans dzielnic, porównanie).
- Podstrona **🏢 Agencje** (`docs/agencje.html`) na wzór `profile_tracker.html`:
  zakładki per agencja (ANMA, Pasjonaci, Alternatywne BN, IdsHome) z listą ofert,
  statystykami (aktywne/archiwalne, mediana ceny/m², min/max) i sparkline ceny
  w czasie. Dane z nowego `agency_generator.py` → `docs/agency_data.json`
  (czyta pełną bazę PRZED dedupem, więc pokazuje komplet ofert agencji z
  adnotacją „też na: Otodom/OLX/Adresowo"). Wpięty w `scanner.yml` i nawigację.

### Zmienione
- Skala kolorów ceny/m² na mapie: 5 → **10 stopni** (zielony→fioletowy, decyle
  zamiast kwartyli). `map_generator.py` liczy 9 progów (0.1…0.9), `script.js`
  ma 10 kolorów; legenda buduje się automatycznie.

### Naprawione
- Mapa nie odświeżała się po automatycznym skanie: `pages.yml` (trigger `push`
  na `docs/**`) nie startował, bo skan pushuje przez `github.token`
  (`github-actions[bot]`), a GitHub z założenia nie budzi nim innych workflowów
  (ochrona antyrekurencyjna). Deploy Pages przeniesiony wprost do `scanner.yml`
  (kroki `configure-pages` + `upload-pages-artifact` + `deploy-pages`, OIDC
  `id-token` zamiast triggera push) — mapa odświeża się od razu po każdym skanie,
  bez zależności od sekretu `PAT_TOKEN`. `pages.yml` zostaje dla pushów ręcznych.
- Fałszywie dokładne pinezki Otodom (centroidy dzielnic, np. plac Zamkowy):
  `mapDetails.radius > 0` ⇒ precyzja `approx`; klastry ≥3 ofert w promieniu
  250 m flagowane jako `approx`; geokoder przyjmuje tylko `class=highway`.
  Efekt: 96 exact / 93 street / 31 approx (wcześniej 168 „exact", z czego
  ~70 stało w generycznych punktach).

### Dodane
- Scraper agencji **IdsHome** (idshome.pl) — kolejny silnik Galactica Virgo
  (jak ANMA/Pasjonaci): ten sam slug `dzialki-na-sprzedaz-{cena}zl-{area}m2-
  {lok}-o{id}` i paginacja `?page=N`, więc listing obsługuje `VirgoAgencyScraper`
  bez zmian. W odróżnieniu od pozostałych agencji strona szczegółów osadza punkt
  oferty w JS (`gmap_params.markers[].lat/long`) → uzupełniamy `coords`
  (precyzja `street`, z sanity-checkiem granic Lubelszczyzny).
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

### Dodane (2026-06-11, agencje)
- Scrapery agencji nieruchomości: ANMA i Pasjonaci (CMS Galactica Virgo —
  wspólny parser, dane w slugu URL) oraz Alternatywne BN (WordPress).
  Oferty agencji mają złotą obwódkę i osobne warstwy "Firmy / Agencje"
  (per agencja, jak w SONAR-POKOJOWY).
- Deduplikacja uogólniona na wszystkie źródła (agencje wystawiają te same
  działki na Otodom) — kanoniczna zostaje oferta z najlepszą lokalizacją.
- location_refiner: fallback geokodowania dzielnicy dla ofert agencji
  bez współrzędnych i bez ulicy w opisie.

### Dodane (2026-06-11, adresowo.pl)
- Czwarte źródło: adresowo.pl (192 oferty działek w Lublinie, coords ze stron
  szczegółów, ulica z tytułu, znacznik "bez pośredników"). Checkbox Adresowo
  w filtrze Źródło.
- Oferty Adresowo bez realnej lokalizacji (centroid miasta) trafiają uczciwie
  do sekcji "bez lokalizacji GPS" zamiast sztucznego stosu pinezek w centrum.
- Audyt paginacji wszystkich scraperów: strona z samymi powtórkami (karuzele
  Virgo, promowane) nie ucina już kolejnych stron.

### Dodane (2026-06-11, kolory typów + szybkość)
- Checkboxy typów działek z kolorowymi swatchami (kolory wspólne z wykresem
  w analityce) + przełącznik koloru pinezek: cena/m² (kwantyle) lub typ
  działki; legenda przełącza się automatycznie.
- Scraping wszystkich 6 źródeł równolegle (ThreadPoolExecutor) — skan
  z ~5 min do ~45 s (szczegóły ofert i tak tylko dla nowych, known_offers).

### Naprawione (2026-06-12)
- Automatyczne skany padały: harmonogram odpala workflow na gałęzi domyślnej
  repo (claude/...), a push szedł na main — `scanner.yml` ma teraz
  `ref: main` w checkout i `push HEAD:main`. Zalecane: zmiana gałęzi
  domyślnej repo na `main` (Settings → Branches).

### Zmienione (2026-06-12, API v2)
- API pokazuje status skanu (udany/nieudany + powód) i bilans ofert
  (+nowe / -znikłe): status.json, health.json (ok/failing/stale).
- api/history.json = 6 ostatnich skanów (nowe nadpisują stare), format
  jak w SONAR-POKOJOWY/MIESZKANIOWY (uiStatus, notification, offers).
- main.py loguje status 'completed'/'failed' i liczbę dezaktywowanych
  ofert do scan_history; nieudany skan też trafia do historii.
