---
id: 2026-08-24-alarm-awarii-zrodla
repo: Bonaventura-EW/SONAR---DZIA-KOWY
family: sonary
date: 2026-08-24
category: feature
what: API (health.json/status.json) alarmuje, gdy pojedyncze źródło przestaje zwracać oferty, mimo że cały skan kończy się sukcesem.
why: Martwy scraper jednego portalu był NIEWIDOCZNY — skan miał status 'completed' (inne źródła działały), ochrona przed masową dezaktywacją słusznie zostawiała oferty aktywne, a health.json raportował 'ok' przez 26 skanów z rzędu (13 dni z zerowym OLX-em).
how: Nowy moduł `src/source_health.py` liczy z `data/scan_history.json` normę każdego źródła (mediana z 10 ostatnich udanych skanów) i porównuje ją z ostatnim skanem: 0 ofert = `source_down` (warning po pierwszym pustym skanie, critical po ≥2, czyli ok. dobie), <30% normy = `source_degraded`. Nieudane skany są pomijane (nic nie mówią o pojedynczym źródle), a źródło bez historii (<3 udane skany) daje status `unknown` zamiast fałszywego alarmu. `api_generator` wystawia `alerts` + `sources` w health.json i `alerts` w status.json, `health.status` schodzi na nowe `degraded`, a alarmy lecą też na stdout i jako annotacje runa GitHub Actions (`::error`/`::warning`) oraz do dashboardu monitoringu (czerwony pasek).
surface: src/source_health.py, src/api_generator.py, src/monitoring_generator.py, docs/monitoring.html, docs/assets/style.css, docs/API.md, tests/test_source_health.py
generality: family
propagate: yes
commit: 3788c40
---

# Kontekst

Wzorzec jest przenośny wszędzie tam, gdzie skan agreguje kilka źródeł, a
awaria jednego nie wywraca całego przebiegu — czyli w każdym sonarze. Do
adaptacji wystarczy zmapować `SOURCE_FIELDS` na własne pola w scan_history
(u nas: scraped_olx / scraped_otodom / scraped_adresowo / scraped_agencies).

Progi (DOWN_AFTER_SCANS=2, DEGRADED_RATIO=0.3, BASELINE_SCANS=10) są
dobrane pod 2 skany dziennie — przy częstszych skanach warto podnieść
DOWN_AFTER_SCANS, żeby jedna wpadka portalu nie krzyczała od razu jako
`critical`.

Świadoma decyzja: `warning` (pojedynczy pusty skan) NIE zmienia
`health.status` na `degraded` — dopiero `critical`. Inaczej healthcheck
migotałby przy każdym chwilowym throttlingu.
