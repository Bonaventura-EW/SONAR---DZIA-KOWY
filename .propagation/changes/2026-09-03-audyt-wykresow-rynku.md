---
id: 2026-09-03-audyt-wykresow-rynku
repo: Bonaventura-EW/SONAR---DZIA-KOWY
family: sonary
date: 2026-09-03
category: bugfix
what: Wykresy przepływów (odpływ / napływ / reaktywacje / wyróżnienia) przestały pokazywać zacięcia własnego pipeline'u jako fakty rynkowe — filtr „mrugnięć", luki dla ślepych źródeł, dni nadrabiania zaległości i dzień w toku poza statystykami.
why: Audyt logiki wykazał, że KAŻDY rekord widoczny na stronie był zdarzeniem technicznym: rekord odpływu i rekord reaktywacji to dwie strony jednego częściowego scrape'u, rekord napływu to dzień powrotu OLX po 12 dniach blokady, a udział wyróżnień był liczony na mianowniku 8× za dużym.
how: (1) life_events paruje deaktywacje z powrotami i wyrzuca pary domknięte w ≤3 dni z obu serii oraz z rekonstrukcji życia oferty; (2) blind_source_days/blind_ranges czytają liczby per źródło z scan_history — źródło z zerem we wszystkich skanach dnia daje lukę w metryce, której dotyczy, i zakreskowany pas na pozostałych wykresach; (3) recovery_days wyłącza ze statystyk dzień powrotu źródła, w którym baza dostaje zaległości z całej blokady; (4) provisional_day wyłącza dzień jeszcze nieskończony (liczba odczytów w index_history < skanów na dobę); (2)-(4) korzystają ze wspólnego mechanizmu `_flow_metric(uncounted=...)`: słupek zostaje, statystyki go nie widzą. Dodatkowo progi artefaktów względne do Indeksu, _day_ms w UTC, tolerancja 3 dni w porównaniach 1D/1M.
surface: src/trend_generator.py, src/index_history.py, src/main.py, docs/analytics.html, docs/assets/trend.js, tests/test_trend_generator.py
generality: family
propagate: yes
commit: c1cea35057302bda0f3c071092b194887b92f7ed
---

# Kontekst dla brata-ewaluatora

**To jest poprawka do `trend.html` / `trend_generator.py`** — jeśli masz u siebie
tę sekcję, prawie na pewno masz też te dziury, bo logika jest wspólna.

**Diagnoza, którą warto powtórzyć u siebie** (zapytania na własnej bazie):

1. Ile par „deaktywacja → reaktywacja" domyka się w ≤3 dni? U nas 66% (42 z 64).
   Działka wycofana ze sprzedaży nie wraca po dwóch dniach — wraca oferta,
   której portal chwilowo nie pokazał albo którą częściowy scrape uznał za martwą.
2. Czy w `scan_history` są dni, w których jakieś źródło zwróciło 0 we WSZYSTKICH
   skanach? U nas OLX milczał 12 dni z rzędu, a wykres napływu rysował w tym
   oknie „ochłodzenie rynku".
3. Czy rekord napływu nie wypada przypadkiem w dniu POWROTU takiego źródła?
   U nas dokładnie tak było.

**Czego świadomie NIE zrobiliśmy:** ochrona z `main._mark_inactive` (próg 30%)
zostaje bez zmian — łapie katastrofy, a nie 10-procentowe niedobory, i tak ma
być; naprawiamy skutki po stronie wykresów, nie zaostrzamy progu, bo zaostrzony
blokowałby też prawdziwe dezaktywacje.

**Różnica architektoniczna wobec brata:** u nas 6 źródeł (2 portale + agregator
+ 3 agencje), więc „ślepe źródło" to codzienność, a mianownik metryk OLX-owych
musi być OLX-owy. W repo z jednym źródłem punkt (1) i (3) nadal obowiązują,
punkt (2) sprowadza się do „dzień bez danych", a mianownik nie jest problemem.
