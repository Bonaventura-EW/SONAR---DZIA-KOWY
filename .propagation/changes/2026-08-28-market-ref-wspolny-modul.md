---
id: 2026-08-28-market-ref-wspolny-modul
repo: Bonaventura-EW/SONAR---DZIA-KOWY
family: sonary
date: 2026-08-28
category: refactor
what: Metodyka odniesienia rynkowego (mediana grupy porównywalnych) w jednym module współdzielonym przez ranking okazji i dymek na mapie; przy okazji odcięcie porównań między nieporównywalnymi grupami.
why: Dwie kopie tego samego algorytmu na dwóch stronach rozjechałyby się z czasem i ta sama oferta pokazywałaby dwa różne procenty. Osobno: kaskada grup mogła zejść do poziomu mieszającego typy nieruchomości i produkować fikcyjne okazje.
how: Nowy `docs/assets/market_ref.js` eksportuje `MarketRef.build(offers, globalMedian) → {ref, evaluate}`; `evaluate(o)` zwraca komplet {ref, ratio, disc, save, odd, weak}. Obie strony ładują moduł przed swoim skryptem. Wspólny jest też CSS paska (przeniesiony do style.css). Poziomy kaskady bez klucza różnicującego dostają `weak: true` — wypadają z rankingu, a na mapie renderują się neutralnie zamiast jako procent.
surface: docs/assets/market_ref.js, docs/assets/script.js, docs/assets/style.css, docs/okazje.html, docs/index.html, CHANGELOG.md
generality: family
propagate: yes
commit: 25eb7ac
---

# Kontekst dla braci

Dwie rzeczy do wzięcia, niezależne od siebie.

## 1. Jedna metodyka, wiele widoków

Jeśli u siebie macie ranking okazji (manifest `2026-08-28-podstrona-okazje`)
i chcecie pokazać to samo porównanie gdzie indziej — w dymku na mapie, na liście
ofert, w karcie szczegółów — **nie kopiujcie algorytmu**. Wyciągnijcie go do
modułu i wołajcie `evaluate(offer)`. U nas kosztowało to jeden plik i refaktor
dwudziestu linii w `okazje.html`; sprawdziliśmy, że ranking po przenosinach daje
co do jednego te same liczby (KPI, licznik ofert, top rankingu).

Drobiazg, który się opłacił: moduł kończy się
`if (typeof module !== 'undefined') module.exports = MarketRef;`, więc ten sam
plik odpala się w node bez przeglądarki — cała weryfikacja metodyki na prawdziwym
`data.json` to `node -e "..."`, bez stawiania serwera i bez headless browsera.

## 2. Nie porównuj rzeczy nieporównywalnych — oznacz je

Ważniejsza lekcja, i to taka, którą **wykrył dopiero nowy widok**.

Kaskada grup odniesienia kończy się gdzieś awaryjnym poziomem („cały obszar").
U nas przedostatnim poziomem był „przedział powierzchni, wszystkie typy" —
czyli poziom BEZ wymiaru, który najmocniej różnicuje cenę. Dotykał 20 ofert
i dla działki rekreacyjnej (mediana ~79 zł/m²) porównywanej z grupą zdominowaną
przez budowlane (~577 zł/m²) dawał **„85% poniżej ceny rynkowej"**. W rankingu
było to niewidoczne, bo te oferty i tak łapały flagę nietypowości i domyślnie
były ukryte. Dopiero mapa, która nic nie ukrywa, pokazała zielony badge z bzdurą.

Wnioski przenośne:

- **Sprawdźcie, co robi ostatni poziom waszej kaskady.** Jeśli gubi wymiar
  z pierwszego poziomu (u brata mieszkaniowego byłoby to miasto), to nie jest
  „gorsze przybliżenie", tylko inna wielkość.
- Lepszy jest **brak liczby niż liczba nie do obrony**. Wprowadziliśmy flagę
  `weak` dla grup bez wymiaru różnicującego: taka oferta wypada z rankingu,
  a w dymku dostaje szare „orientacyjnie — brak grupy porównawczej" zamiast
  procentu. Zostały tak 2 oferty z 384 — koszt żaden.
- Zanim sięgniecie po flagę, sprawdźcie **progi próbki**. U nas realnym winowajcą
  był próg 8 na poziomie „cały typ": rekreacyjne mają 18 ogłoszeń, ale 12 to ROD-y
  odsiane z bazy median, więc zostawało 6 i poziom nie łapał. Obniżenie do 5
  (tyle samo, co dla węższych grup wyżej w kaskadzie) rozwiązało 18 z 20 przypadków.
  Szersza grupa nie ma powodu wymagać większej próbki niż węższa — jeśli macie
  u siebie rosnące progi w dół kaskady, prawdopodobnie jest to przypadek, nie decyzja.
- Uwaga na **sprzężenie z regułą odstających**: nasz próg „cena rażąco poniżej
  porównywalnych" liczy się względem mediany grupy, więc naprawa grup zmieniła
  też liczbę ofert nietypowych (58 → 46). To był fałszywy alarm, nie regresja:
  ROD w cenie ROD-ów przestał wyglądać na błąd cenowy. Jeśli macie podobne
  sprzężenie, przeliczcie oba liczniki po zmianie grup.
