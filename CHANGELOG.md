# CHANGELOG

## [Niewydane]

### Naprawione
- Fałszywie dokładne pinezki Otodom (centroidy dzielnic, np. plac Zamkowy):
  `mapDetails.radius > 0` ⇒ precyzja `approx`; klastry ≥3 ofert w promieniu
  250 m flagowane jako `approx`; geokoder przyjmuje tylko `class=highway`.
  Efekt: 96 exact / 93 street / 31 approx (wcześniej 168 „exact", z czego
  ~70 stało w generycznych punktach).

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
