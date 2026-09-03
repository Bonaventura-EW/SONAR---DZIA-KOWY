"""Ścieżki do katalogów projektu, liczone względem lokalizacji tego pliku.

Konwencja przeniesiona z SONAR-MIESZKANIOWY: kotwiczymy ścieżki do __file__,
dzięki czemu skrypty znajdują dane niezależnie od bieżącego katalogu
(np. odpalane z roota repo albo przez pytest).
"""

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent
DATA_DIR = ROOT_DIR / "data"
DOCS_DIR = ROOT_DIR / "docs"

OFFERS_JSON = str(DATA_DIR / "offers.json")
REMOVED_JSON = str(DATA_DIR / "removed_listings.json")
SCAN_HISTORY_JSON = str(DATA_DIR / "scan_history.json")
# dzienny mierzony stan bazy (Indeks podaży) — rośnie bezterminowo,
# w przeciwieństwie do scan_history.json przycinanego do 200 skanów
INDEX_HISTORY_JSON = str(DATA_DIR / "index_history.json")

DOCS_DATA_JSON = str(DOCS_DIR / "data.json")
DOCS_TREND_JSON = str(DOCS_DIR / "trend_data.json")
