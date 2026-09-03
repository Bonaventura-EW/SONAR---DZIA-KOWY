---
id: 2026-09-02-stos-pelne-szczegoly
repo: Bonaventura-EW/SONAR---DZIA-KOWY
family: sonary
date: 2026-09-02
category: bugfix
what: Dymek „stosu" (pinezka z liczbą, kilka ofert pod jednym punktem) dostał drugi widok — pełną kartę oferty, tę samą co pojedyncza pinezka — zamiast kończyć się na płaskiej liście.
why: Grupowanie ofert o identycznych współrzędnych naprawiło klikalność (wcześniej dostępna była tylko wierzchnia pinezka), ale zabrało dane: z listy nie dało się dojść do zdjęcia, trendu ceny, paska odniesienia rynkowego, opisu ani daty w bazie. U nas dotyczyło to 137 z ~380 widocznych punktów, a największy stos miał 23 oferty — czyli sporej części mapy.
how: Marker stosu trzyma stan widoku (`_detailId`, `_focusId`) i posortowaną grupę, a treść dymka jest FUNKCJĄ (`bindPopup(() => stackPopupContent(marker))`), więc przełączenie widoku to samo `popup.update()` — Leaflet przerysowuje zawartość w miejscu, bez zamykania dymka i bez `render()` mapy. Widok szczegółów to nagłówek (powrót do listy + strzałki ‹ ›, „i / N") sklejony z niezmienionym `popupHtml(offer)`, więc karta stosu i karta pojedynczej pinezki nie mogą się rozjechać. Wiersz listy jest `<button>` (klawiatura, focus-visible) plus osobny link „↗" prosto do ogłoszenia. Wejście z `#offer=<id>` ustawia `_detailId` przed `openPopup()` i otwiera od razu właściwą kartę.
surface: docs/assets/script.js, docs/assets/style.css, docs/index.html, docs/*.html (bump ?v=4), CHANGELOG.md
generality: family
propagate: yes
commit: c482c3c
---

# Kontekst dla braci

Bierzcie, jeśli macie u siebie grupowanie pinezek w stosy (u nas przyszło
manifestem `2026-08-31`-owym, PR „Grupowanie markerów w stosy przy identycznych
współrzędnych"). Sama lista w dymku to regres funkcjonalny, tylko mniej
widoczny niż problem, który naprawiała: użytkownik nie dostaje komunikatu
o brakujących danych — po prostu ich nie ma.

## Pułapka, na której to najpierw nie działało

Klik w wiersz listy przerysowuje zawartość dymka (`innerHTML`), więc kliknięty
węzeł **znika z DOM zanim zdarzenie skończy bąbelkować**. Leaflet szuka wtedy
rodziców celu, nie znajduje kontenera popupu (element jest już odpięty), uznaje
klik za klik w mapę i przy domyślnym `closePopupOnClick: true` zamyka właśnie
otwarty dymek — efekt: „przycisk nic nie robi". Lekarstwo: `stopPropagation()`
w handlerze wiersza (u nas pierwszy argument `event` w inline `onclick`).
Alternatywnie: odroczyć `update()` do `setTimeout(…, 0)`, ale wtedy widok mruga.

## Decyzje warte skopiowania (albo świadomego odrzucenia)

- **Nie duplikujcie treści karty.** Widok szczegółów woła istniejącą funkcję
  renderującą dymek pojedynczej oferty. Inaczej za pół roku karta ze stosu
  będzie miała o dwa pola mniej i nikt nie zauważy.
- **Stan na markerze, nie w globalnym obiekcie widoku.** `render()` przebudowuje
  markery przy każdej zmianie filtrów; stan trzymany obok szybko zostaje sierotą.
- **Zostawcie bezpośredni link.** Ludzie klikali w tytuł, żeby wyjść na portal —
  master-detail to zabiera, więc „↗" w wierszu wraca z tym jednym kliknięciem.
- Odrzucone: „spiderfy" (rozsunięcie pinezek po okręgu). U nas stosy biorą się
  z centroidów dzielnicy/miasta wstawianych przez portale — rozsuwanie
  rysowałoby oferty w miejscach, w których ich nie ma. Jeśli u Was stos oznacza
  „naprawdę ten sam budynek", spiderfy może być lepszy niż lista.
