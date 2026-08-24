---
id: 2026-08-24-olx-tls-impersonation
repo: Bonaventura-EW/SONAR---DZIA-KOWY
family: sonary
date: 2026-08-24
category: bugfix
what: Scraper OLX chodzi przez curl_cffi z impersonacją TLS przeglądarki — omija blokadę 403 CloudFront/WAF.
why: Od 2026-08-11 OLX odrzucał KAŻDY request `requests` kodem 403 (także z pełnym zestawem nagłówków Chrome'a). Skan przez 26 kolejnych przebiegów zbierał 0 ofert z OLX, a mapa pokazywała nieaktualne dane tego portalu.
how: Blokada idzie po fingerprincie TLS (JA3) — handshake pythonowego OpenSSL nie wygląda jak przeglądarka, więc podmiana nagłówków nic nie daje. Warstwa HTTP scrapera przeszła na `curl_cffi.requests.Session(impersonate=...)`, które odtwarza handshake prawdziwego Chrome'a/Safari. Profile próbowane po kolei (chrome131 → chrome124 → chrome110 → safari17_0 → edge101), bo nowsze buildy używają rozszerzeń TLS ucinanych przez niektóre proxy/MITM; po ich wyczerpaniu fallback na gołe `requests`, a import curl_cffi jest opcjonalny (brak biblioteki = zachowanie sprzed zmiany). API curl_cffi jest zgodne z requests, więc reszta scrapera bez zmian.
surface: src/olx_scraper.py, requirements.txt, tests/test_olx_fetch.py
generality: family
propagate: yes
commit: 3788c40
---

# Kontekst

Weryfikacja przed wdrożeniem (warto powtórzyć u siebie, bo blokady bywają
per-URL i per-IP):

- `requests` + nagłówki Chrome'a (sec-ch-ua, Sec-Fetch-*, Accept-Encoding br) → **403**, body CloudFront „Request blocked".
- `curl_cffi` z `impersonate='chrome110'` / `safari17_0` / `edge101` → **200**, pełny `__PRERENDERED_STATE__`, 64 oferty z Lublina.
- Ten sam 403 leci z runnerów GitHub Actions (potwierdzone w logach skanu), więc to nie jest problem lokalnego IP.

Odrzucone alternatywy: (a) same nagłówki — przetestowane, nie działa;
(b) Playwright/headless — działa, ale to ~300 MB w CI i kilkadziesiąt sekund
na skan zamiast ~2 s; sensowne dopiero gdy impersonacja przestanie wystarczać;
(c) proxy rezydencjalne — koszt i zależność od zewnętrznej usługi.

Uwaga dla brata: jeśli wasz scraper OLX/Otodom dzieli sesję `requests` między
źródła, podmieniajcie ją tylko dla zablokowanego źródła — `curl_cffi` niesie
binarkę libcurl-impersonate (~5 MB wheel), ale nie ma powodu przepinać na nią
działających scraperów.
