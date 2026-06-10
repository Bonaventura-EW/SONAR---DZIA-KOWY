/* Animowane logo SONARA DZIAŁKOWEGO — "skan działki".
 * Wstrzykiwane do elementów .sonar-logo, żeby nie duplikować SVG w każdej stronie. */

const SONAR_LOGO_SVG = `
<svg width="40" height="40" viewBox="0 0 64 64" aria-hidden="true">
  <defs>
    <radialGradient id="lgBg" cx="50%" cy="42%" r="62%">
      <stop offset="0%" stop-color="#0c3d22"/>
      <stop offset="100%" stop-color="#041b0e"/>
    </radialGradient>
    <linearGradient id="lgSweep" x1="50%" y1="50%" x2="100%" y2="50%">
      <stop offset="0%" stop-color="#a3e635" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="#a3e635" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="lgScan" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#a3e635" stop-opacity="0"/>
      <stop offset="50%" stop-color="#a3e635" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="#a3e635" stop-opacity="0"/>
    </linearGradient>
    <mask id="lgMask"><circle cx="32" cy="32" r="29" fill="white"/></mask>
    <mask id="lgPlotMask"><rect x="17" y="19" width="30" height="26" rx="2" fill="white"/></mask>
  </defs>

  <circle cx="32" cy="32" r="31" fill="url(#lgBg)"/>
  <circle cx="32" cy="32" r="29.5" fill="none" stroke="#a3e635" stroke-width="1" opacity="0.55"/>
  <circle cx="32" cy="32" r="22" fill="none" stroke="#a3e635" stroke-width="0.4" opacity="0.25"/>

  <!-- działka: parcela z przerywaną granicą i siatką geodezyjną -->
  <g mask="url(#lgMask)">
    <rect x="17" y="19" width="30" height="26" rx="2" fill="#a3e635" opacity="0.10"/>
    <rect x="17" y="19" width="30" height="26" rx="2" fill="none"
          stroke="#a3e635" stroke-width="1.7" stroke-dasharray="5 3.5">
      <animate attributeName="stroke-dashoffset" from="0" to="-17" dur="2.6s" repeatCount="indefinite"/>
    </rect>
    <path d="M27 19 V45 M37 19 V45 M17 28 H47 M17 37 H47"
          stroke="#a3e635" stroke-width="0.5" opacity="0.30"/>

    <!-- paliki geodezyjne w narożnikach -->
    <g fill="#d9f99d">
      <circle cx="17" cy="19" r="2.1"/><circle cx="47" cy="19" r="2.1"/>
      <circle cx="17" cy="45" r="2.1"/><circle cx="47" cy="45" r="2.1"/>
    </g>

    <!-- pozioma linia skanu przesuwająca się po działce -->
    <g mask="url(#lgPlotMask)">
      <rect x="17" y="0" width="30" height="9" fill="url(#lgScan)">
        <animate attributeName="y" values="13;42;13" dur="3.2s" repeatCount="indefinite"/>
      </rect>
    </g>

    <!-- namierzone punkty -->
    <circle cx="25" cy="33" r="1.8" fill="#ecfccb">
      <animate attributeName="opacity" values="1;0.15;1" dur="1.6s" repeatCount="indefinite"/>
    </circle>
    <circle cx="41" cy="25" r="1.8" fill="#ecfccb">
      <animate attributeName="opacity" values="0.15;1;0.15" dur="1.6s" repeatCount="indefinite"/>
    </circle>
  </g>

  <!-- obrotowy snop radaru -->
  <g mask="url(#lgMask)" opacity="0.55">
    <path d="M32,32 L32,3 A29,29 0 0,1 61,32 Z" fill="url(#lgSweep)">
      <animateTransform attributeName="transform" type="rotate" from="0 32 32" to="360 32 32" dur="4s" repeatCount="indefinite"/>
    </path>
  </g>
</svg>`;

document.querySelectorAll('.sonar-logo').forEach(el => { el.innerHTML = SONAR_LOGO_SVG; });
