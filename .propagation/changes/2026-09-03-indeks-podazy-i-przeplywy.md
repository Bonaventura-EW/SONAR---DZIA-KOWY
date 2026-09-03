---
id: 2026-09-03-indeks-podazy-i-przeplywy
repo: Bonaventura-EW/SONAR---DZIA-KOWY
family: sonary
date: 2026-09-03
category: feature
what: Sekcja „Indeks podaży i ruch na rynku" na stronie analityki — sześć wykresów szeregów czasowych (stan rynku, odpływ, napływ, reaktywacje, wyróżnienia) liczonych z mierzonego dziennego stanu bazy.
why: Analityka pokazywała wyłącznie PRZEKRÓJ „tu i teraz" (histogram cen, scatter, typy działek) plus 30 dni nowych ofert. Nie dało się odpowiedzieć na pytanie, czy podaż rośnie czy maleje, ile ofert znika dziennie i ile z „nowych" to recykling starych ogłoszeń.
how: Port trend.html z SONAR-POKOJOWY na dane tego repo. Nowy src/index_history.py zapisuje po każdym skanie dzienny stan bazy do data/index_history.json (wartość dnia = maksimum z odczytów, dzień bez skanu = luka; historia odtworzona z scan_history.json, który przycinamy do 200 skanów). src/trend_generator.py buduje z tego + offers.json plik docs/trend_data.json (seria Indeksu, pasma świeże/recykling skalowane do mierzonego Indeksu, odpływ/napływ/reaktywacje ze średnią kroczącą 7 dni, wyróżnienia OLX z udziałem w rynku). Front to docs/assets/trend.js (ApexCharts 3.49.1, jasny motyw). main.py dostał `_record_event` — listy dat deaktywacji/reaktywacji zamiast samych pól „ostatnie zdarzenie", bo bez nich szeregi przepływów są wstecz zaniżone.
surface: src/index_history.py, src/trend_generator.py, src/main.py, src/paths.py, docs/analytics.html, docs/assets/trend.js, docs/assets/style.css, .github/workflows/scanner.yml, tests/test_trend_generator.py
generality: family
propagate: yes
commit: 8fcbdab13adb839a53c204e65e60a1e21e5f9116
---

# Kontekst dla brata-ewaluatora

**Skąd to się wzięło:** użytkownik wskazał `trend.html` z SONAR-POKOJOWY i poprosił
o te same wykresy u nas. Struktura danych (`trend_data.json`) i logika generatora są
w 90% przeniesione z brata — jeśli masz u siebie `trend_generator.py`, różnice do
przejrzenia są poniżej.

**Czym się różnimy od brata:**

1. **Daty zdarzeń.** Brat trzyma `deactivation_dates` / `reactivation_dates` (listy)
   i chowa starsze wersje w `versions[]`. My mieliśmy tylko `deactivated_at` /
   `reactivated_at` — POJEDYNCZY znacznik ostatniego zdarzenia. Stąd
   `collect_dates(offer, list_field, scalar_field)`, które scala oba źródła, i
   `main._record_event`, które od teraz dopisuje dni do list. Historia sprzed
   wdrożenia zostaje zaniżona i tak jest opisana pod wykresami — nie udajemy,
   że szereg jest kompletny.

2. **Brak sztucznych granic wiarygodności.** U brata `REACT_RELIABLE_START`
   (01.07.2026) wycina odcinek, w którym backfill wstawił po jednej dacie na ofertę.
   Naszych danych nikt nie backfillował, więc nie ma czego wycinać — zostały tylko
   progi artefaktów (60 zdarzeń/dzień ≈ 12% rynku), które dziś nic nie tną.

3. **Deduplikacja źródeł.** Zbieramy z 6 źródeł (OLX, Otodom, Adresowo, 3 agencje),
   a ~20% aktywnych ofert to ta sama działka wystawiona w kilku miejscach
   (dziś 473 w bazie → 380 na mapie). Indeks rysujemy z liczby SUROWEJ, bo
   `duplicate_of` to stan bieżący i historii powiązań nikt nie zapisuje —
   liczby po deduplikacji nie da się odtworzyć wstecz. Zapisujemy ją od teraz
   (`active_dedup` w index_history), a różnica jest wprost wyjaśniona pod wykresem.

4. **Jasny motyw.** Brat ma ciemne tło i białe napisy na kolorowych plakietkach.
   ApexCharts 3.49 wystawia prostokąt tła adnotacji poza obszar wykresu
   (`x=-137`), więc u brata napis „MAX: 816" jest czytelny tylko dlatego, że biel
   działa na ciemnym tle. U nas trzeba było dać KOLOROWY tekst bez tła — inaczej
   etykieta MAX (nad wykresem, na białym) była niewidzialna. Druga różnica:
   w trybie pasm oś Y musi startować od zera (stos rysuje się od zera), inaczej
   dolne pasmo chowa się pod przyciętą dolną krawędzią osi.
