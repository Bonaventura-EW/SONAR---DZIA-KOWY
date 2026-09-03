/**
 * Sekcja „Indeks podaży i ruch na rynku" na docs/analytics.html.
 *
 * Czyta docs/trend_data.json (src/trend_generator.py) i rysuje sześć wykresów
 * ApexCharts: Indeks aktywnych ofert (z rozbiciem na pasma świeże/recykling),
 * odpływ, nowe oferty, napływ całkowity, reaktywacje i płatne wyróżnienia OLX.
 *
 * Wzorowane na trend.html z SONAR-POKOJOWY; paleta i tło dostosowane do
 * jasnego motywu tego serwisu (assets/style.css).
 */
(function () {
    'use strict';

    // paleta spójna z resztą serwisu (--green-600 / --lime z style.css)
    var INK = '#0f1f15';
    var MUTED = '#64748b';
    var GRID = '#dce5dc';
    var GREEN = '#16a34a';
    var RED = '#dc2626';

    // Polski locale — miesiące na osi X po polsku (sty/lut/…)
    var PL_LOCALE = {
        name: 'pl',
        options: {
            months: ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec',
                     'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień'],
            shortMonths: ['sty', 'lut', 'mar', 'kwi', 'maj', 'cze', 'lip', 'sie', 'wrz', 'paź', 'lis', 'gru'],
            days: ['niedziela', 'poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota'],
            shortDays: ['niedz', 'pon', 'wt', 'śr', 'czw', 'pt', 'sob'],
            toolbar: {
                exportToSVG: 'Pobierz SVG', exportToPNG: 'Pobierz PNG', exportToCSV: 'Pobierz CSV',
                menu: 'Menu', selection: 'Zaznaczenie', selectionZoom: 'Zoom zaznaczenia',
                zoomIn: 'Powiększ', zoomOut: 'Pomniejsz', pan: 'Przesuń', reset: 'Reset zoomu'
            }
        }
    };

    var TOOLBAR = {
        show: true,
        tools: { download: true, selection: true, zoom: true, zoomin: true, zoomout: true, pan: true, reset: true }
    };

    function baseChart(type, height) {
        return {
            type: type, height: height, background: 'transparent',
            locales: [PL_LOCALE], defaultLocale: 'pl',
            fontFamily: 'inherit', foreColor: MUTED,
            toolbar: TOOLBAR, animations: { enabled: true, speed: 550 }, zoom: { enabled: true }
        };
    }

    var TIME_AXIS = {
        type: 'datetime', axisBorder: { show: false }, axisTicks: { color: GRID },
        labels: {
            datetimeUTC: false, style: { colors: MUTED },
            datetimeFormatter: { year: 'yyyy', month: "MMM 'yy", day: 'dd MMM', hour: 'HH:mm' }
        }
    };

    var GRID_OPTS = {
        borderColor: GRID, strokeDashArray: 4,
        xaxis: { lines: { show: true } }, yaxis: { lines: { show: true } }
    };

    function pl(value) {
        return String(value).replace('.', ',');
    }

    function fail(id, message) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="chart-loading">' + message + '</div>';
    }

    function mount(id, options) {
        var el = document.getElementById(id);
        if (!el) return null;
        el.innerHTML = '';
        var chart = new ApexCharts(el, options);
        chart.render();
        return chart;
    }

    /** Wykres przepływu: seria dzienna (ostra linia) + średnia 7 dni (gładka). */
    function flowOptions(metric, dailyName, colors) {
        return {
            chart: baseChart('line', 320),
            series: [
                { name: dailyName, data: metric.daily },
                { name: 'Średnia 7 dni', data: metric.avg }
            ],
            colors: colors,
            stroke: { curve: ['straight', 'smooth'], width: [2, 3] },
            dataLabels: { enabled: false },
            markers: { size: 0, hover: { size: 5 } },
            grid: GRID_OPTS,
            xaxis: TIME_AXIS,
            yaxis: {
                min: 0, tickAmount: 4,
                labels: { style: { colors: MUTED }, formatter: function (v) { return Math.round(v); } }
            },
            legend: { labels: { colors: MUTED }, markers: { radius: 12 }, itemMargin: { horizontal: 10 } },
            tooltip: {
                shared: true, x: { format: 'dd.MM.yyyy' },
                y: { formatter: function (v) { return v == null ? '—' : (pl(v) + ' ofert'); } }
            }
        };
    }

    function flowSummary(metric, prefix, afterRate, suffix) {
        return prefix + ' <b>' + pl(metric.rate) + '/dzień</b>' + (afterRate ? ' ' + afterRate : '') +
               ', rekord <b>' + metric.max_day + '</b> (' + metric.max_label + ').' +
               (suffix ? ' ' + suffix : '');
    }

    function setText(id, text) {
        var el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function setHTML(id, html) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = html;
    }

    function renderDeltas(deltas) {
        var order = ['1D', '1M', '6M', '1Y'];
        setHTML('trendDeltas', order.map(function (label) {
            var v = (deltas || {})[label];
            if (v === null || v === undefined) {
                return '<span><b>' + label + ':</b><span class="na">—</span></span>';
            }
            var cls = v > 0 ? 'pos' : (v < 0 ? 'neg' : 'na');
            return '<span><b>' + label + ':</b><span class="' + cls + '">' +
                   (v > 0 ? '+' : '') + v + '</span></span>';
        }).join(''));
    }

    /** Indeks: pole aktywnych ofert + linie MAX/MIN, z przełącznikiem na pasma. */
    function renderIndex(d) {
        var series = d.series || [];
        if (!series.length) {
            fail('trendChart', 'Brak danych w serii.');
            return;
        }
        var cur = d.current, mx = d.max, mn = d.min, unit = d.unit || 'ofert';
        var range = (mx - mn) || 1;

        // Etykiety MAX/MIN/„teraz" potrafią się nakładać, gdy bieżąca wartość
        // leży przy krawędzi zakresu — wtedy pomijamy redundantną etykietę
        // „teraz": ta sama liczba jest już na linii MAX/MIN i w nagłówku karty.
        var curNearEdge = Math.abs(cur - mx) <= range * 0.07 || Math.abs(cur - mn) <= range * 0.07;

        // Etykieta adnotacji: KOLOROWY tekst bez tła. ApexCharts 3.49 wystawia
        // prostokąt tła poza obszar wykresu (x=-137), więc biały napis „na
        // kolorowym tle" — jak u brata z ciemnym motywem — byłby na naszym
        // jasnym tle niewidoczny. Kolor tekstu = kolor linii, którą opisuje.
        function annotationLabel(text, color, position, offsetX, weight) {
            return {
                text: text, position: position, offsetX: offsetX,
                style: { background: 'transparent', color: color,
                         fontSize: '12px', fontWeight: weight }
            };
        }

        var yAnnotations = [
            {
                y: mx, borderColor: RED, strokeDashArray: 5,
                label: annotationLabel('MAX: ' + mx, RED, 'left', 64, 700)
            },
            // MIN po PRAWEJ: linia minimum biegnie nisko, w obszarze wypełnienia,
            // więc przy lewej krawędzi etykieta ginęła pod danymi.
            {
                y: mn, borderColor: GREEN, strokeDashArray: 5,
                label: annotationLabel('MIN: ' + mn, GREEN, 'right', -6, 700)
            }
        ];
        if (!curNearEdge) {
            yAnnotations.push({
                y: cur, borderColor: '#0284c7', strokeDashArray: 3,
                label: annotationLabel('teraz: ' + cur, '#0284c7', 'left', 84, 700)
            });
        }

        var options = {
            chart: Object.assign(baseChart('area', 440), { animations: { enabled: true, speed: 600 } }),
            series: [{ name: 'Aktywne oferty', data: series }],
            colors: [GREEN],
            stroke: { curve: 'straight', width: 2 },
            fill: {
                type: 'gradient',
                gradient: {
                    shadeIntensity: 1, opacityFrom: 0.45, opacityTo: 0.03, stops: [0, 90, 100],
                    colorStops: [
                        { offset: 0, color: GREEN, opacity: 0.45 },
                        { offset: 100, color: GREEN, opacity: 0.02 }
                    ]
                }
            },
            dataLabels: { enabled: false },
            grid: GRID_OPTS,
            xaxis: TIME_AXIS,
            yaxis: {
                // Bez widełek Apex dobiera „ładną" skalę schodzącą poniżej zera —
                // ujemna liczba ofert nie znaczy nic, a wahania robią się płaskie.
                min: Math.max(0, Math.floor((mn - Math.max(10, range * 0.25)) / 10) * 10),
                max: Math.ceil((mx + Math.max(10, range * 0.25)) / 10) * 10,
                tickAmount: 5,
                labels: { style: { colors: MUTED }, formatter: function (v) { return Math.round(v); } }
            },
            tooltip: {
                x: { format: 'dd.MM.yyyy' },
                y: { formatter: function (v) { return v == null ? '— (brak skanu)' : (v + ' ' + unit); } }
            },
            annotations: {
                // 'front' — inaczej wypełnienie pola zamalowuje etykietę MIN,
                // która leży nisko, dokładnie w obszarze serii.
                position: 'front',
                yaxis: yAnnotations,
                points: [
                    { x: d.max_ts, y: mx, marker: { size: 5, fillColor: RED, strokeColor: '#fff', strokeWidth: 1 } },
                    { x: d.min_ts, y: mn, marker: { size: 5, fillColor: GREEN, strokeColor: '#fff', strokeWidth: 1 } }
                ]
            }
        };

        // Rozbicie na pasma (stacked area): dół = oferty świeże, góra = recykling.
        // Suma pasm == linia Indeksu (generator skaluje udziały do mierzonej liczby).
        var bands = d.bands && d.bands.new && d.bands.new.length ? d.bands : null;
        var chart = null, mode = 0;

        function stackedOptions() {
            return Object.assign({}, options, {
                chart: Object.assign({}, options.chart, {
                    stacked: true, animations: { enabled: true, speed: 450 }
                }),
                series: [
                    { name: 'Nowe (świeże)', data: bands.new },
                    { name: 'Reaktywowane (recykling)', data: bands.react }
                ],
                colors: [GREEN, '#f97316'],
                stroke: { curve: 'straight', width: 1.5 },
                // Stos rysuje się OD ZERA, więc oś nie może być przycięta do
                // okolic Indeksu jak w trybie sumy — dolne pasmo (dziś ~400)
                // schowałoby się pod dolną krawędzią i zostałby sam recykling.
                yaxis: {
                    min: 0, max: Math.ceil(mx * 1.05 / 10) * 10, tickAmount: 5,
                    labels: { style: { colors: MUTED }, formatter: function (v) { return Math.round(v); } }
                },
                fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.7, opacityTo: 0.3, stops: [0, 100] } },
                annotations: {},
                legend: { labels: { colors: MUTED }, markers: { radius: 12 }, itemMargin: { horizontal: 10 } },
                tooltip: {
                    shared: true, x: { format: 'dd.MM.yyyy' },
                    y: { formatter: function (v) { return v == null ? '—' : (v + ' ' + unit); } }
                }
            });
        }

        function chip(color, label) {
            return '<span class="ci"><span class="dot" style="background:' + color + '"></span>' + label + '</span>';
        }

        function draw() {
            if (chart) chart.destroy();
            chart = mount('trendChart', (mode === 1 && bands) ? stackedOptions() : options);
            var sumBtn = document.getElementById('idxSum');
            var splitBtn = document.getElementById('idxSplit');
            if (sumBtn) sumBtn.classList.toggle('on', mode === 0);
            if (splitBtn) splitBtn.classList.toggle('on', mode === 1);
            if (mode === 1 && bands) {
                var n = bands.new[bands.new.length - 1][1];
                var r = bands.react[bands.react.length - 1][1];
                var total = n + r;
                var pct = total ? Math.round(100 * r / total) : 0;
                setHTML('idxLegend',
                    chip(GREEN, 'Nowe (świeże) — dół') + chip('#f97316', 'Reaktywowane (recykling) — góra') +
                    '<span class="ci muted">' + n + ' + ' + r + ' = ' + total + ' aktywnych · <b>' +
                    pct + '%</b> recykling · podział szacunkowy, recykling zaniżony</span>');
            } else {
                setHTML('idxLegend', '');
            }
        }

        var splitBtn = document.getElementById('idxSplit');
        var sumBtn = document.getElementById('idxSum');
        if (bands && splitBtn && sumBtn) {
            sumBtn.addEventListener('click', function () { mode = 0; draw(); });
            splitBtn.addEventListener('click', function () { mode = 1; draw(); });
        } else if (splitBtn) {
            splitBtn.style.display = 'none';  // brak danych pasm → tylko Suma
        }
        draw();
    }

    /** Promowane: liczba wyróżnień (lewa oś) + udział w rynku (prawa, ukryta). */
    function renderPromoted(pr) {
        // Zakresy obu osi liczone z danych. Bez tego Apex, dopasowując dwie osie
        // do siebie, rozciąga skalę „ofert" kilkukrotnie ponad dane i wykres
        // robi się płaski. Oś nie startuje od zera, bo to metryka STANU —
        // od zera nie widać wahań rzędu kilku ofert.
        function span(pairs, padLow, padHigh) {
            var values = (pairs || []).map(function (p) { return p[1]; })
                                      .filter(function (v) { return v != null; });
            if (!values.length) return { min: 0, max: 1 };
            var lo = Math.min.apply(null, values), hi = Math.max.apply(null, values);
            var pad = Math.max((hi - lo) || hi * 0.1, 1);
            return { min: Math.max(0, lo - pad * padLow), max: hi + pad * padHigh };
        }
        var spanCount = span(pr.daily, 0.6, 0.4);
        var spanShare = span(pr.share, 0.6, 0.4);
        // Liczba wyróżnień to liczba całkowita. Bez zaokrąglenia widełek
        // i przycięcia liczby podziałek świeża metryka (dwa dni, wartość 2)
        // rysuje oś „2 / 2 / 2 / 2" — cztery podziałki na zakresie 1,4–2,4.
        var countMin = Math.floor(spanCount.min);
        var countMax = Math.ceil(spanCount.max);
        var countTicks = Math.min(4, Math.max(1, countMax - countMin));

        // Minimalny zakres osi czasu — patrz komentarz przy `xaxis` niżej.
        var DAY = 86400000, MIN_DAYS = 6;
        var firstMs = pr.daily[0][0], lastMs = pr.daily[pr.daily.length - 1][0];
        var missingMs = Math.max(0, MIN_DAYS * DAY - (lastMs - firstMs));
        var axisSpan = { min: firstMs - missingMs / 2 - DAY / 2,
                         max: lastMs + missingMs / 2 + DAY / 2 };

        mount('promotedChart', {
            chart: Object.assign(baseChart('line', 320), {
                // Udział w rynku startuje ukryty (kliknięcie w legendę go pokazuje):
                // jest proporcjonalny do liczby wyróżnień, więc na starcie tylko
                // dubluje kształt tamtej linii. Ma sens dopiero przy porównaniu
                // okresów o różnej wielkości rynku.
                events: { mounted: function (ctx) { ctx.hideSeries('Udział w rynku'); } }
            }),
            series: [
                { name: 'Wyróżnione danego dnia', data: pr.daily },
                { name: 'Średnia 7 dni', data: pr.avg },
                { name: 'Udział w rynku', data: pr.share }
            ],
            colors: ['#eab308', '#fde047', '#7c3aed'],
            stroke: { curve: ['straight', 'smooth', 'smooth'], width: [2, 3, 2], dashArray: [0, 0, 5] },
            dataLabels: { enabled: false },
            markers: { size: 0, hover: { size: 5 } },
            grid: GRID_OPTS,
            // Wymuszony format dzienny: metryka startuje od dnia wdrożenia, więc
            // przy dwóch punktach Apex rozpisywał oś na GODZINY (12:00, 13:00…),
            // choć każdy punkt to cały dzień.
            // …a przy zakresie krótszym niż kilka dni Apex rozpisuje oś na
            // GODZINY: dwa dni danych dawały 24 etykiety („02 wrz" ×12,
            // „03 wrz" ×12). Rozciągamy więc sam ZAKRES osi do minimum 6 dni —
            // punkty zostają w miejscu, a podziałki wracają na dni.
            xaxis: Object.assign({}, TIME_AXIS, {
                labels: Object.assign({}, TIME_AXIS.labels, { format: 'dd MMM' }),
                min: axisSpan.min, max: axisSpan.max
            }),
            yaxis: [
                {
                    seriesName: 'Wyróżnione danego dnia', min: countMin, max: countMax, tickAmount: countTicks,
                    labels: { style: { colors: MUTED }, formatter: function (v) { return Math.round(v); } },
                    title: { text: 'ofert', style: { color: MUTED, fontWeight: 500 } }
                },
                { seriesName: 'Wyróżnione danego dnia', show: false },
                {
                    seriesName: 'Udział w rynku', opposite: true, min: spanShare.min, max: spanShare.max, tickAmount: 4,
                    labels: {
                        style: { colors: MUTED },
                        formatter: function (v) { return pl(Math.round(v * 10) / 10) + '%'; }
                    },
                    title: { text: '% rynku', style: { color: MUTED, fontWeight: 500 } }
                }
            ],
            legend: { labels: { colors: MUTED }, markers: { radius: 12 }, itemMargin: { horizontal: 10 } },
            tooltip: {
                shared: true, x: { format: 'dd.MM.yyyy' },
                y: [
                    { formatter: function (v) { return v == null ? '—' : (v + ' ofert'); } },
                    { formatter: function (v) { return v == null ? '—' : (pl(v) + ' ofert'); } },
                    { formatter: function (v) { return v == null ? '—' : (pl(v) + '% rynku'); } }
                ]
            }
        });
    }

    var CHART_IDS = ['trendChart', 'outflowChart', 'newFlowChart', 'allFlowChart',
                     'reactFlowChart', 'promotedChart'];

    function init(d) {
        if (d.title) setText('trendTitle', '📉 Indeks podaży — ' + d.title);
        setText('trendLastLabel', d.last_label || '—');
        setText('trendCurVal', d.current == null ? '—' : d.current);
        setText('trendDedupNote', d.current_dedup == null ? '—'
            : (d.current + ' ofert w bazie → ' + d.current_dedup + ' pinezek na mapie'));
        renderDeltas(d.deltas);
        renderIndex(d);

        var of = d.outflow;
        if (of && of.daily && of.daily.length) {
            setHTML('outLabel', flowSummary(of, 'Znika średnio', '',
                'Pomarańczowa = wygładzony trend (7 dni).'));
            mount('outflowChart', flowOptions(of, 'Znikło danego dnia', [RED, '#f59e0b']));
        } else {
            fail('outflowChart', 'Brak danych o odpływie.');
        }

        var inf = d.inflow;
        if (inf && inf.new && inf.new.daily && inf.new.daily.length) {
            setHTML('newLabel', flowSummary(inf.new, 'Pojawia się średnio', '',
                'Zielona = nowe, jasna = trend 7 dni.'));
            setHTML('allLabel', flowSummary(inf.new_react, 'Średnio',
                'pojawień na rynku (świeże + wskrzeszone)', ''));
            setHTML('reactLabel', flowSummary(inf.react, 'Wraca średnio', '',
                'Wstecz zaniżone — patrz opis pod wykresem.'));
            mount('newFlowChart', flowOptions(inf.new, 'Nowe danego dnia', [GREEN, '#86efac']));
            mount('allFlowChart', flowOptions(inf.new_react, 'Pojawiło się danego dnia', ['#0284c7', '#7dd3fc']));
            mount('reactFlowChart', flowOptions(inf.react, 'Reaktywacje danego dnia', ['#0d9488', '#5eead4']));
        } else {
            ['newFlowChart', 'allFlowChart', 'reactFlowChart'].forEach(function (id) {
                fail(id, 'Brak danych o napływie.');
            });
        }

        var pr = d.promoted;
        if (pr && pr.daily && pr.daily.length) {
            setHTML('promoLabel',
                'Teraz <b>' + (pr.current == null ? '—' : pr.current) + '</b> wyróżnionych' +
                (pr.current_share == null ? '' : ' (<b>' + pl(pr.current_share) + '%</b> rynku)') +
                ', ' + flowSummary(pr, 'średnio', '', ''));
            setText('promoSince', pr.start_label || '—');
            renderPromoted(pr);
        } else {
            fail('promotedChart', 'Metryka rusza od pierwszego skanu po wdrożeniu detekcji wyróżnień — ' +
                'wykres pojawi się, gdy uzbieramy pierwszy dzień danych.');
        }
    }

    function start() {
        fetch('trend_data.json?v=' + Date.now())
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(init)
            .catch(function (e) {
                CHART_IDS.forEach(function (id) {
                    fail(id, 'Nie udało się wczytać danych (' + e.message + ').');
                });
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
