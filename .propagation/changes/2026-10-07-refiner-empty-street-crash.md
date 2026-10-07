---
id: 2026-10-07-refiner-empty-street-crash
repo: Bonaventura-EW/SONAR---DZIA-KOWY
family: sonary
date: 2026-10-07
category: bugfix
what: Refiner lokalizacji nie wywraca już całego skanu, gdy oferta ma pustą nazwę ulicy (np. street == "ul.").
why: IndexError w nominative_variants('') przerywał main.py przed zapisem bazy — 4 z 8 skanów przepadły po cichu (workflow zielony dzięki `|| echo`).
how: Guard na pustą nazwę w nominative_variants i geocode_street, pomijanie kandydata z pola street krótszego niż 3 znaki po odcięciu "ul./al.", oraz try/except per oferta w pętli refinera w main.py (log + pominięcie).
surface: src/location_refiner.py, src/main.py, tests/test_location_refiner.py
generality: family
propagate: yes
commit: TBD
---

Dotyczy każdego brata, który ma `location_refiner.py` z `nominative_variants`
(`street.split()[-1]`). Warto też sprawdzić, czy pętla refinera jest owinięta
w try/except — pojedyncza oferta nie powinna blokować zapisu całego skanu.
