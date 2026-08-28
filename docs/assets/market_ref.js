/* SONAR DZIAŁKOWY — odniesienie rynkowe (mediana zł/m² grupy porównywalnych).
 *
 * FIX 2026-08-28: wspólny moduł dla docs/okazje.html (ranking okazji) i
 * docs/assets/script.js (pasek „ta oferta vs mediana grupy" w dymku na mapie).
 * Obie strony MUSZĄ liczyć to samo — inaczej ta sama działka pokazywałaby
 * na mapie inny procent niż w rankingu.
 *
 * Metodyka (opisana dla użytkownika w sekcji „Jak liczymy okazję" na okazje.html):
 * dla każdej oferty szukamy mediany zł/m² w najwęższej grupie porównywalnych,
 * w której starcza próbki. Typ działki i przedział powierzchni są częścią
 * KAŻDEGO klucza (poza ostatnim awaryjnym), bo przy gruntach to one różnicują
 * zł/m² najmocniej: budowlana ~445 zł/m² vs rekreacyjna ~89 zł/m², a ta sama
 * budowlana poniżej 600 m² ~775 zł/m² wobec ~355 zł/m² przy 1200–2500 m².
 */
const MarketRef = (function () {

    // Przedziały powierzchni — zł/m² gruntu mocno spada z wielkością działki.
    const AREA_BUCKETS = [
        [0,     600,      'do 600 m²'],
        [600,   1200,     '600–1200 m²'],
        [1200,  2500,     '1200–2500 m²'],
        [2500,  5000,     '2500–5000 m²'],
        [5000,  10000,    '0,5–1 ha'],
        [10000, Infinity, 'od 1 ha'],
    ];

    function areaBucket(a) {
        if (a == null) return null;
        const b = AREA_BUCKETS.find(([lo, hi]) => a >= lo && a < hi);
        return b ? b[2] : null;
    }

    const plotType = o => o.plot_type || 'inna';

    function median(arr) {
        if (!arr.length) return null;
        const s = [...arr].sort((a, b) => a - b), m = Math.floor(s.length / 2);
        return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
    }

    // --- oferty nietypowe: formalnie nie są zwykłą sprzedażą gruntu ----------
    // ROD-a szukamy w tytule I opisie — to najliczniejsze zniekształcenie
    // (ok. 50 z ~384 aktywnych ofert, mediana ~74 zł/m²), a fraza jest
    // jednoznaczna. Reszta reguł patrzy tylko na tytuł: w opisie „udział"
    // bywa niewinny („udział w kosztach mediów").
    const ROD_RE = /\bROD\b|rodzinn\w*\s+ogr[oó]d|ogr[oó]d(?:ek|ka|ki|y|zie|u|em)?\s+dzia[lł]kow|dzia[lł]k\w*\s+ogrodow/;
    const TITLE_RULES = [
        [/\budzia[łl]\w*/i,                       'udział w nieruchomości'],
        [/syndyk|licytacj|komornicz|egzekucyj/i,  'licytacja / syndyk'],
        [/u[żz]ytkowani\w*\s+wieczyst|wieczyst\w*\s+u[żz]ytkowani/i, 'użytkowanie wieczyste (nie własność)'],
        [/dzier[żz]aw/i,                          'dzierżawa, nie sprzedaż'],
        [/zamieni[eę]|zamiana\s+na/i,             'zamiana, nie sprzedaż'],
        [/miejsce\s+postojow|\bpiwnic\w*\b/i,     'to nie jest działka'],
    ];

    function keywordReasons(o) {
        const title = o.title || '';
        const out = [];
        if (ROD_RE.test(title + ' ' + (o.description || '')))
            out.push('ROD / ogródek działkowy — prawo do działki, nie własność gruntu');
        TITLE_RULES.forEach(([re, why]) => { if (re.test(title)) out.push(why); });
        if (o.area_m2 < 100) out.push('powierzchnia poniżej 100 m² — to raczej nie jest działka');
        return out;
    }

    // Próg ceny odstającej liczony WZGLĘDEM GRUPY, nie mediany całego miasta:
    // globalna mediana miesza budowlane z rekreacyjnymi, więc próg globalny
    // oflagowałby hurtem cały tańszy typ działki.
    const OUTLIER_RATIO = 0.35;
    function oddReasons(o, ratio) {
        const kw = keywordReasons(o);
        return (ratio != null && ratio < OUTLIER_RATIO)
            ? kw.concat('cena/m² rażąco poniżej porównywalnych — możliwy błąd lub haczyk')
            : kw;
    }

    /* Buduje odniesienia z listy ofert i zwraca obiekt z metodą ref(offer).
     *
     * Bazą są WYŁĄCZNIE oferty aktywne, z ceną/m² i powierzchnią, i tylko te
     * „zdrowe" (bez sygnałów nietypowości) — ROD-y i udziały zaniżyłyby mediany.
     * Pytać można o dowolną ofertę, także nieaktywną: porównanie z bieżącym
     * rynkiem nadal ma sens.
     */
    function build(offers, globalMedian) {
        const usable = (offers || []).filter(
            o => o.active && o.price_per_m2 > 0 && o.area_m2 > 0);
        const base = usable.filter(o => !keywordReasons(o).length);
        const globalMed = globalMedian || median(usable.map(o => o.price_per_m2));

        const g1 = {}, g2 = {}, g3 = {}, g4 = {}, g5 = {};
        base.forEach(o => {
            const t = plotType(o), d = o.district, ab = areaBucket(o.area_m2);
            if (d && ab) (g1[t + '§' + d + '§' + ab] ??= []).push(o.price_per_m2);
            if (d)       (g2[t + '§' + d] ??= []).push(o.price_per_m2);
            if (ab)      (g3[t + '§' + ab] ??= []).push(o.price_per_m2);
            (g4[t] ??= []).push(o.price_per_m2);
            if (ab)      (g5[ab] ??= []).push(o.price_per_m2);
        });
        const agg = g => Object.fromEntries(
            Object.entries(g).map(([k, v]) => [k, { med: median(v), n: v.length }]));
        const R = { g1: agg(g1), g2: agg(g2), g3: agg(g3), g4: agg(g4), g5: agg(g5) };

        /* Kaskada: najwęższa grupa z wystarczającą próbką wygrywa.
         *
         * Poziomy 1–4 mają typ działki w kluczu. Poziomy 5–6 go NIE mają i są
         * oznaczane `weak: true` — porównanie działki rekreacyjnej z medianą
         * zdominowaną przez budowlane dałoby fałszywe „85% poniżej rynku".
         * Strony mają traktować `weak` jako „brak dobrej grupy porównawczej",
         * a nie jako wycenę.
         *
         * FIX 2026-08-28: próg poziomu 4 (cały typ, całe miasto) obniżony z 8 na 5.
         * Rekreacyjne mają tylko 6 „zdrowych" ofert (12 z 18 to ROD-y odsiane
         * z bazy median), więc przy progu 8 wpadały właśnie w mieszaną grupę.
         * 5 to ten sam próg, co dla węższych grup 1–2, więc szersza grupa nie
         * ma powodu wymagać więcej.
         */
        function ref(o) {
            const t = plotType(o), d = o.district, ab = areaBucket(o.area_m2);
            let hit;
            if (d && ab && (hit = R.g1[t + '§' + d + '§' + ab]) && hit.n >= 5)
                return { value: hit.med, n: hit.n, label: `${t} · ${d} · ${ab}` };
            if (d && (hit = R.g2[t + '§' + d]) && hit.n >= 5)
                return { value: hit.med, n: hit.n, label: `${t} · ${d}` };
            if (ab && (hit = R.g3[t + '§' + ab]) && hit.n >= 8)
                return { value: hit.med, n: hit.n, label: `${t} · ${ab} · cały Lublin` };
            if ((hit = R.g4[t]) && hit.n >= 5)
                return { value: hit.med, n: hit.n, label: `${t} · cały Lublin` };
            if (ab && (hit = R.g5[ab]) && hit.n >= 8)
                return { value: hit.med, n: hit.n, weak: true,
                         label: `${ab} · wszystkie typy (brak próbki dla „${t}")` };
            return { value: globalMed, n: usable.length, weak: true,
                     label: `cały obszar (brak próbki dla „${t}")` };
        }

        /* Komplet liczb dla jednej oferty albo null, gdy nie ma czego porównać.
         * ratio  — zł/m² oferty / mediana grupy (1 = dokładnie w medianie)
         * disc   — o ile % PONIŻEJ mediany (ujemne = powyżej)
         * save   — szacowana oszczędność w zł (0, gdy oferta jest powyżej)   */
        function evaluate(o) {
            if (!(o.price_per_m2 > 0) || !(o.area_m2 > 0)) return null;
            const r = ref(o);
            if (!r.value) return null;
            const ratio = o.price_per_m2 / r.value;
            return {
                ref: r,
                ratio,
                disc: (1 - ratio) * 100,
                save: Math.max(0, (r.value - o.price_per_m2) * o.area_m2),
                odd: oddReasons(o, ratio),
                // grupa bez typu działki — liczba jest orientacyjna, nie wyceną
                weak: !!r.weak,
            };
        }

        return { ref, evaluate, globalMedian: globalMed, baseCount: base.length, usable };
    }

    return {
        AREA_BUCKETS, areaBucket, plotType, median,
        keywordReasons, oddReasons, OUTLIER_RATIO, build,
    };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = MarketRef;  // testy w node
