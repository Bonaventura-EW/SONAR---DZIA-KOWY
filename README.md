# SONAR DZIAŁKOWY 🛰️

Automatyczny agent monitorujący oferty sprzedaży **działek w Lublinie**
(źródła: **OLX** + **Otodom**) i zaznaczający je na mapie.
Trzeci z rodziny sonarów (obok [SONAR-POKOJOWY](https://github.com/Bonaventura-EW/SONAR-POKOJOWY)
i [SONAR-MIESZKANIOWY](https://github.com/Bonaventura-EW/SONAR-MIESZKANIOWY)).

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

## Uruchomienie lokalne

```bash
pip install -r requirements.txt

cd src
python main.py            # pełny skan (~1,5 min)
python map_generator.py   # generuje docs/data.json

cd ../docs && python -m http.server 8000   # podgląd: http://localhost:8000
```

## Testy

```bash
pip install pytest
pytest
```
