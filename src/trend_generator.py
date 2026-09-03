#!/usr/bin/env python3
"""Generator docs/trend_data.json — szeregi czasowe rynku działek.

Zasila sekcję „Indeks podaży i ruch na rynku" w docs/analytics.html:

  * Indeks    — dzienna liczba aktywnych ofert (stan rynku), z rozbiciem na
                pasma świeże / recykling,
  * odpływ    — ile ofert znika z listingów danego dnia,
  * napływ    — nowe / reaktywacje / suma,
  * promowane — płatne wyróżnienia OLX + ich udział w rynku.

Indeks czytamy z data/index_history.json — MIERZONEGO stanu bazy po każdym
skanie (patrz src/index_history.py), nie z rekonstrukcji wstecznej. Różnica jest
istotna: oferta, która zniknęła w czerwcu i wróciła w sierpniu, ma w bazie jeden
ciągły przedział `first_seen … last_seen`, więc rekonstrukcja liczyłaby ją jako
żywą przez całą przerwę i zawyżała przeszłość. Rekonstrukcja została jako
`build_series_reconstructed()` — awaryjne źródło, gdy nie ma zapisanej historii.

Wzorowane na trend.html z SONAR-POKOJOWY, dostosowane do danych tego repo
(daty deaktywacji/reaktywacji trzymamy w listach dopiero od 2026-09-03 —
patrz `collect_dates`).
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytz

import index_history
import paths

TITLE = "Lublin – działki na sprzedaż"
# strefa scannera: „dziś" liczymy tak samo jak main.py stemplujący zdarzenia
TZ = pytz.timezone('Europe/Warsaw')
UNIT = "ofert"
DAY_MS = 86_400_000

# Pierwszy wiarygodny dzień. Baza zapełniała się 10–11.06.2026 (220 + 274 oferty
# pierwszego i drugiego dnia) — to napełnianie bazy, nie napływ na rynek.
# Od 12.06 Indeks i przepływy opisują już rynek, nie rozpęd scrapera.
RELIABLE_START = date(2026, 6, 12)

# Dzień z liczbą deaktywacji / reaktywacji powyżej progu traktujemy jako artefakt
# pipeline'u (częściowy scrape przepuszczony przez ochronę z main._mark_inactive:
# hurtowa deaktywacja, a po niej hurtowy powrót), nie ruch rynkowy. Taki dzień
# rysuje się jako luka i nie wchodzi do średniej ani statystyk. Przy rynku ~480
# ofert i typowym ruchu ~5/dzień próg 60 (≈12% rynku w jedną dobę) nic dziś nie
# tnie — rekordy to 27 i 26 — i zostaje jako tania asekuracja na przyszłość.
OUTFLOW_ARTIFACT_THRESHOLD = 60
REACT_ARTIFACT_THRESHOLD = 60

# „Mrugnięcie" pipeline'u: oferta znika z listingu i wraca w ciągu tylu dni.
# To NIE jest ruch rynkowy, tylko częściowy scrape (ochrona z main._mark_inactive
# łapie tylko katastrofy — przy 30% progu scraper agencji, który zwrócił 229 ofert
# zamiast 265, spokojnie zdezaktywował 23 żywe oferty 06.07.2026, a następny skan
# je wskrzesił) albo chwilowe schowanie oferty przez portal. W bazie 66% par
# „zniknęła → wróciła" domyka się w ≤3 dni; bez tego filtru rekordy odpływu (27)
# i reaktywacji (26) na wykresach to były dwie strony tego samego zacięcia.
FLAP_MAX_DAYS = 3

# Ile skanów w pełnym dniu (scanner.yml: 8:37 i 18:37). Dzień z mniejszą liczbą
# odczytów, jeśli to DZISIAJ, jest jeszcze w toku — jego słupek może tylko urosnąć.
SCANS_PER_DAY = 2


def _day_ms(d: date) -> int:
    """Epoch (ms) dla południa danego dnia — punkt ląduje w środku dnia na osi."""
    return int(datetime(d.year, d.month, d.day, 12, 0).timestamp() * 1000)


def _d(iso_string: str) -> date:
    return datetime.fromisoformat(iso_string).date()


def collect_dates(offer, list_field, scalar_field):
    """Wszystkie daty zdarzenia — z listy i ze starego pola pojedynczego.

    Do 2026-09-03 main.py zapisywał wyłącznie `deactivated_at` / `reactivated_at`,
    czyli OSTATNIE zdarzenie danego typu: oferta, która znikała trzykrotnie,
    zostawiła jeden ślad. Od wdrożenia list (`deactivation_dates`,
    `reactivation_dates`) historia domyka się sama, ale stare wpisy pozostają
    zaniżone — dlatego czytamy oba źródła i sklejamy je bez powtórek.
    """
    out = set()
    for raw in (offer.get(list_field) or []):
        try:
            out.add(_d(str(raw)))
        except (ValueError, TypeError):
            continue
    scalar = offer.get(scalar_field)
    if scalar:
        try:
            out.add(_d(str(scalar)))
        except (ValueError, TypeError):
            pass
    return sorted(out)


def life_events(offer):
    """(deaktywacje, reaktywacje, ile par odsiano) — zdarzenia życia oferty
    po odfiltrowaniu „mrugnięć" pipeline'u (patrz FLAP_MAX_DAYS).

    Każdą deaktywację parujemy z najbliższym późniejszym powrotem. Para krótsza
    niż FLAP_MAX_DAYS wypada Z OBU serii naraz — inaczej wykres odpływu i wykres
    reaktywacji pokazywałyby dwa „rekordy rynkowe" będące jednym zacięciem
    scrapera. Powrót domykający deaktywację, która ZOSTAJE, też zostaje.
    """
    deactivations = collect_dates(offer, 'deactivation_dates', 'deactivated_at')
    reactivations = collect_dates(offer, 'reactivation_dates', 'reactivated_at')

    drop_d, drop_r, matched = set(), set(), set()
    for i, gone in enumerate(deactivations):
        back = next((j for j, r in enumerate(reactivations)
                     if j not in matched and r >= gone), None)
        if back is None:
            continue
        matched.add(back)
        if (reactivations[back] - gone).days <= FLAP_MAX_DAYS:
            drop_d.add(i)
            drop_r.add(back)

    return (
        [d for i, d in enumerate(deactivations) if i not in drop_d],
        [r for j, r in enumerate(reactivations) if j not in drop_r],
        len(drop_d),
    )


def build_spans(offers):
    """[(offer, [(start, end), ...]), ...] — PRZEDZIAŁY życia każdej oferty.

    Oferta może żyć na raty: zniknęła z listingu (deaktywacja) i wróciła
    (reaktywacja). Każda taka przerwa zamyka jeden przedział i otwiera następny,
    więc dzień w środku przerwy nie liczy się jako żywy.

    Przedziały służą TYLKO podziałowi Indeksu na pasma (świeże / recykling) —
    sam Indeks jest mierzony, nie odtwarzany (patrz `build_series`).

    end ostatniego przedziału = dziś dla ofert wciąż aktywnych (last_seen bywa
    w tyle, gdy scraper pomija znane oferty), inaczej last_seen.
    """
    today = max(
        (_d(o['last_seen']) for o in offers if o.get('last_seen')),
        default=date.today(),
    )
    spans = []
    for o in offers:
        if not o.get('first_seen') or not o.get('last_seen'):
            continue
        try:
            start = _d(o['first_seen'])
            final_end = today if o.get('active') else _d(o['last_seen'])
        except (ValueError, TypeError):
            continue
        if final_end < start:
            final_end = start

        gone, back, _ = life_events(o)
        deactivations = [d for d in gone if start <= d <= final_end]
        reactivations = back

        intervals = []
        cursor = start
        for gap_start in deactivations:
            if gap_start < cursor:
                continue
            intervals.append((cursor, gap_start))
            back = next((r for r in reactivations if r >= gap_start), None)
            if back is None or back > final_end:
                cursor = None
                break
            cursor = back
        if cursor is not None:
            intervals.append((cursor, final_end))
        elif o.get('active') and intervals:
            # Oferta jest AKTYWNA, ale po ostatniej deaktywacji nie ma daty
            # powrotu (niespójny rekord). Skoro żyje dziś, domykamy ostatni
            # przedział do końca zamiast chować ją z wykresu na dobre.
            last_start, _ = intervals[-1]
            intervals[-1] = (last_start, final_end)
        spans.append((o, intervals))
    return spans, today


def _alive(intervals, day):
    """Czy oferta żyła danego dnia. Przedziały mogą się stykać (deaktywacja
    i powrót tego samego dnia) — liczy się raz, `any` nie sumuje."""
    return any(s <= day <= e for s, e in intervals)


def build_series(offers, base_dir=None):
    """Dzienna seria [[ms, aktywne|None], ...] — MIERZONY stan bazy.

    Źródłem jest data/index_history.json: ile ofert miało `active=true` po skanie
    danego dnia. `None` = dzień bez ani jednego skanu (awaria Actions) — front
    rysuje lukę zamiast zmyślonego zera.

    Gdy pliku nie ma (świeży klon, repo-brat bez historii), spadamy na
    rekonstrukcję — z jej znanym zawyżeniem przeszłości.
    """
    measured = index_history.daily_series(start=RELIABLE_START, base_dir=base_dir)
    if measured:
        return [[_day_ms(day), value] for day, value in measured]
    return build_series_reconstructed(offers)


def build_series_reconstructed(offers):
    """AWARYJNE źródło Indeksu: rekonstrukcja wsteczna z offers.json.

    Zawyża przeszłość — przerwy w życiu ofert sprzed wdrożenia list dat są
    niewidoczne, a zawyżenie maleje z wiekiem punktu, więc prawy koniec
    sztucznie opada. Używane tylko, gdy nie ma data/index_history.json.
    """
    spans, today = build_spans(offers)
    starts = [iv[0][0] for _, iv in spans if iv]
    if not starts:
        return []
    start = max(RELIABLE_START, min(starts))
    return [[_day_ms(day), sum(1 for _, iv in spans if _alive(iv, day))]
            for day in _daily_range(start, today)]


def _daily_range(start, today):
    """Lista kolejnych dni [start .. today] (włącznie)."""
    days = []
    day = start
    while day <= today:
        days.append(day)
        day += timedelta(days=1)
    return days


def _axis(offers, series=None):
    """Wspólna oś dni dla wszystkich szeregów: dokładnie te dni, które są na
    Indeksie. Dzięki temu odpływ, napływ i pasma stoją w tych samych słupkach."""
    if series:
        days = [datetime.fromtimestamp(ms / 1000).date() for ms, _ in series]
        return days, days[-1]
    spans, today = build_spans(offers)
    starts = [iv[0][0] for _, iv in spans if iv]
    if not starts:
        return [], today
    return _daily_range(max(RELIABLE_START, min(starts)), today), today


def _flow_metric(counts, days, exclude=None, provisional=None):
    """Standardowy blok: szereg dzienny + średnia krocząca 7 dni + statystyki.

    counts:      dict {date: liczba zdarzeń tego dnia}
    days:        uporządkowana lista kolejnych dni (oś czasu)
    exclude:     zbiór dni-artefaktów. Taki dzień rysuje się jako LUKA
                 (daily=None), nie wchodzi do średniej kroczącej ani do
                 statystyk — żeby nierynkowy pik nie zniekształcał trendu.
    provisional: DZIŚ, jeśli dzień jeszcze się nie skończył (patrz
                 `provisional_day`). Słupek zostaje na wykresie — to prawdziwa
                 liczba zdarzeń do tej pory — ale nie wchodzi do średniej
                 kroczącej ani do statystyk. Inaczej pół dnia (0 nowych ofert
                 o 9 rano) ciągnęłoby trend w dół i podmieniało rekordy;
                 dokładnie ten błąd sprawiał, że prawy koniec wykresu zawsze
                 opadał.
    """
    exclude = exclude or set()
    skip = set(exclude) | ({provisional} if provisional else set())

    daily = [[_day_ms(d), None if d in exclude else counts.get(d, 0)] for d in days]

    # średnia krocząca 7 dni licząca tylko dni „zdrowe" i ZAMKNIĘTE w oknie
    avg = []
    for i, d in enumerate(days):
        window = [counts.get(days[j], 0)
                  for j in range(max(0, i - 6), i + 1)
                  if days[j] not in skip]
        avg.append([_day_ms(d), round(sum(window) / len(window), 1) if window else None])

    clean = [(d, counts.get(d, 0)) for d in days if d not in skip]
    total = sum(v for _, v in clean)
    ndays = len(clean)
    mx = max((v for _, v in clean), default=0)
    # dzień rekordu: ostatnie (najświeższe) wystąpienie maksimum
    max_day_date = next((d for d, v in reversed(clean) if v == mx), None)

    return {
        'daily': daily,
        'avg': avg,
        'total': total,
        'rate': round(total / ndays, 1) if ndays else 0,
        'max_day': mx,
        'max_ts': _day_ms(max_day_date) if max_day_date else None,
        'max_label': max_day_date.strftime('%d.%m') if max_day_date else '',
    }


def provisional_day(series, base_dir=None):
    """Ostatni dzień serii, JEŚLI jeszcze trwa — inaczej None.

    „Trwa" = to dzisiaj (czas warszawski, w którym pracuje scanner) i nie
    odbyły się jeszcze wszystkie dzienne skany. Po wieczornym skanie dzień jest
    zamknięty, bo dane zmieniają się wyłącznie podczas skanu.
    """
    if not series:
        return None
    last = datetime.fromtimestamp(series[-1][0] / 1000).date()
    if last != datetime.now(TZ).date():
        return None
    entry = index_history.load(base_dir)['days'].get(last.isoformat()) or {}
    return last if entry.get('scans', 0) < SCANS_PER_DAY else None


def build_outflow(offers, series=None, provisional=None):
    """Dzienny odpływ ofert (ile zniknęło z listingów) + średnia krocząca 7 dni.

    Zniknięcie bierzemy z `deactivation_dates` (zapisywane od 2026-09-03) i ze
    starego `deactivated_at`, a gdy oferta nie ma żadnego z nich, a jest
    nieaktywna — z `last_seen`. Historia jest ZANIŻONA: stare pole trzyma tylko
    OSTATNIE zniknięcie, więc oferta, która umarła i wróciła, nie zostawiła
    śladu po pierwszej śmierci. Widać to w bilansie: napływ − odpływ nie schodzi
    się z przyrostem Indeksu, a różnica to mniej więcej liczba niezapisanych
    reaktywacji. Szereg domyka się sam w miarę kolejnych skanów.
    """
    days, _ = _axis(offers, series)
    if not days:
        return None
    start = days[0]

    dep = {}
    for o in offers:
        gone, _, _ = life_events(o)
        if not gone and not o.get('active') and o.get('last_seen'):
            try:
                gone = [_d(o['last_seen'])]
            except (ValueError, TypeError):
                gone = []
        for d in gone:
            if d >= start:
                dep[d] = dep.get(d, 0) + 1

    artifacts = {d for d, v in dep.items() if v > OUTFLOW_ARTIFACT_THRESHOLD}
    return _flow_metric(dep, days, exclude=artifacts, provisional=provisional)


def build_inflow(offers, series=None, provisional=None):
    """Dzienny NAPŁYW ofert — trzy powiązane metryki (każda jak odpływ):

    - `new`       : nowe oferty (`first_seen` = ten dzień), BEZ reaktywacji.
                    Czysty przyrost świeżych ogłoszeń — ta seria jest rzetelna
                    na całej długości (pierwsze pojawienie się zapisujemy od
                    początku istnienia bazy).
    - `react`     : same reaktywacje — oferty, które wróciły na rynek po
                    wcześniejszym zniknięciu. Zaniżone wstecz jak odpływ.
    - `new_react` : suma powyższych = wszystkie „pojawienia się" danego dnia.
    """
    days, _ = _axis(offers, series)
    if not days:
        return None
    start = days[0]

    new, react = {}, {}
    for o in offers:
        fs = o.get('first_seen')
        if fs:
            try:
                d = _d(fs)
                if d >= start:
                    new[d] = new.get(d, 0) + 1
            except (ValueError, TypeError):
                pass
        for d in life_events(o)[1]:
            if d >= start:
                react[d] = react.get(d, 0) + 1

    combined = {d: new.get(d, 0) + react.get(d, 0) for d in set(new) | set(react)}

    # Dni-artefakty (patrz REACT_ARTIFACT_THRESHOLD) wycinamy z serii reaktywacji
    # ORAZ z napływu całkowitego — składnik reaktywacji jest wtedy nierzetelny.
    # Nowe oferty zostają nietknięte: ta seria nie ma jak się zepsuć hurtem.
    unreliable = {d for d, v in react.items() if v > REACT_ARTIFACT_THRESHOLD}

    return {
        'new': _flow_metric(new, days, provisional=provisional),
        'react': _flow_metric(react, days, exclude=unreliable, provisional=provisional),
        'new_react': _flow_metric(combined, days, exclude=unreliable,
                                  provisional=provisional),
    }


def build_bands(offers, series=None):
    """Rozbicie dziennej liczby AKTYWNYCH ofert na dwa pasma (suma = Indeks):

    - `new`   : oferty świeże — do dnia D nie miały ani jednej reaktywacji,
    - `react` : „recykling" — oferty, które do dnia D już kiedyś wróciły
                z martwych (najwcześniejsza data reaktywacji <= D).

    Metoda: UDZIAŁ pasm liczymy z rekonstrukcji przedziałów życia
    (`build_spans`), a potem nakładamy go na MIERZONY Indeks, żeby suma pasm
    dalej równała się linii Indeksu. Same liczby z rekonstrukcji nie mogą tu
    wejść — zawyżają przeszłość i stos wystawałby ponad linię.

    Czego ten podział nie widzi: oferta, która w dniu D była martwa i wróciła
    później, jest w rekonstrukcji liczona jako żywa i trafia do pasma „świeże"
    (jej pierwsza reaktywacja jest PO D). Recykling jest więc ZANIŻONY; domknie
    się sam, gdy przybędzie dat w `deactivation_dates`.
    """
    spans, _ = build_spans(offers)
    days, _ = _axis(offers, series)
    if not spans or not days:
        return {'new': [], 'react': []}

    first_reactivation = []
    for offer, intervals in spans:
        dates = life_events(offer)[1]
        first_reactivation.append((intervals, dates[0] if dates else None))

    measured = {ms: value for ms, value in (series or [])}

    new_series, react_series = [], []
    for day in days:
        ms = _day_ms(day)
        total = recycled = 0
        for intervals, first in first_reactivation:
            if _alive(intervals, day):
                total += 1
                if first is not None and first <= day:
                    recycled += 1
        index_value = measured.get(ms, total if not measured else None)
        if index_value is None:
            new_series.append([ms, None])
            react_series.append([ms, None])
            continue
        scaled = round(index_value * recycled / total) if total else 0
        new_series.append([ms, index_value - scaled])
        react_series.append([ms, scaled])
    return {'new': new_series, 'react': react_series}


def load_scan_days(base_dir=None) -> set:
    """Dni z ZAKOŃCZONYM skanem wg data/scan_history.json.

    Historia trzyma ostatnie 200 skanów (≈100 dni przy 2 skanach dziennie),
    więc starsze dni dobierają index_history i `_scanned_days`.
    Brak/uszkodzony plik = pusty zbiór.
    """
    return set(daily_source_counts(base_dir))


# Pole w `scan_history.json` z liczbą ofert zebranych z danego źródła.
# Agencje (ANMA, Pasjonaci, Alternatywne, IdsHome) mają jeden wspólny licznik.
SOURCE_SCAN_FIELDS = {
    'olx': 'scraped_olx',
    'otodom': 'scraped_otodom',
    'adresowo': 'scraped_adresowo',
}
AGENCY_SCAN_FIELD = 'scraped_agencies'


def daily_source_counts(base_dir=None) -> dict:
    """{dzień: {źródło: NAJWYŻSZA liczba zebranych ofert tego dnia}}.

    Ta sama konwencja co Indeks (maksimum z odczytów dnia): skan częściowy nie
    może zaniżyć obrazu dnia, w którym drugi skan poszedł normalnie. Służy do
    (a) mianownika udziału wyróżnień, (b) wykrywania dni ze ślepym źródłem.
    """
    path = (Path(paths.SCAN_HISTORY_JSON) if base_dir is None
            else Path(base_dir) / 'data' / 'scan_history.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            history = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    scans = history.get('scans', []) if isinstance(history, dict) else (history or [])

    out = {}
    for scan in scans or []:
        if scan.get('status') not in (None, 'completed', 'warning'):
            continue
        ts = scan.get('timestamp')
        if not ts:
            continue
        try:
            day = _d(ts)
        except (ValueError, TypeError):
            continue
        bucket = out.setdefault(day, {})
        for source, field in SOURCE_SCAN_FIELDS.items():
            value = scan.get(field)
            if value is not None:
                bucket[source] = max(bucket.get(source, 0), value)
        value = scan.get(AGENCY_SCAN_FIELD)
        if value is not None:
            bucket['agencies'] = max(bucket.get('agencies', 0), value)
    return out


def blind_source_days(base_dir=None) -> dict:
    """{dzień: [źródła, które NIE ODPOWIEDZIAŁY ani razu tego dnia]}.

    Zero zebranych ofert we WSZYSTKICH skanach dnia to blokada portalu, nie
    pusty rynek. Ochrona z `main._mark_inactive` nie pozwala wtedy zdezaktywować
    ofert tego źródła (Indeks trzyma ostatni znany stan), ale nikt nie broni
    wykresom NAPŁYWU: dzień z zablokowanym OLX rysował „0 nowych ofert" jak
    fakt rynkowy. W tej bazie OLX milczał 12 dni z rzędu (12–23.08.2026).

    Źródło, którego dany skan w ogóle nie raportował (starsze wpisy nie mają
    `scraped_adresowo`), jest NIEZNANE, nie ślepe — i tu nie trafia.
    """
    out = {}
    for day, counts in daily_source_counts(base_dir).items():
        blind = sorted(source for source, value in counts.items() if value == 0)
        if blind:
            out[day] = blind
    return out


def blind_ranges(base_dir=None) -> list:
    """Ciągłe odcinki ślepoty źródła — [{source, from, to, days}] w ms.

    Front zakreskowuje je na wykresach przepływów: bez tego dołek w napływie
    czyta się jak ochłodzenie rynku, a to była blokada portalu.
    """
    by_source = {}
    for day, sources in blind_source_days(base_dir).items():
        for source in sources:
            by_source.setdefault(source, []).append(day)

    ranges = []
    for source, days in by_source.items():
        days.sort()
        start = prev = days[0]
        for day in days[1:] + [None]:
            if day is not None and (day - prev).days == 1:
                prev = day
                continue
            ranges.append({
                'source': source,
                'from': _day_ms(start) - DAY_MS // 2,
                'to': _day_ms(prev) + DAY_MS // 2,
                'days': (prev - start).days + 1,
            })
            if day is not None:
                start = prev = day
    return sorted(ranges, key=lambda r: r['from'])


def olx_active_by_day(base_dir=None) -> dict:
    """{dzień: ile ofert OLX było aktywnych} — mianownik udziału wyróżnień.

    Wyróżnienie na listingu potrafi mieć TYLKO oferta OLX, więc dzielenie ich
    liczby przez cały Indeks (6 źródeł, z czego OLX to ~13%) zaniżałoby udział
    kilkukrotnie — i przeczyłoby liczbie, którą na tej samej stronie podaje
    `map_generator.build_promoted`.

    Źródła, w kolejności zaufania:
      1. `active_olx` z index_history (mierzone, zapisywane od 2026-09-04),
      2. `scraped_olx` z scan_history — ile ofert widział listing OLX tego dnia
         (dobra przybliżona miara historyczna; scan_history trzyma 200 skanów).
    """
    measured = index_history.daily_field('active_olx', base_dir=base_dir)
    out = {day: counts['olx']
           for day, counts in daily_source_counts(base_dir).items()
           if counts.get('olx')}
    out.update(measured)  # pomiar bije przybliżenie
    return out


def _scanned_days(offers):
    """Dni, w których skan REALNIE zebrał dane (jakakolwiek oferta ma tam
    `last_seen`). Uzupełnienie dla dni starszych niż okno scan_history.json."""
    days = set()
    for o in offers:
        if not o.get('last_seen'):
            continue
        try:
            days.add(_d(o['last_seen']))
        except (ValueError, TypeError):
            continue
    return days


def build_promoted(offers, series, scan_days=None, base_dir=None, provisional=None):
    """Dzienna liczba ofert PROMOWANYCH (płatne wyróżnienie na listingu OLX).

    Źródło: `promoted_dates` w offers.json — dni, w których scraper zobaczył
    ofertę jako wyróżnioną (main._track_promoted, max 1 wpis/dzień). To metryka
    STANU (ile ofert jest wyróżnianych danego dnia), nie przepływu, więc `total`
    (suma po dniach) nie ma tu sensu i nie jest pokazywana.

    Historia zaczyna się w dniu wdrożenia detekcji — wyróżnienia NIE DA SIĘ
    odtworzyć wstecz (to stan chwilowy na listingu, nie ślad w ofercie).

    Druga seria to udział wyróżnionych wśród AKTYWNYCH OFERT OLX danego dnia
    (patrz `olx_active_by_day`) — nie wśród całego Indeksu, bo wyróżnić może się
    tylko oferta OLX. Dzień bez znanego mianownika zostaje luką.
    """
    counts = {}
    for o in offers:
        for pd in (o.get('promoted_dates') or []):
            try:
                d = date.fromisoformat(str(pd)[:10])
            except (ValueError, TypeError):
                continue
            counts[d] = counts.get(d, 0) + 1

    if not counts:
        return None

    _, today = build_spans(offers)
    start = min(counts)
    days = _daily_range(start, max(today, max(counts)))

    # Dzień liczy się jako zeskanowany, gdy: zapisał się w index_history
    # (najpewniejsze źródło — wpis powstaje przy każdym skanie), jest w oknie
    # scan_history, jakaś oferta ma tam last_seen, albo widzieliśmy tego dnia
    # wyróżnioną ofertę. Reszta = luka, żeby awaria Actions nie wyglądała jak
    # zerowe wyróżnianie.
    recorded = {day for day, value in index_history.daily_series(base_dir=base_dir) if value}
    scanned = recorded | set(scan_days or set()) | _scanned_days(offers) | set(counts)
    # Dzień ze ŚLEPYM OLX też jest luką, choć skan się odbył i inne źródła
    # odpowiedziały: wyróżnienie potrafi zgłosić wyłącznie listing OLX, więc
    # zero z takiego dnia byłoby zmyślone (patrz blind_source_days).
    blind_olx = {day for day, sources in blind_source_days(base_dir).items()
                 if 'olx' in sources}
    missing = {d for d in days if d not in scanned or d in blind_olx}

    metric = _flow_metric(counts, days, exclude=missing, provisional=provisional)

    olx_active = olx_active_by_day(base_dir)
    share = []
    for d in days:
        active = olx_active.get(d)
        if d in missing or not active:
            share.append([_day_ms(d), None])
        else:
            share.append([_day_ms(d), round(100 * counts.get(d, 0) / active, 1)])

    last_day = next((d for d in reversed(days) if d not in missing), None)
    current = counts.get(last_day, 0) if last_day else None
    current_share = None
    if last_day:
        active = olx_active.get(last_day)
        if active:
            current_share = round(100 * counts.get(last_day, 0) / active, 1)

    metric.pop('total', None)
    metric.update({
        'share': share,
        'current': current,
        'current_share': current_share,
        'start': start.isoformat(),
        'start_label': start.strftime('%d.%m.%Y'),
        'days': len(days),
    })
    return metric


def count_dedup_active(offers) -> int:
    """Ile aktywnych ofert widać na mapie — bez tych, które wskazują duplikatem
    na inną AKTYWNĄ ofertę (ta sama działka wystawiona w kilku źródłach).

    Indeks rysujemy z liczby SUROWEJ, bo tylko ją da się odtworzyć wstecz
    (`duplicate_of` to stan bieżący, historia powiązań nie jest zapisywana).
    Ta liczba służy podpisowi pod wykresem — żeby różnica wobec mapy nie
    wyglądała na błąd.
    """
    active_ids = {o['id'] for o in offers if o.get('active')}
    return sum(1 for o in offers
               if o.get('active')
               and not (o.get('duplicate_of') and o['duplicate_of'] in active_ids))


def _value_at_or_before(series, target_ms):
    """Ostatni ZMIERZONY odczyt nie później niż target_ms. Dni bez skanu (None)
    przeskakujemy — inaczej awaria Actions kasowałaby porównanie."""
    best = None
    for ms, val in series:
        if ms > target_ms:
            break
        if val is not None:
            best = val
    return best


def compute_deltas(series):
    """Zmiany 1D/1M/6M/1Y vs dziś. None, gdy nie mamy tak starej historii."""
    measured = [(ms, val) for ms, val in (series or []) if val is not None]
    if not measured:
        return {}
    now_ms, current = measured[-1]
    first_ms = measured[0][0]
    out = {}
    for label, days in (('1D', 1), ('1M', 30), ('6M', 182), ('1Y', 365)):
        target = now_ms - days * DAY_MS
        if target < first_ms:
            out[label] = None  # brak tak starych danych → front pokaże „—"
            continue
        past = _value_at_or_before(measured, target)
        out[label] = (current - past) if past is not None else None
    return out


def generate(base_dir=None) -> bool:
    """data/offers.json + data/index_history.json → docs/trend_data.json."""
    offers_path = (Path(paths.OFFERS_JSON) if base_dir is None
                   else Path(base_dir) / 'data' / 'offers.json')
    out_path = (Path(paths.DOCS_TREND_JSON) if base_dir is None
                else Path(base_dir) / 'docs' / 'trend_data.json')

    with open(offers_path, 'r', encoding='utf-8') as f:
        offers = json.load(f).get('offers', [])

    series = build_series(offers, base_dir)
    measured = [(ms, val) for ms, val in series if val is not None]
    if not measured:
        print("⚠️ Brak danych do Indeksu — pomijam trend_data.json")
        return False
    index_source = ('measured' if index_history.daily_series(base_dir=base_dir)
                    else 'reconstructed')

    # dziś może jeszcze urosnąć — nie liczymy go do średnich i rekordów
    provisional = provisional_day(series, base_dir)

    values = [val for _, val in measured]
    current = values[-1]
    mx, mn = max(values), min(values)
    # MAX: pierwsze wystąpienie, MIN: ostatnie
    max_ts = next(ms for ms, val in measured if val == mx)
    min_ts = next(ms for ms, val in reversed(measured) if val == mn)
    last_day = datetime.fromtimestamp(measured[-1][0] / 1000).date()

    data = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'title': TITLE,
        'metric': 'active_daily',
        'unit': UNIT,
        'reliable_start': RELIABLE_START.isoformat(),
        # 'measured' = zapisany stan bazy (data/index_history.json),
        # 'reconstructed' = awaryjna rekonstrukcja z offers.json (zawyża przeszłość)
        'index_source': index_source,
        'current': current,
        # tyle pinezek jest dziś na mapie (Indeks liczy oferty przed deduplikacją)
        'current_dedup': count_dedup_active(offers),
        'max': mx,
        'min': mn,
        'max_ts': max_ts,
        'min_ts': min_ts,
        'last_label': last_day.strftime('%d.%m.%Y'),
        'points': len(series),
        'measured_points': len(measured),
        # dzień jeszcze nietrwały: front oznacza go na wykresach, a średnie
        # i rekordy już go nie widzą
        'provisional_ms': _day_ms(provisional) if provisional else None,
        'deltas': compute_deltas(series),
        'series': series,
        'outflow': build_outflow(offers, series, provisional),
        'inflow': build_inflow(offers, series, provisional),
        'bands': build_bands(offers, series),
        'promoted': build_promoted(offers, series, load_scan_days(base_dir),
                                   base_dir, provisional),
        # odcinki, w których źródło nie odpowiadało — front je zakreskowuje
        'blind_ranges': blind_ranges(base_dir),
        # ile par „zniknęła i zaraz wróciła" odsialiśmy jako zacięcie scrapera
        'flapping': {
            'pairs': sum(life_events(o)[2] for o in offers),
            'max_days': FLAP_MAX_DAYS,
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    of = data['outflow'] or {}
    inf = (data['inflow'] or {}).get('new') or {}
    gaps = len(series) - len(measured)
    print(f"📉 Wygenerowano {out_path}: {len(series)} dni od {RELIABLE_START} "
          f"({index_source}, luk bez skanu: {gaps}), "
          f"teraz={current}, max={mx}, min={mn}")
    print(f"   ↘️ odpływ: łącznie={of.get('total')}, śr={of.get('rate')}/dzień, "
          f"rekord={of.get('max_day')} ({of.get('max_label')})")
    print(f"   ↗️ nowe: łącznie={inf.get('total')}, śr={inf.get('rate')}/dzień, "
          f"rekord={inf.get('max_day')} ({inf.get('max_label')})")
    print(f"   🧹 odsiane mrugnięcia pipeline'u (powrót ≤{FLAP_MAX_DAYS} dni): "
          f"{data['flapping']['pairs']} par")
    for r in data['blind_ranges']:
        first = datetime.fromtimestamp(r['from'] / 1000).date()
        print(f"   🚫 {r['source']}: bez odpowiedzi przez {r['days']} dni "
              f"(od {first.strftime('%d.%m')})")
    pr = data['promoted']
    if pr:
        print(f"   ⭐ wyróżnione: teraz={pr.get('current')} "
              f"({pr.get('current_share')}% rynku), śr={pr.get('rate')}/dzień, "
              f"historia od {pr.get('start_label')}")
    else:
        print("   ⭐ wyróżnione: brak danych (metryka zbiera się od wdrożenia)")
    return True


if __name__ == '__main__':
    generate()
