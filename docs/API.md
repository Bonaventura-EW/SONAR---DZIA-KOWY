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
  "last_scan_status": "completed",
  "last_scan_success": true,
  "last_scan_new_offers": 8,
  "last_scan_disappeared_offers": 2,
  "last_scan_duration_s": 46.3,
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

**6 ostatnich skanów** (nowe nadpisują stare), najnowszy pierwszy — format
analogiczny do SONAR-POKOJOWY/MIESZKANIOWY:

```json
{
  "system": "sonar-dzialkowy",
  "count": 6,
  "scans": [{
    "timestamp": "2026-06-12T22:18:08+02:00",
    "uiStatus": "success",            // "success" | "failure"
    "rawStatus": "completed",
    "failureReason": null,
    "durationFormatted": "46s",
    "notification": {"title": "✅ Skan 22:18 — +8 nowych / -2 znikło", "body": "..."},
    "offers": {"new": 8, "disappeared": 2, "updated": 478,
               "active": 485, "activeDelta": -1, "totalInDb": 502,
               "bySource": {"olx": 53, "otodom": 171, "adresowo": 192, "agencies": 70}}
  }]
}
```

### `GET api/health.json`

```json
{"status": "ok", "last_scan_status": "completed", "hours_since_last_scan": 0.1}
```

`status`: `ok` (świeży i udany) / `failing` (świeży, ale nieudany) /
`stale` (brak skanu od >26 h).

## Pełne dane mapy

`GET data.json` (katalog główny Pages) — to samo co `api/offers.json` plus
oferty nieaktywne (historia) i kwantyle ceny/m² używane do kolorowania pinezek.
