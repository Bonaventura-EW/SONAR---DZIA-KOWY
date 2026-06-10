# API — SONAR DZIAŁKOWY

Statyczne API serwowane przez GitHub Pages, regenerowane przy każdym skanie
(2×/dzień) przez `src/api_generator.py`.

Baza URL: `https://bonaventura-ew.github.io/SONAR---DZIA-KOWY/api/`

## Endpointy

### `GET api/status.json`

Statystyki bieżącego stanu bazy.

```json
{
  "generated_at": "2026-06-10T20:07:04+02:00",
  "last_scan": "2026-06-10T20:06:18+02:00",
  "next_scan": "2026-06-11T08:00:00+02:00",
  "active_offers": 182,
  "total_in_db": 220,
  "median_price_per_m2": 396.44,
  "by_source": {"olx": 14, "otodom": 168},
  "by_plot_type": {"budowlana": 124, "inwestycyjna": 19, "rolna": 4, "inna": 32}
}
```

Uwaga: `by_source` liczy oferty **po deduplikacji** — działka wystawiona na
obu portalach liczona jest raz (zostaje wpis Otodom).

### `GET api/offers.json`

Wszystkie aktywne oferty po deduplikacji OLX↔Otodom.

```json
{
  "generated_at": "...",
  "count": 182,
  "offers": [
    {
      "id": "otodom:68093538",
      "source": "otodom",
      "url": "https://www.otodom.pl/pl/oferta/...",
      "title": "Piękna, zielona działka pod Twój dom",
      "price": 690000,
      "previous_price": null,
      "price_trend": null,
      "price_history": [690000],
      "area_m2": 1200,
      "price_per_m2": 575,
      "plot_type": "budowlana",
      "district": "Sławin",
      "street": "ul. Poligonowa",
      "coords": {"lat": 51.2811, "lon": 22.529907},
      "coords_precision": "exact",
      "description": "…(max 1200 znaków)…",
      "is_private_owner": false,
      "image": "https://…",
      "first_seen": "2026-06-10T19:00:00+02:00",
      "last_seen": "2026-06-10T20:06:00+02:00",
      "active": true,
      "days_active": 0,
      "also_at": "https://www.olx.pl/d/oferta/…"
    }
  ]
}
```

Pola:
- `coords_precision`: `"exact"` (Otodom, dokładny punkt) lub `"approx"`
  (OLX rozmywa pinezkę w promieniu ~1 km)
- `plot_type`: `budowlana` / `inwestycyjna` / `rolno-budowlana` / `rolna` /
  `rekreacyjna` / `leśna` / `siedliskowa` / `inna`
- `also_at`: URL tej samej działki na drugim portalu (jeśli wykryto)
- `price_trend`: `"down"` / `"up"` po zmianie ceny, `previous_price` = stara cena

### `GET api/history.json`

Ostatnie 50 skanów (czas trwania, liczby ofert, nowe/zaktualizowane).

### `GET api/health.json`

```json
{"status": "ok", "last_scan": "...", "hours_since_last_scan": 0.1}
```

`status` = `"stale"` gdy ostatni skan starszy niż 26 h.

## Pełne dane mapy

`GET data.json` (katalog główny Pages) — to samo co `api/offers.json` plus
oferty nieaktywne (historia) i kwantyle ceny/m² używane do kolorowania pinezek.
