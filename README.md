# SONAR DZIAŁKOWY 🛰️

Automatyczny agent monitorujący oferty sprzedaży **działek w Lublinie**
(źródła: **OLX** + **Otodom**) i zaznaczający je na mapie.
Trzeci z rodziny sonarów (obok [SONAR-POKOJOWY](https://github.com/Bonaventura-EW/SONAR-POKOJOWY)
i [SONAR-MIESZKANIOWY](https://github.com/Bonaventura-EW/SONAR-MIESZKANIOWY)).

**🌍 Strona:** <https://bonaventura-ew.github.io/SONAR---DZIA-KOWY/>

> ⚙️ Jednorazowa konfiguracja po utworzeniu repo: **Settings → Pages →
> Source: GitHub Actions** — potem workflow `pages.yml` publikuje stronę
> automatycznie przy każdej zmianie w `docs/`.

## Jak działa

- **GitHub Actions** uruchamia skan 2×/dzień (`.github/workflows/scanner.yml`)
- **GitHub Pages** serwuje statyczny frontend z katalogu `docs/`
- **Źródłem prawdy są pliki JSON** w `data/` (commitowane przez Actions)
- Bez serwera, bez bazy SQL

### Źródła danych

| Portal | Co dostajemy | Lokalizacja |
|--------|-------------|-------------|
| OLX (działki budowlane / inwestycyjne / rolno-budowlane) | cena, powierzchnia, cena/m², typ, opis | przybliżona (~1 km) z listingu |
| Otodom (wszystkie działki, Lublin) | cena, powierzchnia, cena/m², typ, opis, ulica, dzielnica | **dokładna** ze strony szczegółów |

Oba portale osadzają dane w JSON (`__PRERENDERED_STATE__` / `__NEXT_DATA__`),
więc nie ma parsowania HTML kart ani geokodowania adresów.

## Funkcje mapy

- pinezki kolorowane wg **ceny za m²** (kwantyle: zielony = tanio, czerwony = drogo)
- pełna pinezka = dokładna lokalizacja (Otodom), obwódka = przybliżona (OLX)
- filtry: źródło, typ działki, cena, powierzchnia, tylko nowe, tylko od właściciela
- historia cen (📉/📈) i reaktywacje ofert
- wykrywanie tej samej działki na obu portalach (ta sama cena + powierzchnia → link „Druga oferta")
- nieaktywne oferty zostają w bazie jako historia

## API (statyczne, GitHub Pages)

| Endpoint | Zawartość |
|----------|-----------|
| `api/status.json` | statystyki: liczba ofert, mediana ceny/m², podział wg źródła i typu |
| `api/offers.json` | wszystkie aktywne oferty (po deduplikacji OLX↔Otodom) |
| `api/history.json` | historia ostatnich 50 skanów |
| `api/health.json` | healthcheck: świeżość skanu + **alarmy awarii źródeł** (`degraded`, gdy portal przestał zwracać oferty) |

Szczegóły i przykłady odpowiedzi: [docs/API.md](docs/API.md).

Deduplikacja: ta sama działka wystawiona na obu portalach (identyczna cena,
powierzchnia ±1%, odległość <5 km) liczona jest raz — zostaje wpis z Otodom
(dokładniejsza lokalizacja) z linkiem `also_at` do ogłoszenia OLX.

## Uruchomienie lokalne

```bash
pip install -r requirements.txt

cd src
python main.py            # pełny skan (~1,5 min)
python map_generator.py   # generuje docs/data.json
python api_generator.py   # generuje docs/api/*.json

cd ../docs && python -m http.server 8000   # podgląd: http://localhost:8000
```

## Testy

```bash
pip install pytest
pytest
```
