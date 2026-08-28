---
id: 2026-08-28-podstrona-okazje
repo: Bonaventura-EW/SONAR---DZIA-KOWY
family: sonary
date: 2026-08-28
category: feature
what: Podstrona „Okazje" — ranking ofert o najlepszym zł/m² względem mediany najwęższej grupy porównywalnych, z regułą odsiewania ofert nietypowych.
why: Sama niska cena nic nie mówi — trzeba ją odnieść do porównywalnych ofert. Surowa lista posortowana po zł/m² wypycha na górę wyłącznie najtańszy segment rynku (u nas ROD-y i grunty rolne), więc jest bezużyteczna.
how: Frontend-only, czyta istniejący docs/data.json. Dla każdej aktywnej oferty liczona jest mediana zł/m² w najwęższej grupie porównywalnych, w której starcza próbki (kaskada 6 poziomów z progami 5/8 ofert); „% poniżej ceny rynkowej" = 1 − zł/m² oferty / mediana grupy, oszczędność = różnica × powierzchnia. Odniesienia liczone tylko na ofertach „zdrowych", żeby nietypowe nie zaniżały median. Karty + tabela, KPI, komplet filtrów, sekcja metodyki na stronie.
surface: docs/okazje.html, docs/oferty.html, docs/index.html, docs/analytics.html, docs/monitoring.html, docs/zmiany.html, docs/agencje.html, CHANGELOG.md
generality: family
propagate: maybe
commit: 6d210ec
---

# Kontekst dla braci

Strona jest **adaptacją `docs/okazje.html` z SONAR-MIESZKANIOWY**, nie nowym
pomysłem. Przenośny jest *szkielet* — kaskada grup odniesienia, „% poniżej ceny
rynkowej" ≠ obniżka sprzedającego, pasek pozycji względem mediany grupy, odsiew
ofert nietypowych, karty/tabela + sekcja „Jak liczymy okazję". Nieprzenośne są
**osie grupowania**: to jedyna rzecz, którą trzeba przemyśleć od zera w każdym repo.

## Co zmieniliśmy względem wersji mieszkaniowej i dlaczego

Brat grupuje po `miasto + dzielnica + liczba pokoi + rynek`. Przy gruntach żaden
z tych wymiarów (poza dzielnicą) nie istnieje, a dwa inne okazały się dominujące:

- **Typ działki** (budowlana / inwestycyjna / rolna / rekreacyjna / siedliskowa / inna)
  — mediana zł/m² w naszych danych: budowlana ~445, inwestycyjna ~458,
  rekreacyjna ~89, rolna ~133. Bez typu w kluczu **każda** działka rolna
  i rekreacyjna wychodziła jako 60–80% „okazja". To dokładnie ta sama pułapka,
  którą brat rozwiązał, wstawiając `miasto` do każdego klucza po dołączeniu Świdnika.
- **Przedział powierzchni** — u mieszkań zł/m² jest w przybliżeniu niezależne od
  metrażu, u gruntów spada z wielkością i to mocno: budowlana <600 m² ma medianę
  ~775 zł/m², ta sama budowlana 1200–2500 m² — ~355 zł/m². Bez tego ranking
  degenerował się do listy dużych działek. Przedziały: do 600 m², 600–1200,
  1200–2500, 2500–5000, 0,5–1 ha, od 1 ha.

Dzielnica zeszła do roli doprecyzowania (u nas zna ją tylko ~46% ogłoszeń),
więc kaskada musi działać także bez niej:
`typ+dzielnica+powierzchnia (5) → typ+dzielnica (5) → typ+powierzchnia (8) →
typ (8) → powierzchnia (8) → cały obszar`.

**Wniosek do przeniesienia:** kluczem grupy powinny być te wymiary, które
w danym repo najmocniej różnicują zł/m² — nie te, które akurat są w danych.
Warto to sprawdzić na własnych danych przed kopiowaniem kaskady.

## Oferty nietypowe — dwie różnice

1. **ROD / ogródki działkowe** to nasz odpowiednik TBS-u/udziałów u brata:
   nie kupujesz własności gruntu, tylko prawo do działki i altanę. 50 z 384
   aktywnych ofert, mediana ~74 zł/m² — bez odsiewu okupowały cały szczyt rankingu.
   Jako jedyną regułę puszczamy ją po **tytule i opisie** (brat świadomie skanuje
   sam tytuł); fraza jest na tyle jednoznaczna, że na naszych danych dała 0 fałszywek
   na działkach budowlanych. Pozostałe reguły zostały przy samym tytule.
2. **Próg ceny odstającej liczymy względem mediany GRUPY (<35%), nie mediany
   całego obszaru** jak brat (<55% mediany miasta). U nas globalna mediana miesza
   budowlane z rekreacyjnymi, więc próg globalny oflagowałby hurtem cały tańszy
   typ działki. Jeśli w danym repo grupy mają porównywalny poziom cen, wersja
   brata jest prostsza i wystarcza.

## Drobiazg przy okazji

`docs/oferty.html` obsługuje teraz `#offer=<id>` (otwiera wykres ceny w czasie),
bo znacznik 💲↓ na karcie okazji linkuje do historii ceny. `docs/index.html`
miał `#offer=` już wcześniej.
