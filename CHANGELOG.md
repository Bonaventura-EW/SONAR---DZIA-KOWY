# CHANGELOG

## [Niewydane]

### Dodane
- **Metryka płatnie wyróżnionych ofert OLX** (propagacja z SONAR-POKOJOWY,
  manifest `2026-08-26-promoted-listings-metric`). Scraper czyta wyróżnienie
  z pola `searchReason` w `__PRERENDERED_STATE__` (`'promoted'`/`'organic'`, z
  fallbackiem na `isPromoted`) — u brata sygnał szło z href-a karty HTML, u nas
  jest wprost w JSON, więc nie trzeba go ratować przed `url.split('?')[0]`.
  `main.py` zapisuje stan per oferta (`promoted`) i historię dni
  (`promoted_dates`, max 1 wpis/dzień), a `map_generator` (`build_promoted`)
  liczy z tego dzienny szereg i bieżący udział wyróżnionych w aktywnych ofertach
  OLX. Nowy wykres w `docs/analytics.html` (dni bez skanu = luka, nie zero).
- **Pasek „ta oferta vs mediana grupy" w dymku na mapie** (`docs/assets/script.js`).
  Ten sam obraz i te same liczby co karta w rankingu Okazji: procent względem
  mediany porównywalnych, z czym dokładnie porównaliśmy (grupa + liczba ofert),
  pasek na skali 0–1,5× mediany ze znacznikiem mediany oraz ostrzeżenie
  o ofercie nietypowej. W odróżnieniu od rankingu (z definicji tylko okazje)
  mapa pokazuje też oferty **droższe** od porównywalnych — czerwony pasek
  i „X% powyżej ceny rynkowej", a przy skrajnościach czytelniejsze
  „32,5× mediany porównywalnych" zamiast „−3152%".
- Metodyka odniesienia rynkowego wyjechała do wspólnego modułu
  **`docs/assets/market_ref.js`** (`MarketRef.build(offers) → {ref, evaluate}`),
  z którego korzystają teraz i `okazje.html`, i mapa. Gdyby dymek liczył medianę
  własnym kodem, ta sama działka mogłaby z czasem pokazywać na mapie inny
  procent niż w rankingu. Ranking po refaktorze daje identyczne wyniki.

### Naprawione
- **Pinezka z liczbą nie gubi już szczegółów ofert** (`docs/assets/script.js`,
  `style.css`). Po zgrupowaniu ofert o identycznych współrzędnych w „stosy"
  dymek takiego punktu pokazywał wyłącznie płaską listę (tytuł, cena, metraż) —
  zdjęcie, trend ceny, pasek „ta oferta vs mediana grupy", opis i data w bazie
  były z mapy nieosiągalne, choć pojedyncze pinezki dawały je od jednego
  kliknięcia. Dotyczyło to 137 punktów z 733 ofert (największy stos: 23).
  Dymek stosu ma teraz dwa widoki: listę i **pełną kartę oferty** — dokładnie tę
  samą, którą renderuje pojedyncza pinezka (`popupHtml`). Klik w wiersz otwiera
  kartę, a nagłówek karty wraca do listy (z podświetleniem oglądanej pozycji)
  i przeskakuje strzałkami ‹ › między ofertami spod punktu. Wiersz listy ma też
  „↗" prosto do ogłoszenia, więc dawne jedno kliknięcie na portal zostaje.
  Widok trzymamy na markerze, a treść dymka jest funkcją — przełączenie to samo
  `popup.update()`, bez zamykania dymka i bez przerysowania mapy. Wejście
  z linku `#offer=<id>` otwiera od razu kartę wskazanej oferty, nie listę.
  Przy okazji odmiana liczebnika: „2 **oferty** w tym punkcie" zamiast „2 ofert".
- **Koniec porównywania działek między typami.** Grupa odniesienia mogła zejść
  do poziomu „przedział powierzchni, wszystkie typy", co dotykało 20 ofert
  (18 rekreacyjnych + 2 siedliskowe) i produkowało fikcje w rodzaju „85% poniżej
  ceny rynkowej" dla działki rekreacyjnej porównanej z medianą zdominowaną przez
  budowlane. W rankingu było to ukryte (te oferty i tak łapały flagę ROD),
  ale w dymku na mapie wychodziło jako zielony badge. Dwie zmiany:
  (a) próg poziomu „cały typ działki" obniżony z 8 na 5 ofert — rekreacyjne mają
  tylko 6 „zdrowych" ogłoszeń (12 z 18 to ROD-y odsiane z bazy median), więc przy
  progu 8 wpadały właśnie w mieszaną grupę; 5 to ten sam próg co dla węższych
  grup 1–2, więc szersza grupa nie ma powodu wymagać więcej;
  (b) grupy **bez typu w kluczu** są teraz oznaczone `weak` — wypadają z rankingu,
  a na mapie dostają szary znacznik „orientacyjnie — brak grupy porównawczej"
  zamiast procentu. Zostały tak 2 oferty (siedliskowe).
  Efekt uboczny, zamierzony: licznik ofert nietypowych spadł z 58 na 46 — ROD-y
  porównywane teraz do własnej mediany (~79 zł/m²) przestały fałszywie łapać
  regułę „cena rażąco poniżej porównywalnych". Flagę ROD zachowują wszystkie 52.

### Dodane
- Podstrona **💎 Okazje** (`docs/okazje.html`) — ranking działek o najlepszym
  stosunku ceny do metrażu. Dla każdej aktywnej oferty liczymy medianę zł/m²
  w **najwęższej grupie porównywalnych**, w której jest dość danych, i pokazujemy,
  o ile procent oferta jest pod tą medianą (plus szacowaną oszczędność
  = różnica zł/m² × powierzchnia). Wzór z `okazje.html` w SONAR-MIESZKANIOWY,
  ale grupy odniesienia przeliczone na realia gruntów:
  **typ działki i przedział powierzchni są częścią każdego klucza**
  (u brata rolę tę pełnią miasto, liczba pokoi i rynek pierwotny/wtórny).
  Bez typu każda działka rolna czy rekreacyjna wychodziłaby jako okazja —
  budowlana kosztuje w Lublinie ~445 zł/m², rekreacyjna ~89 zł/m².
  Bez przedziału powierzchni to samo robiłby rozmiar: budowlana poniżej 600 m²
  ma medianę ~775 zł/m², ta sama budowlana 1200–2500 m² — ~355 zł/m².
  Dzielnica jest tylko doprecyzowaniem, bo zna ją mniej niż połowa ogłoszeń.
  Hierarchia: typ+dzielnica+powierzchnia (min. 5) → typ+dzielnica (min. 5) →
  typ+powierzchnia (min. 8) → typ (min. 8) → powierzchnia (min. 8) → cały obszar.
  Karty/tabela, KPI, filtry (źródło z agencjami, typ, dzielnica, cena, powierzchnia,
  nowe, właściciel, po obniżce, z GPS), tryb „najniższa cena/m²", linki
  📍 Mapa (`index.html#offer=`) i 💲↓ do historii ceny (`oferty.html#offer=`).
- **Oferty nietypowe** odsiewane z rankingu (domyślnie ukryte, checkbox przywraca):
  ROD / ogródki działkowe (kupujesz prawo do działki i altanę, nie własność gruntu),
  udziały, licytacje i syndyk, użytkowanie wieczyste, dzierżawa, zamiana,
  ogłoszenia niebędące działką oraz ceny poniżej 35% mediany **własnej grupy**.
  ROD-a szukamy w tytule *i opisie* — to najliczniejsze zniekształcenie w tych
  danych (50 z 384 aktywnych ofert, mediana ~74 zł/m²), a fraza jest jednoznaczna;
  reszta reguł patrzy tylko na tytuł, żeby nie łapać „udziału w kosztach mediów".
  Próg odstający liczymy **względem grupy, nie mediany całego miasta** — globalna
  mediana miesza budowlane z rekreacyjnymi, więc oflagowałaby hurtem cały tańszy typ.
- Link do historii ceny z podstrony Okazje: `docs/oferty.html` obsługuje teraz
  `#offer=<id>` i otwiera wykres „cena w czasie" wybranej oferty.

### Naprawione
- **OLX znów się skanuje** (`olx_scraper.py`). Od 2026-08-11 OLX (CloudFront/WAF)
  odrzucał każdy request biblioteki `requests` kodem **403** — niezależnie od
  nagłówków (sprawdzone: pełny zestaw Chrome'owych `sec-ch-ua`/`Sec-Fetch-*`
  też dostaje 403). Blokada idzie po **fingerprincie TLS (JA3)**: handshake
  pythonowego OpenSSL nie wygląda jak przeglądarka. Warstwa HTTP scrapera OLX
  przeszła na **`curl_cffi`** z `impersonate=` (odtwarza handshake prawdziwego
  Chrome'a/Safari); ten sam URL wraca z kodem **200** i pełnym
  `__PRERENDERED_STATE__`. Profile próbowane po kolei
  (`chrome131 → chrome124 → chrome110 → safari17_0 → edge101`), a gdy żaden nie
  przejdzie — fallback na gołe `requests` (scraper działa też bez `curl_cffi`
  w środowisku). Zweryfikowane end-to-end: 64 oferty z Lublina po 13 dniach ciszy.

### Dodane
- **Alarm o awarii źródła w API** (`src/source_health.py`). Skan z martwym
  źródłem kończył się statusem `completed` (pozostałe portale działały), a
  ochrona przed masową dezaktywacją słusznie pomijała dezaktywację ofert —
  przez co `api/health.json` przez **26 kolejnych skanów** raportował
  `"status": "ok"` przy zerowym OLX-ie. Teraz `health.json` i `status.json`
  niosą listę `alerts` (`source_down` / `source_degraded`, `severity`
  `critical`/`warning`), a `health.status` schodzi na **`degraded`**, gdy
  źródło padło mimo udanego skanu. `sources` w `health.json` pokazuje stan
  każdego portalu (norma vs ostatni skan, liczba pustych skanów z rzędu, data
  ostatnich ofert). Norma to mediana 10 ostatnich **niezerowych** odczytów
  szukanych w głąb 40 skanów — liczona z okna „10 ostatnich skanów" znikałaby
  pod stertą zer po długiej awarii i przez kolejne 3 skany po naprawie źródła
  ponowna blokada nie odpalałaby alarmu. Alarmy trafiają też do
  `docs/monitoring_data.json` → czerwony pasek na dashboardzie monitoringu
  i annotacje runa w GitHub Actions (`::error` / `::warning`).

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
