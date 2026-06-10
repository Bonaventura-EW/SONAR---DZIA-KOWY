# CLAUDE.md

Wytyczne dla Claude Code (i innych agentów) pracujących w tym repozytorium.
Czytaj na starcie każdej sesji.

## Czym jest projekt

**SONAR DZIAŁKOWY** — agent monitorujący oferty sprzedaży działek w Lublinie
(OLX + Otodom), z mapą na GitHub Pages. Trzeci z rodziny sonarów; architektura
wzorowana na `SONAR-MIESZKANIOWY`, ale **celowo prostsza**:

- **Brak parsera adresów i geokodera.** Oba portale osadzają w HTML pełny JSON
  ze współrzędnymi: OLX `window.__PRERENDERED_STATE__` (coords przybliżone,
  ~1 km), Otodom `__NEXT_DATA__` (coords dokładne na stronie szczegółów).
- **GitHub Actions** skanuje 2×/dzień (`scanner.yml`), commituje wyniki na `main`.
- **GitHub Pages** serwuje `docs/` — frontend czyta `docs/data.json`.

## Przepływ danych

```
olx_scraper.py     → listing OLX → __PRERENDERED_STATE__ → znormalizowane oferty
otodom_scraper.py  → listing Otodom (__NEXT_DATA__) + strony szczegółów
                     TYLKO dla nowych ofert (coords, pełny opis, typ działki)
  ↓
main.py            → aktualizacja data/offers.json (historia cen, dezaktywacja,
                     reaktywacja, deduplikacja OLX↔Otodom, scan_history)
  ↓
map_generator.py   → docs/data.json   (mapa: oferty po dedup + kwantyle ceny/m²)
api_generator.py   → docs/api/*.json  (status / offers / history / health)
  ↓
docs/index.html + assets/script.js → mapa Leaflet (GitHub Pages)
```

## Workflowy GitHub Actions

| Plik | Co robi |
|------|---------|
| `scanner.yml` | skan 2×/dzień (8:37, 18:37 PL) + `workflow_dispatch`; commituje `data/` i `docs/` na `main` |
| `pages.yml` | deploy `docs/` na GitHub Pages po pushu na `main` dotykającym `docs/**` |
| `tests.yml` | pytest na push/PR dotykającym `src/`, `tests/` |

> 🏷️ **„Uruchom scan" (polecenie użytkownika) = odpal workflow `scanner.yml`
> na `main`** (manualny `workflow_dispatch`), NIE lokalne `python main.py`.
> Lokalnie uruchamiaj tylko gdy użytkownik wprost poprosi.

> ⚠️ **GitHub Pages musi być raz włączone ręcznie** (Settings → Pages →
> Source: **GitHub Actions**) — domyślny token Actions nie może utworzyć
> site'u Pages (`Resource not accessible by integration`). Po włączeniu
> `pages.yml` działa już automatycznie.

## Jak uruchomić

> ⚠️ Skrypty uruchamiaj z katalogu `src/` (importy między modułami zakładają
> `src/` na sys.path; ścieżki danych są kotwiczone w `paths.py` do `__file__`).

```bash
pip install -r requirements.txt
cd src
python main.py             # pełny skan (~1,5 min pierwszy, ~15 s kolejne)
python map_generator.py    # docs/data.json
python api_generator.py    # docs/api/*.json
cd ../docs && python -m http.server 8000
```

Testy: `pytest` z roota repo (konfiguracja w `pytest.ini`, `pythonpath = src`).

## Pułapki i konwencje (WAŻNE)

1. **Stabilne ID z prefiksem źródła**: `olx:CID3-IDxxxx` (slug OLX zmienia się
   przy edycji tytułu — patrz `cid.py`) oraz `otodom:<numeric_id>`.
2. **Dekodowanie OLX**: `__PRERENDERED_STATE__` to escapowany string JS;
   po `unicode_escape` trzeba naprawić polskie znaki re-enkodowaniem
   latin-1 → utf-8 (`decode_prerendered_state` w `olx_scraper.py`).
3. **Otodom: coords tylko na stronie szczegółów.** Scraper pobiera szczegóły
   wyłącznie dla ofert nieznanych bazie (`known_offers` z `main.py`) — nie
   psuj tej optymalizacji, bo skan urośnie ze ~90 s do wielu minut.
4. **Ochrona przed masową dezaktywacją** (`main.py::_mark_inactive`): działa
   PER ŹRÓDŁO — jeśli scraper źródła zwróci 0 ofert albo <30% liczby aktywnych,
   dezaktywacja tego źródła jest pomijana (blokada portalu ≠ zniknięcie ofert).
   Nie usuwaj tej ochrony.
5. **Nie nadpisuj dokładnych coords przybliżonymi** — logika w
   `_update_existing` (precision `exact` > `approx`).
6. **OLX dokleja wyniki „z okolicy"** na końcu listingu — filtrujemy po
   `cityNormalizedName == 'lublin'`.
7. **Deduplikacja OLX↔Otodom** (`main.py::_tag_cross_portal_duplicates`):
   ta sama cena + powierzchnia ±1% + dystans <5 km (gdy oba mają GPS) →
   oferta OLX dostaje `duplicate_of` (ID oferty Otodom) i oba dostają
   `also_at` (URL drugiego ogłoszenia). Jedna oferta Otodom paruje się z
   maksymalnie jednym OLX. `map_generator` i `api_generator` **chowają**
   oferty z aktywnym `duplicate_of` — na mapie zostaje pinezka Otodom
   (dokładniejsza lokalizacja) z linkiem do OLX w popupie.
8. **Nie modyfikuj ręcznie `data/offers.json`** — plik generowany przez skan.
9. Zmiany oznaczaj datowanym komentarzem `# FIX YYYY-MM-DD: opis`, a istotne
   wpisuj do `CHANGELOG.md` (konwencja z siostrzanych sonarów).

## Konwencja commitów

Format `typ(zakres): opis` po polsku (`fix(scanner):`, `feat(map):`).
Skany automatyczne commitują jako `🤖 Automatyczny scan: <data>`.
