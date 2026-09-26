"""
ETL Scraper module for Dapamozhnik (helper.archonline.by).
Features:
- Recursive alphabet search to bypass the 12-result limit
- Support for proxies (Belarusian IP support)
- Checkpointing and deduplication in SQLite
- MessagePack and JSON response parsing
"""
import time
import json
import logging
import argparse
from typing import List, Dict, Any, Optional
import requests
import msgpack
from db import get_db_connection, slugify

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BELARUSIAN_ALPHABET = [
    "А", "Б", "В", "Г", "Д", "Е", "Ё", "Ж", "З", "І", "Й", "К", "Л", "М",
    "Н", "О", "П", "Р", "С", "Т", "У", "Ў", "Ф", "Х", "Ц", "Ч", "Ш", "Ы",
    "Э", "Ю", "Я"
]

class DapamozhnikScraper:
    def __init__(self, base_url: str = "https://helper.archonline.by", proxy: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "be,ru;q=0.9,en;q=0.8"
        })
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
            logging.info(f"Using proxy: {proxy}")

    def search(self, query: str, mode: str = "settlements") -> List[Dict[str, Any]]:
        """
        Query helper backend for settlements or surnames.
        mode: 'settlements' or 'surnames'
        """
        endpoint = f"{self.base_url}/search"
        payload = {"q": query, "mode": mode}
        try:
            resp = self.session.post(endpoint, data=payload, timeout=12)
            if resp.status_code == 200:
                # Try msgpack first, then json
                try:
                    return msgpack.unpackb(resp.content, raw=False)
                except Exception:
                    return resp.json()
            elif resp.status_code == 403:
                logging.warning(f"403 Forbidden received. Server requires Belarus IP / proxy.")
                return []
            else:
                logging.warning(f"HTTP {resp.status_code} for query '{query}'")
                return []
        except Exception as e:
            logging.error(f"Network error querying '{query}': {e}")
            return []

    def recursive_crawl(self, prefix: str = "", max_depth: int = 3, mode: str = "settlements"):
        """
        Recursively queries the API. If 12 results are returned (limit hit),
        it appends the next letter to search deeper and gather all items.
        """
        letters = BELARUSIAN_ALPHABET if not prefix else [prefix + l for l in BELARUSIAN_ALPHABET]
        for query in letters:
            logging.info(f"Querying: '{query}' (mode={mode})")
            results = self.search(query, mode=mode)
            logging.info(f"Found {len(results)} results for '{query}'")

            for item in results:
                self.save_item(item, mode=mode)

            # If results count is 12 (or limit reached) and we haven't exceeded depth, drill down
            if len(results) >= 12 and len(query) < max_depth:
                logging.info(f"Hit 12-result ceiling on '{query}'. Drilling deeper...")
                self.recursive_crawl(prefix=query, max_depth=max_depth, mode=mode)
            
            time.sleep(0.2) # Polite rate-limiting

    def save_item(self, item: Dict[str, Any], mode: str = "settlements"):
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if mode == "settlements":
                name_be = item.get("name_be") or item.get("name", "")
                district = item.get("district", "")
                slug = slugify(f"{name_be}-{district}")
                cur.execute("""
                INSERT OR IGNORE INTO settlements (
                    slug, name_be, name_ru, settlement_type, district, selsoviet,
                    gubernia, uezd, volost, parish_orthodox, parish_catholic,
                    estate, lat, lon
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    slug, name_be, item.get("name_ru", ""), item.get("type", ""),
                    district, item.get("selsoviet", ""), item.get("gubernia", ""),
                    item.get("uezd", ""), item.get("volost", ""), item.get("parish_orthodox", ""),
                    item.get("parish_catholic", ""), item.get("estate", ""),
                    item.get("lat"), item.get("lon")
                ))
            elif mode == "surnames":
                surname_be = item.get("surname", "")
                slug = slugify(surname_be)
                cur.execute("""
                INSERT OR IGNORE INTO surnames (slug, surname_be, normalized)
                VALUES (?, ?, ?)
                """, (slug, surname_be, surname_be.lower()))
            conn.commit()
        except Exception as e:
            logging.error(f"DB insert error: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dapamozhnik Scraper")
    parser.add_argument("--proxy", help="HTTP/SOCKS proxy (e.g. http://proxy.belarus:8080)")
    parser.add_argument("--mode", choices=["settlements", "surnames"], default="settlements")
    parser.add_argument("--max-depth", type=int, default=3)
    args = parser.parse_args()

    scraper = DapamozhnikScraper(proxy=args.proxy)
    logging.info(f"Starting scraper in '{args.mode}' mode with max_depth={args.max_depth}")
    scraper.recursive_crawl(mode=args.mode, max_depth=args.max_depth)
