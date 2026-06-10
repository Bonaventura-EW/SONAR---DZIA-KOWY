"""SONAR DZIAŁKOWY — główny agent.

Koordynuje: scraping (OLX + Otodom) → normalizacja → aktualizacja bazy →
dezaktywacja zniknietych ofert → zapis. Wzorowany na SONAR-MIESZKANIOWY,
ale bez parsera adresów i geokodera — oba portale dają współrzędne w JSON.
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import pytz

import paths
from olx_scraper import OLXDzialkiScraper
from otodom_scraper import OtodomDzialkiScraper

# Maksymalna wiarygodna zmiana ceny między skanami (ochrona przed błędami parsowania)
MAX_PRICE_CHANGE_PERCENT = 70
# Ochrona przed masową dezaktywacją: scraper źródła musi zwrócić >= 30%
# wcześniejszej liczby aktywnych ofert tego źródła, inaczej pomijamy dezaktywację
MIN_SCRAPE_RATIO = 0.3


class SonarDzialkowy:
    def __init__(self, data_file: str = paths.OFFERS_JSON,
                 removed_file: str = paths.REMOVED_JSON):
        self.data_file = Path(data_file)
        self.removed_file = Path(removed_file)
        self.tz = pytz.timezone('Europe/Warsaw')
        self.database = self._load_json(self.data_file) or {
            'last_scan': None, 'next_scan': None, 'offers': []
        }
        removed = self._load_json(self.removed_file) or {}
        self.removed_ids = set(removed.get('removed_ids', []))

    @staticmethod
    def _load_json(path: Path):
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"⚠️ Uszkodzony plik {path}, pomijam")
            return None

    def _save_database(self):
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.database, f, ensure_ascii=False, indent=1)
        print(f"💾 Baza zapisana: {self.data_file}")

    def _known_otodom_offers(self) -> Dict:
        """Indeks znanych ofert Otodom — pozwala scraperowi pominąć strony szczegółów."""
        known = {}
        for offer in self.database['offers']:
            if offer.get('source') != 'otodom':
                continue
            loc = offer.get('location') or {}
            if loc.get('coords'):
                known[offer['id']] = {
                    'coords': loc['coords'],
                    'coords_precision': loc.get('coords_precision'),
                    'plot_type': offer.get('plot_type'),
                    'description': offer.get('description'),
                }
        return known

    def _find_existing(self, offer_id: str):
        for offer in self.database['offers']:
            if offer['id'] == offer_id:
                return offer
        return None

    def _update_existing(self, existing: Dict, new: Dict):
        now = datetime.now(self.tz).isoformat()
        existing['last_seen'] = now

        # slug/URL mógł się zmienić (sprzedawca edytował tytuł) — odśwież
        existing['url'] = new['url']
        existing['title'] = new['title'] or existing.get('title')

        old_price = existing['price']['current']
        new_price = new['price']
        if new_price and new_price != old_price:
            change_pct = abs(new_price - old_price) / old_price * 100
            if change_pct <= MAX_PRICE_CHANGE_PERCENT:
                trend = 'down' if new_price < old_price else 'up'
                arrow = '📉' if trend == 'down' else '📈'
                print(f"   {arrow} Zmiana ceny {existing['id']}: "
                      f"{old_price} → {new_price} zł")
                existing['price']['previous_price'] = old_price
                existing['price']['current'] = new_price
                existing['price']['price_trend'] = trend
                existing['price']['price_changed_at'] = now
                existing['price']['history'].append(new_price)
                existing['price'].setdefault('price_changes', []).append({
                    'old_price': old_price, 'new_price': new_price,
                    'changed_at': now, 'trend': trend,
                })
            else:
                print(f"   ⚠️ PODEJRZANA zmiana ceny {existing['id']}: "
                      f"{old_price} → {new_price} zł ({change_pct:.0f}%) — ignoruję")

        # uzupełnij/odśwież pola merytoryczne (nowy skan = świeższe dane)
        if new.get('area_m2'):
            existing['area_m2'] = new['area_m2']
        if existing.get('area_m2') and existing['price']['current']:
            existing['price_per_m2'] = round(
                existing['price']['current'] / existing['area_m2'], 2)
        if new.get('plot_type'):
            existing['plot_type'] = new['plot_type']
        if new.get('description') and len(new['description']) >= len(existing.get('description') or ''):
            existing['description'] = new['description']
        if new.get('image'):
            existing['image'] = new['image']

        # coords: nie nadpisuj dokładnych przybliżonymi
        new_loc = new.get('location') or {}
        old_loc = existing.setdefault('location', {})
        if new_loc.get('coords'):
            if not old_loc.get('coords') or old_loc.get('coords_precision') != 'exact' \
               or new_loc.get('coords_precision') == 'exact':
                old_loc['coords'] = new_loc['coords']
                old_loc['coords_precision'] = new_loc.get('coords_precision')
        for key in ('city', 'district', 'street'):
            if new_loc.get(key):
                old_loc[key] = new_loc[key]

        if not existing.get('active', True):
            existing['active'] = True
            existing['reactivated_at'] = now
            print(f"   🔄 REAKTYWOWANO: {existing['id']}")

    def _add_new(self, new: Dict):
        now = datetime.now(self.tz).isoformat()
        price = new.pop('price')
        new['price'] = {
            'current': price,
            'history': [price],
        }
        new['first_seen'] = now
        new['last_seen'] = now
        new['active'] = True
        new['days_active'] = 0
        self.database['offers'].append(new)

    def _mark_inactive(self, scraped_by_source: Dict[str, List[Dict]]):
        """Dezaktywuje oferty nieobecne w skanie — per źródło, z ochroną
        przed masową dezaktywacją przy blokadzie portalu."""
        now = datetime.now(self.tz).isoformat()
        for source, scraped in scraped_by_source.items():
            scraped_ids = {o['id'] for o in scraped}
            active_in_db = [o for o in self.database['offers']
                            if o.get('source') == source and o.get('active')]

            if not active_in_db:
                continue
            if len(scraped) == 0:
                print(f"   ⚠️ OCHRONA [{source}]: scraper zwrócił 0 ofert, "
                      f"baza ma {len(active_in_db)} aktywnych — pomijam dezaktywację")
                continue
            if len(active_in_db) >= 10 and len(scraped) < len(active_in_db) * MIN_SCRAPE_RATIO:
                print(f"   ⚠️ OCHRONA [{source}]: tylko {len(scraped)} ofert ze skanu "
                      f"vs {len(active_in_db)} aktywnych — pomijam dezaktywację")
                continue

            deactivated = 0
            for offer in active_in_db:
                if offer['id'] not in scraped_ids:
                    offer['active'] = False
                    offer['deactivated_at'] = now
                    deactivated += 1
            if deactivated:
                print(f"   ⏸️ [{source}] dezaktywowano: {deactivated}")

    def _update_days_active(self):
        for offer in self.database['offers']:
            try:
                first = datetime.fromisoformat(offer['first_seen'])
                last = datetime.fromisoformat(offer['last_seen'])
                offer['days_active'] = (last - first).days
            except (ValueError, KeyError):
                offer['days_active'] = 0

    def _tag_cross_portal_duplicates(self):
        """Ta sama działka wystawiona na OLX i Otodom: identyczna cena
        i powierzchnia (±1%) → linkujemy oferty polem `also_at`."""
        active = [o for o in self.database['offers'] if o.get('active')]
        olx = [o for o in active if o['source'] == 'olx' and o.get('area_m2')]
        otodom = [o for o in active if o['source'] == 'otodom' and o.get('area_m2')]
        tagged = 0
        for a in olx:
            for b in otodom:
                if a['price']['current'] == b['price']['current'] and \
                   abs(a['area_m2'] - b['area_m2']) <= 0.01 * max(a['area_m2'], b['area_m2']):
                    a['also_at'] = b['url']
                    b['also_at'] = a['url']
                    tagged += 1
                    break
        if tagged:
            print(f"   🔗 Powiązano {tagged} par ofert OLX↔Otodom (ta sama działka)")

    def _cleanup_old(self, max_age_days: int = 548):
        cutoff = datetime.now(self.tz) - timedelta(days=max_age_days)
        before = len(self.database['offers'])
        self.database['offers'] = [
            o for o in self.database['offers']
            if datetime.fromisoformat(o['first_seen']) > cutoff
        ]
        removed = before - len(self.database['offers'])
        if removed:
            print(f"🗑️ Usunięto {removed} ofert starszych niż {max_age_days} dni")

    def _next_scan_time(self) -> str:
        now = datetime.now(self.tz)
        for hour in (8, 14, 20):
            candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if candidate > now:
                return candidate.isoformat()
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=8, minute=0, second=0, microsecond=0).isoformat()

    def _log_scan(self, stats: Dict):
        """Dopisuje wpis do data/scan_history.json (ostatnie 200 skanów)."""
        history_path = Path(paths.SCAN_HISTORY_JSON)
        history = self._load_json(history_path) or {'scans': []}
        history['scans'].append(stats)
        history['scans'] = history['scans'][-200:]
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=1)

    def run_scan(self, max_pages: int = 10):
        print("\n" + "=" * 60)
        print("🎯 SONAR DZIAŁKOWY — Scan Started")
        print("=" * 60 + "\n")
        start = time.time()
        now = datetime.now(self.tz)

        # 1. Scraping obu źródeł (awaria jednego nie blokuje drugiego)
        scraped_by_source: Dict[str, List[Dict]] = {}
        try:
            scraped_by_source['olx'] = OLXDzialkiScraper().scrape(max_pages=max_pages)
        except Exception as e:
            print(f"❌ OLX: scraping nieudany: {e}")
            scraped_by_source['olx'] = []
        try:
            scraped_by_source['otodom'] = OtodomDzialkiScraper().scrape(
                max_pages=max_pages, known_offers=self._known_otodom_offers())
        except Exception as e:
            print(f"❌ Otodom: scraping nieudany: {e}")
            scraped_by_source['otodom'] = []

        # 2. Aktualizacja bazy
        print("💾 Aktualizacja bazy danych...")
        new_count, updated_count, skipped_removed = 0, 0, 0
        for source, scraped in scraped_by_source.items():
            for offer in scraped:
                if offer['id'] in self.removed_ids:
                    skipped_removed += 1
                    continue
                existing = self._find_existing(offer['id'])
                if existing:
                    self._update_existing(existing, offer)
                    updated_count += 1
                else:
                    price = offer['price']
                    self._add_new(dict(offer))
                    new_count += 1
                    print(f"   🆕 [{source}] {offer['title'][:60]} — {price} zł")

        # 3. Dezaktywacja + porządki
        self._mark_inactive(scraped_by_source)
        self._update_days_active()
        self._tag_cross_portal_duplicates()
        self._cleanup_old()

        # 4. Metadane + zapis
        self.database['last_scan'] = now.isoformat()
        self.database['next_scan'] = self._next_scan_time()
        self._save_database()

        # 5. Statystyki
        active = sum(1 for o in self.database['offers'] if o.get('active'))
        with_coords = sum(1 for o in self.database['offers']
                          if o.get('active') and (o.get('location') or {}).get('coords'))
        duration = time.time() - start
        self._log_scan({
            'timestamp': now.isoformat(),
            'duration_s': round(duration, 1),
            'scraped_olx': len(scraped_by_source['olx']),
            'scraped_otodom': len(scraped_by_source['otodom']),
            'new': new_count,
            'updated': updated_count,
            'skipped_removed': skipped_removed,
            'active': active,
            'total_in_db': len(self.database['offers']),
        })

        print("\n" + "=" * 60)
        print("📊 PODSUMOWANIE SCANU")
        print("=" * 60)
        print(f"✅ Aktywne oferty: {active} (z GPS: {with_coords})")
        print(f"🆕 Nowe: {new_count} | 🔄 Zaktualizowane: {updated_count}")
        print(f"📦 Łącznie w bazie: {len(self.database['offers'])}")
        print(f"⏱️ Czas: {duration:.1f}s")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    SonarDzialkowy().run_scan()
