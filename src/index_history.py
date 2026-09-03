"""Dzienny stan bazy — ŹRÓDŁO PRAWDY dla Indeksu podaży (docs/analytics.html).

Dlaczego osobny plik, skoro jest `scan_history.json`
----------------------------------------------------
`scan_history.json` trzyma tylko OSTATNIE 200 skanów (przy 2 skanach dziennie
≈ 100 dni) — starsze wpisy wypadają i wykres skracałby się z każdym skanem.
Ten plik rośnie bezterminowo: jeden wpis na dzień, nigdy nie przycinany.

Konwencja dnia: `active` = MAKSIMUM z odczytów danego dnia. Skan częściowy
(blokada portalu) zaniża stan bazy, więc bierzemy najpełniejszy obraz dnia —
inaczej przerwany scrape rysowałby się jak załamanie rynku. `record()` nigdy
nie obniża już zapisanej wartości.

Dzień bez ANI JEDNEGO skanu (awaria Actions) nie ma tu wpisu, a
`daily_series()` zwraca dla niego `None` — front rysuje lukę zamiast
zmyślonego zera.

Dwie liczby na dzień:
  `active`       — ile ofert ma w bazie `active=true` (surowy stan bazy;
                   ta sama liczba, którą zapisuje scan_history),
  `active_dedup` — to samo po ukryciu duplikatów między źródłami
                   (`duplicate_of` wskazujące na aktywną ofertę) — czyli tyle,
                   ile pinezek widać na mapie.
Indeks rysujemy z `active`, bo tylko tę liczbę da się odtworzyć wstecz:
`duplicate_of` to stan BIEŻĄCY, historia powiązań nigdzie nie jest zapisywana.
`active_dedup` zbiera się od wdrożenia (2026-09-03) na przyszłość.

Historia sprzed wdrożenia jest odtworzona z `data/scan_history.json`
(`backfill_from_scan_history()`); te wpisy mają `backfilled: true` i nie mają
`active_dedup`. Pliku nie edytuj ręcznie — dopisuje go każdy skan.
"""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import paths

NOTE = ("Dzienny stan bazy: ile ofert ma active=true po skanie. Zrodlo prawdy dla "
        "Indeksu podazy (docs/analytics.html). active = maksimum z odczytow danego "
        "dnia (skan czesciowy nie moze zanizyc historii). Nie edytowac recznie.")


def _path(base_dir=None) -> Path:
    if base_dir is None:
        return Path(paths.INDEX_HISTORY_JSON)
    return Path(base_dir) / 'data' / 'index_history.json'


def load(base_dir=None) -> dict:
    """Cała zawartość pliku. Brak pliku / uszkodzony JSON = pusty szkielet."""
    try:
        with open(_path(base_dir), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {'note': NOTE, 'days': {}}
    if not isinstance(data, dict) or not isinstance(data.get('days'), dict):
        return {'note': NOTE, 'days': {}}
    return data


def save(data: dict, base_dir=None) -> None:
    """Zapis atomowy (tmp + replace) — plik dopisuje skan, a równolegle czyta go
    generator; ucięty JSON kasowałby całą historię Indeksu."""
    data['note'] = NOTE
    data['generated_at'] = datetime.now().astimezone().isoformat()
    data['days'] = {day: data['days'][day] for day in sorted(data['days'])}
    path = _path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def record(active: int, timestamp: str = None, base_dir=None,
           extra: dict = None) -> dict:
    """Dopisuje wynik skanu do dnia wynikającego z `timestamp`.

    Wartość dnia to maksimum z odczytów — skan częściowy nigdy nie obniży już
    zapisanej liczby. `scans` liczy wszystkie odczyty dnia (także niższe), żeby
    dało się poznać dzień z jednym skanem zamiast dwóch.

    `extra` to dodatkowe liczniki tego samego odczytu (`active_dedup`,
    `active_olx`, ...) — zapisujemy je RAZEM z nowym maksimum, żeby wszystkie
    liczby w dniu pochodziły z jednego, najpełniejszego skanu. Inaczej udział
    wyróżnień mieszałby licznik z pełnego skanu z mianownikiem z ubogiego.
    """
    if active is None:
        return {}
    ts = timestamp or datetime.now().astimezone().isoformat()
    try:
        day = datetime.fromisoformat(ts).date().isoformat()
    except (ValueError, TypeError):
        day = date.today().isoformat()

    data = load(base_dir)
    entry = data['days'].get(day) or {'active': 0, 'scans': 0}
    entry['scans'] = entry.get('scans', 0) + 1
    if active > entry.get('active', 0):
        entry['active'] = active
        entry['ts'] = ts
        for key, value in (extra or {}).items():
            if value is not None:
                entry[key] = value
    # dzień dotknięty przez żywy skan przestaje być odtworzony z historii skanów
    entry.pop('backfilled', None)
    data['days'][day] = entry
    save(data, base_dir)
    return entry


def daily_series(start: date = None, base_dir=None):
    """[(date, active|None), ...] — kolejne dni od `start` (albo od pierwszego
    zapisanego) do ostatniego zapisanego. `None` = dzień bez skanu."""
    days = load(base_dir)['days']
    parsed = {}
    for key, entry in days.items():
        try:
            parsed[date.fromisoformat(key)] = (entry or {}).get('active')
        except (ValueError, TypeError):
            continue
    if not parsed:
        return []
    first = max(start, min(parsed)) if start else min(parsed)
    last = max(parsed)
    out = []
    day = first
    while day <= last:
        out.append((day, parsed.get(day)))
        day += timedelta(days=1)
    return out


def daily_field(field: str, base_dir=None) -> dict:
    """{date: wartość} dla dowolnego licznika dnia (np. `active_olx`).

    Dni bez tego pola (zapisane przed jego wdrożeniem albo odtworzone
    z scan_history) po prostu nie trafiają do wyniku — wołający decyduje,
    czym je uzupełnić.
    """
    out = {}
    for key, entry in load(base_dir)['days'].items():
        value = (entry or {}).get(field)
        if value is None:
            continue
        try:
            out[date.fromisoformat(key)] = value
        except (ValueError, TypeError):
            continue
    return out


def backfill_from_scan_history(base_dir=None) -> int:
    """Uzupełnia brakujące dni z `data/scan_history.json` (max `active` z dnia).

    Idempotentne i nieniszczące: dzień już zapisany przez żywy skan zostaje
    nietknięty. Sensowne do jednorazowego zasiania historii i jako asekuracja,
    gdyby index_history.json kiedyś przepadł, a scan_history jeszcze pamiętał
    ostatnie ~100 dni. Zwraca liczbę dopisanych dni.
    """
    path = (Path(paths.SCAN_HISTORY_JSON) if base_dir is None
            else Path(base_dir) / 'data' / 'scan_history.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            history = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0
    scans = history.get('scans', []) if isinstance(history, dict) else (history or [])

    best = {}
    for scan in scans:
        # starsze wpisy (czerwiec 2026) nie mają pola `status` — brak statusu
        # przy zapisanym `active` znaczy „skan doszedł do końca"
        if scan.get('status') not in (None, 'completed', 'warning'):
            continue
        ts, active = scan.get('timestamp'), scan.get('active')
        if not ts or active is None:
            continue
        try:
            day = datetime.fromisoformat(ts).date().isoformat()
        except (ValueError, TypeError):
            continue
        if active > best.get(day, (0, ''))[0]:
            best[day] = (active, ts)

    data = load(base_dir)
    added = 0
    for day, (active, ts) in best.items():
        if day in data['days']:
            continue
        data['days'][day] = {'active': active, 'scans': 1, 'ts': ts,
                             'backfilled': True}
        added += 1
    if added:
        save(data, base_dir)
    return added


if __name__ == '__main__':
    n = backfill_from_scan_history()
    series = daily_series()
    print(f"📈 index_history: dopisano {n} dni z scan_history; "
          f"historia {len(series)} dni"
          + (f" ({series[0][0]} → {series[-1][0]})" if series else ""))
