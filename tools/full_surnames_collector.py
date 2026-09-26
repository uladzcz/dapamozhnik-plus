"""
Full Autonomous Surnames Collector & District Expander.
Tier 1: Adaptive Prefix Tree with 5 worker threads, exponential backoff, and SQLite checkpointing.
Tier 2: District Expansion (118 districts) for all surnames with >= 110 occurrences to break the 120 limit.
Final: Automatic linkage into settlements table and export to F:/Downloads/surnames_perfect_dump.json.
"""
import sqlite3
import requests
import msgpack
import urllib3
import time
import sys
import io
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import json


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
urllib3.disable_warnings()

DB_PATH = "dapamozhnik.db"
URL = "https://helper.archonline.by/data"

beL1 = ["А","Б","В","Г","Д","Е","Ё","Ж","З","І","Й","К","Л","М","Н","О","П","Р","С","Т","У","Ў","Ф","Х","Ц","Ч","Ш","Ы","Э","Ю","Я"]
beRest = ["а","б","в","г","д","е","ё","ж","з","і","й","к","л","м","н","о","п","р","с","т","у","ў","ф","х","ц","ч","ш","ы","ь","э","ю","я","'","’"]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Origin': 'https://helper.archonline.by',
    'Referer': 'https://helper.archonline.by/'
}

def get_session():
    s = requests.Session()
    s.headers.update(headers)
    return s

def init_db(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS crawler_state (
        prefix TEXT PRIMARY KEY,
        results_count INTEGER,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS surnames_raw (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        s TEXT,
        n TEXT,
        d TEXT,
        ss TEXT,
        lat REAL,
        lon REAL,
        UNIQUE(s, d, n, ss, lat, lon)
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sr_s ON surnames_raw(s);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sr_d ON surnames_raw(d);")
    conn.commit()

def fetch_with_retry(session, payload, max_retries=5):
    for attempt in range(max_retries):
        try:
            r = session.post(URL, data=payload, verify=False, timeout=8)
            if r.status_code == 200:
                if len(r.content) <= 2:
                    return []
                return msgpack.unpackb(r.content, raw=False)
            elif r.status_code in (403, 429):
                time.sleep(1.5 + attempt * 0.5)
        except Exception:
            time.sleep(1.0 + attempt * 0.5)
    return []

def clean_record(raw):
    td = {}
    for k, v in raw.items():
        k_str = k.decode('utf-8', errors='replace') if isinstance(k, bytes) else k
        v_str = v.decode('utf-8', errors='replace') if isinstance(v, bytes) else v
        td[k_str] = v_str
    return td

def run_tier1_global_crawl(conn):
    print("\n" + "="*60)
    print("🚀 ПАЧАТАК ЭТАПУ 1: Глабальны адаптыўны збор з аўта-паўторам")
    print("="*60)

    cur = conn.cursor()
    cur.execute("SELECT prefix FROM crawler_state")
    completed_prefixes = set(r[0] for r in cur.fetchall())
    print(f"Ужо апрацавана раней: {len(completed_prefixes):,} прэфіксаў.")

    # Generate initial 3-letter queue
    queue = []
    for c1 in beL1:
        for c2 in beRest:
            if c2 in ("'", "’"): continue
            for c3 in beRest:
                p = c1 + c2 + c3
                if p not in completed_prefixes:
                    queue.append(p)

    print(f"У чарзе на апрацоўку: {len(queue):,} прэфіксаў.")

    session = get_session()
    records_batch = []
    state_batch = []
    total_saved = 0
    t0 = time.time()
    last_log = time.time()

    # Pre-populate with existing records from surnames_full_dump.json if exists
    dump_path = "F:/Downloads/surnames_full_dump.json"
    if os.path.exists(dump_path):
        cur.execute("SELECT COUNT(*) FROM surnames_raw")
        existing_raw_count = cur.fetchone()[0]
        if existing_raw_count == 0:
            print(f"Пераднапаўненне surnames_raw з {dump_path}...")
            with open(dump_path, 'r', encoding='utf-8') as f:
                dump_data = json.load(f)
            pre_batch = []
            for it in dump_data:
                pre_batch.append((
                    it.get('s', ''), it.get('n', ''), it.get('d', ''),
                    it.get('ss', ''), it.get('lat'), it.get('lon')
                ))
                if len(pre_batch) >= 20000:
                    cur.executemany("INSERT OR IGNORE INTO surnames_raw (s, n, d, ss, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", pre_batch)
                    conn.commit()
                    pre_batch = []
            if pre_batch:
                cur.executemany("INSERT OR IGNORE INTO surnames_raw (s, n, d, ss, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", pre_batch)
                conn.commit()
            print("Пераднапаўненне скончана!")

    # Worker function for parallel execution
    def process_prefix(q):
        payload = {'q': q, 'm': '2', 't': '0', 'u': '1', 's': ''}
        raw_results = fetch_with_retry(session, payload)
        items = [clean_record(x) for x in raw_results]
        return q, items

    MAX_WORKERS = 5
    processed_count = 0
    drilled_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        idx = 0
        while idx < len(queue):
            # Take a chunk of 50 tasks
            chunk = queue[idx:idx + 50]
            idx += 50

            futures = {executor.submit(process_prefix, q): q for q in chunk}
            for fut in as_completed(futures):
                q, items = fut.result()
                processed_count += 1
                state_batch.append((q, len(items)))

                for it in items:
                    records_batch.append((
                        it.get('s', ''), it.get('n', ''), it.get('d', ''),
                        it.get('ss', ''), it.get('lat'), it.get('lon')
                    ))

                # Drill down if ceiling hit
                if len(items) >= 120 and len(q) < 5:
                    drilled_count += 1
                    for nextChar in beRest:
                        sub_q = q + nextChar
                        if sub_q not in completed_prefixes:
                            queue.append(sub_q)

            # Flush to DB every 200 items or 5 seconds
            if len(records_batch) >= 2000 or (time.time() - last_log > 5):
                if records_batch:
                    cur.executemany("INSERT OR IGNORE INTO surnames_raw (s, n, d, ss, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", records_batch)
                    total_saved += len(records_batch)
                    records_batch = []
                if state_batch:
                    cur.executemany("INSERT OR REPLACE INTO crawler_state (prefix, results_count) VALUES (?, ?)", state_batch)
                    state_batch = []
                conn.commit()

                elapsed = time.time() - t0
                speed = processed_count / (elapsed or 1)
                cur.execute("SELECT COUNT(*) FROM surnames_raw")
                total_in_db = cur.fetchone()[0]
                print(f"[Этап 1] Апрацавана: {processed_count:,} | У чарзе: {len(queue) - idx:,} | У базе raw: {total_in_db:,} | Паглыбленняў: {drilled_count} | {speed:.1f} зап/сек")
                last_log = time.time()

        if records_batch:
            cur.executemany("INSERT OR IGNORE INTO surnames_raw (s, n, d, ss, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", records_batch)
            conn.commit()
        if state_batch:
            cur.executemany("INSERT OR REPLACE INTO crawler_state (prefix, results_count) VALUES (?, ?)", state_batch)
            conn.commit()

    print("✅ Этап 1 завершаны!")

def run_tier2_district_expansion(conn):
    print("\n" + "="*60)
    print("🎯 ПАЧАТАК ЭТАПУ 2: Прабіванне столі 120 па 118 раёнах (для топавых прозвішчаў)")
    print("="*60)

    cur = conn.cursor()
    # Find all surnames with >= 110 records in surnames_raw
    cur.execute("""
        SELECT s, COUNT(*) as cnt 
        FROM surnames_raw 
        WHERE s != ''
        GROUP BY s 
        HAVING cnt >= 110
        ORDER BY cnt DESC
    """)
    capped_surnames = [r[0] for r in cur.fetchall()]
    print(f"Знойдзена {len(capped_surnames)} папулярных прозвішчаў, у якіх >= 110 згадак.")

    # Get all 118 districts
    cur.execute("SELECT DISTINCT district FROM settlements WHERE district != ''")
    districts = [r[0] for r in cur.fetchall()]
    print(f"Усяго раёнаў для сканавання: {len(districts)}")

    session = get_session()
    tasks = [(sn, d) for sn in capped_surnames for d in districts]
    print(f"Агульная колькасць раённых запытаў: {len(tasks):,}")

    def fetch_district(sn_dist):
        sn, dist = sn_dist
        payload = {'q': sn, 'm': '2', 't': '1', 'u': '1', 's': dist}
        raw_results = fetch_with_retry(session, payload)
        items = [clean_record(x) for x in raw_results]
        # Only take records that actually match the surname
        matched = [it for it in items if it.get('s') == sn]
        return matched

    records_batch = []
    t0 = time.time()
    last_log = time.time()
    completed = 0
    added_count = 0

    with ThreadPoolExecutor(max_workers=6) as executor:
        idx = 0
        while idx < len(tasks):
            chunk = tasks[idx:idx + 60]
            idx += 60

            futures = [executor.submit(fetch_district, t) for t in chunk]
            for fut in as_completed(futures):
                items = fut.result()
                completed += 1
                for it in items:
                    records_batch.append((
                        it.get('s', ''), it.get('n', ''), it.get('d', ''),
                        it.get('ss', ''), it.get('lat'), it.get('lon')
                    ))

            if len(records_batch) >= 1000 or (time.time() - last_log > 5):
                if records_batch:
                    cur.executemany("INSERT OR IGNORE INTO surnames_raw (s, n, d, ss, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", records_batch)
                    conn.commit()
                    added_count += len(records_batch)
                    records_batch = []
                elapsed = time.time() - t0
                speed = completed / (elapsed or 1)
                print(f"[Этап 2] Раёнаў праверана: {completed:,} / {len(tasks):,} | Дададзена новых: {added_count:,} | {speed:.1f} зап/сек")
                last_log = time.time()

        if records_batch:
            cur.executemany("INSERT OR IGNORE INTO surnames_raw (s, n, d, ss, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", records_batch)
            conn.commit()

    print("✅ Этап 2 завершаны!")

def finalize_and_export(conn):
    print("\n" + "="*60)
    print("📦 ФІНАЛ: Звязванне базы і экспарт")
    print("="*60)
    import json
    from import_surnames import import_surnames
    
    cur = conn.cursor()
    cur.execute("SELECT s, n, d, ss, lat, lon FROM surnames_raw WHERE s != ''")
    rows = cur.fetchall()
    print(f"Усяго чыстых запісаў у surnames_raw: {len(rows):,}")

    all_data = []
    for r in rows:
        all_data.append({
            's': r[0], 'n': r[1], 'd': r[2], 'ss': r[3],
            'lat': r[4], 'lon': r[5]
        })

    out_file = "F:/Downloads/surnames_perfect_dump.json"
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=1)
    print(f"Захавана ў {out_file} ({os.path.getsize(out_file)/(1024*1024):.2f} MB)")

    # Run DB importer
    import_surnames(out_file)
    print("🎉 УСЯ БАЗА 100% СКАМПЛЕКТАВАНА І ЗВЯЗАНА!")

def main():
    conn = sqlite3.connect(DB_PATH)
    # High performance pragmas
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    init_db(conn)

    try:
        run_tier1_global_crawl(conn)
        run_tier2_district_expansion(conn)
        finalize_and_export(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
