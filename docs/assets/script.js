/* SONAR DZIAŁKOWY — frontend mapy (Leaflet).
 * Czyta data.json wygenerowany przez src/map_generator.py. */

const LUBLIN_CENTER = [51.2465, 22.5684];
const NEW_OFFER_DAYS = 7;
// kolory kwantyli ceny za m²: tani (zielony) → drogi (czerwony)
const QUANTILE_COLORS = ['#15803d', '#84cc16', '#eab308', '#f97316', '#dc2626'];
const INACTIVE_COLOR = '#9ca3af';

let map, markersLayer;
let allOffers = [];
let quantiles = [];
let typeFilterState = {}; // plot_type -> bool

init();

async function init() {
    map = L.map('map').setView(LUBLIN_CENTER, 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap', maxZoom: 19,
    }).addTo(map);
    markersLayer = L.layerGroup().addTo(map);

    let data;
    try {
        const resp = await fetch('data.json?t=' + Date.now());
        data = await resp.json();
    } catch (e) {
        document.getElementById('visible-count').textContent = 'błąd danych';
        return;
    }

    allOffers = data.offers || [];
    quantiles = (data.stats && data.stats.per_m2_quantiles || []).filter(q => q != null);

    if (data.last_scan) {
        document.getElementById('last-scan').textContent =
            new Date(data.last_scan).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' });
    }
    const med = data.stats && data.stats.median_price_per_m2;
    document.getElementById('median-per-m2').textContent = med ? fmtPrice(med) + '/m²' : '—';

    buildTypeFilters();
    buildLegend();
    bindFilterEvents();
    render();
}

function fmtPrice(v) {
    if (v == null) return '—';
    return Math.round(v).toLocaleString('pl-PL') + ' zł';
}

function fmtArea(v) {
    if (v == null) return '—';
    return v.toLocaleString('pl-PL') + ' m²';
}

function isNew(offer) {
    if (!offer.first_seen) return false;
    return (Date.now() - new Date(offer.first_seen).getTime()) < NEW_OFFER_DAYS * 86400000;
}

function colorFor(offer) {
    if (!offer.active) return INACTIVE_COLOR;
    const v = offer.price_per_m2;
    if (v == null || !quantiles.length) return QUANTILE_COLORS[2];
    let i = 0;
    while (i < quantiles.length && v > quantiles[i]) i++;
    return QUANTILE_COLORS[i];
}

function buildTypeFilters() {
    const types = {};
    allOffers.forEach(o => { const t = o.plot_type || 'inna'; types[t] = (types[t] || 0) + 1; });
    const container = document.getElementById('type-filters');
    Object.keys(types).sort().forEach(t => {
        typeFilterState[t] = true;
        const label = document.createElement('label');
        label.innerHTML = `<input type="checkbox" checked data-type="${t}"> ${t} <span class="count">(${types[t]})</span>`;
        label.querySelector('input').addEventListener('change', e => {
            typeFilterState[t] = e.target.checked;
            render();
        });
        container.appendChild(label);
    });
}

function buildLegend() {
    const container = document.getElementById('legend');
    if (!quantiles.length) { container.textContent = 'brak danych'; return; }
    const bounds = [null, ...quantiles, null];
    for (let i = 0; i < QUANTILE_COLORS.length; i++) {
        const lo = bounds[i], hi = bounds[i + 1];
        let text;
        if (lo == null) text = `do ${fmtPrice(hi)}/m²`;
        else if (hi == null) text = `powyżej ${fmtPrice(lo)}/m²`;
        else text = `${fmtPrice(lo)} – ${fmtPrice(hi)}/m²`;
        const row = document.createElement('div');
        row.className = 'legend-row';
        row.innerHTML = `<span class="legend-dot" style="background:${QUANTILE_COLORS[i]}"></span> ${text}`;
        container.appendChild(row);
    }
}

function bindFilterEvents() {
    ['src-olx', 'src-otodom', 'layer-active', 'layer-inactive', 'only-new', 'only-private']
        .forEach(id => document.getElementById(id).addEventListener('change', render));
    ['price-min', 'price-max', 'area-min', 'area-max']
        .forEach(id => document.getElementById(id).addEventListener('input', debounce(render, 300)));
}

function debounce(fn, ms) {
    let t;
    return () => { clearTimeout(t); t = setTimeout(fn, ms); };
}

function passesFilters(o) {
    const srcOlx = document.getElementById('src-olx').checked;
    const srcOtodom = document.getElementById('src-otodom').checked;
    if (o.source === 'olx' && !srcOlx) return false;
    if (o.source === 'otodom' && !srcOtodom) return false;

    const showActive = document.getElementById('layer-active').checked;
    const showInactive = document.getElementById('layer-inactive').checked;
    if (o.active && !showActive) return false;
    if (!o.active && !showInactive) return false;

    if (document.getElementById('only-new').checked && !isNew(o)) return false;
    if (document.getElementById('only-private').checked && !o.is_private_owner) return false;

    if (!typeFilterState[o.plot_type || 'inna']) return false;

    const pMin = parseFloat(document.getElementById('price-min').value);
    const pMax = parseFloat(document.getElementById('price-max').value);
    if (!isNaN(pMin) && (o.price == null || o.price < pMin)) return false;
    if (!isNaN(pMax) && (o.price == null || o.price > pMax)) return false;

    const aMin = parseFloat(document.getElementById('area-min').value);
    const aMax = parseFloat(document.getElementById('area-max').value);
    if (!isNaN(aMin) && (o.area_m2 == null || o.area_m2 < aMin)) return false;
    if (!isNaN(aMax) && (o.area_m2 == null || o.area_m2 > aMax)) return false;

    return true;
}

function popupHtml(o) {
    const newBadge = isNew(o) ? ' <span class="badge-new">NOWA</span>' : '';
    const trend = o.price_trend === 'down'
        ? ` <span class="trend-down">↓ było ${fmtPrice(o.previous_price)}</span>`
        : o.price_trend === 'up'
            ? ` <span class="trend-up">↑ było ${fmtPrice(o.previous_price)}</span>` : '';
    const img = o.image ? `<img class="popup-img" src="${o.image}" loading="lazy" alt="">` : '';
    const where = [o.street, o.district].filter(Boolean).join(', ');
    const precision = o.coords_precision === 'approx' ? ' (lokalizacja przybliżona)' : '';
    const alsoAt = o.also_at
        ? `<a class="secondary" href="${o.also_at}" target="_blank" rel="noopener">Druga oferta ↗</a>` : '';
    const status = o.active ? '' : '<div style="color:#dc2626;font-weight:700;font-size:12px;">⏸ OFERTA NIEAKTYWNA</div>';
    return `
        ${img}${status}
        <div class="popup-title">${escapeHtml(o.title)}${newBadge}</div>
        <div class="popup-price">${fmtPrice(o.price)}${trend}</div>
        <div class="popup-meta">
            📐 ${fmtArea(o.area_m2)} • ${o.price_per_m2 ? fmtPrice(o.price_per_m2) + '/m²' : '—'}<br>
            🏷️ ${o.plot_type || 'inna'} • ${o.source.toUpperCase()}${o.is_private_owner ? ' • od właściciela' : ''}<br>
            ${where ? '📍 ' + escapeHtml(where) + precision + '<br>' : ''}
            🗓️ w bazie od ${o.first_seen ? new Date(o.first_seen).toLocaleDateString('pl-PL') : '—'} (${o.days_active} dni)
        </div>
        <div class="popup-desc">${escapeHtml(o.description || '')}</div>
        <div class="popup-links">
            <a href="${o.url}" target="_blank" rel="noopener">Zobacz ogłoszenie ↗</a>${alsoAt}
        </div>`;
}

function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function render() {
    markersLayer.clearLayers();
    const visible = allOffers.filter(passesFilters);
    const located = visible.filter(o => o.coords);

    located.forEach(o => {
        const exact = o.coords_precision === 'exact';
        const marker = L.circleMarker([o.coords.lat, o.coords.lon], {
            radius: exact ? 9 : 11,
            color: colorFor(o),
            weight: exact ? 1.5 : 3,
            fillColor: colorFor(o),
            fillOpacity: exact ? 0.85 : 0.25,
            opacity: o.active ? 1 : 0.6,
        });
        marker.bindPopup(popupHtml(o), { maxWidth: 320 });
        markersLayer.addLayer(marker);
    });

    renderStats(visible);
    renderUnlocalised(visible.filter(o => !o.coords));
    renderCounts();
}

function renderStats(visible) {
    document.getElementById('visible-count').textContent = visible.length;
    const prices = visible.map(o => o.price).filter(p => p != null);
    document.getElementById('min-price').textContent = prices.length ? fmtPrice(Math.min(...prices)) : '—';
    document.getElementById('max-price').textContent = prices.length ? fmtPrice(Math.max(...prices)) : '—';
}

function renderCounts() {
    const c = (pred) => allOffers.filter(pred).length;
    document.getElementById('count-olx').textContent = `(${c(o => o.source === 'olx')})`;
    document.getElementById('count-otodom').textContent = `(${c(o => o.source === 'otodom')})`;
    document.getElementById('count-active').textContent = `(${c(o => o.active)})`;
    document.getElementById('count-inactive').textContent = `(${c(o => !o.active)})`;
    document.getElementById('count-new').textContent = `(${c(o => o.active && isNew(o))})`;
    document.getElementById('count-private').textContent = `(${c(o => o.active && o.is_private_owner)})`;
}

function renderUnlocalised(offers) {
    const bar = document.getElementById('unlocalised-bar');
    const grid = document.getElementById('unlocalised-grid');
    document.getElementById('unlocalised-count').textContent = offers.length;
    bar.style.display = offers.length ? 'block' : 'none';
    if (!offers.length) document.getElementById('unlocalised-section').style.display = 'none';

    grid.innerHTML = offers.map(o => `
        <div class="unloc-card">
            <a href="${o.url}" target="_blank" rel="noopener">${escapeHtml(o.title)}</a><br>
            ${fmtPrice(o.price)} • ${fmtArea(o.area_m2)} • ${o.plot_type || 'inna'} • ${o.source.toUpperCase()}
            ${o.district ? '<br>📍 ' + escapeHtml(o.district) : ''}
        </div>`).join('');
}

function toggleUnlocalised() {
    const sec = document.getElementById('unlocalised-section');
    sec.style.display = sec.style.display === 'none' ? 'block' : 'none';
}
