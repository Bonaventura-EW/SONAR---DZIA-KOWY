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
                     reaktywacja, parowanie OLX↔Otodom, scan_history)
  ↓
map_generator.py   → docs/data.json (kompaktowe oferty + kwantyle ceny/m²)
  ↓
docs/index.html + assets/script.js → mapa Leaflet
```

## Jak uruchomić

> ⚠️ Skrypty uruchamiaj z katalogu `src/` (importy między modułami zakładają
> `src/` na sys.path; ścieżki danych są kotwiczone w `paths.py` do `__file__`).

```bash
pip install -r requirements.txt
cd src
python main.py             # pełny skan (~1,5 min, ~220 ofert)
python map_generator.py    # docs/data.json
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
7. **Parowanie OLX↔Otodom**: ta sama cena + powierzchnia ±1% → pole `also_at`.
8. **Nie modyfikuj ręcznie `data/offers.json`** — plik generowany przez skan.
9. Zmiany oznaczaj datowanym komentarzem `# FIX YYYY-MM-DD: opis`, a istotne
   wpisuj do `CHANGELOG.md` (konwencja z siostrzanych sonarów).

## Konwencja commitów

Format `typ(zakres): opis` po polsku (`fix(scanner):`, `feat(map):`).
Skany automatyczne commitują jako `🤖 Automatyczny scan: <data>`.
