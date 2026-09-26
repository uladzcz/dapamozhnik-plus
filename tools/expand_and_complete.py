"""
expand_and_complete.py
Phase 1: Deep prefix expansion on 5- and 6-letter prefixes hitting 120 limit (finds Каралёў and all siblings).
Phase 2: District expansion (118 districts) for all capped surnames (>= 110 occurrences) to break the 120 limit.
Phase 3: Populate `surnames` and `settlement_surnames` tables, export `surnames_perfect_dump.json`.
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

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
urllib3.disable_warnings()

DB_PATH = "dapamozhnik.db"
URL = "https://helper.archonline.by/data"

beRest = ["а","б","в","г","д","е","ё","ж","з","і","й","к","л","м","н","о","п","р","с","т","у","ў","ф","х","ц","ч","ш","ы","ь","э","ю","я"]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Origin': 'https://helper.archonline.by',
    'Referer': 'https://helper.archonline.by/'
}

def get_session():
    s = requests.Session()
    s.headers.update(headers)
    return s

def clean_record(raw):
    td = {}
    for k, v in raw.items():
        k_str = k.decode('utf-8', errors='replace') if isinstance(k, bytes) else k
        v_str = v.decode('utf-8', errors='replace') if isinstance(v, bytes) else v
        td[k_str] = v_str
    return td

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

def run_phase1_deep_expansion(conn):
    print("\n" + "="*60)
    print("🚀 ФАЗА 1: Глыбокае паглыбленне на 6 і 7 літар для каранёў са столлю 120")
    print("="*60)

    cur = conn.cursor()
    # Find all 5-letter prefixes with results_count >= 120
    cur.execute("SELECT prefix FROM crawler_state WHERE length(prefix) = 5 AND results_count >= 120")
    p5_list = [r[0] for r in cur.fetchall()]
    print(f"Знойдзена {len(p5_list)} 5-літарных каранёў з лімітам 120.")

    # Check which 6-letter prefixes already exist in crawler_state
    cur.execute("SELECT prefix FROM crawler_state WHERE length(prefix) >= 6")
    already_done = set(r[0] for r in cur.fetchall())
    print(f"Ужо апрацавана 6-літарных раней: {len(already_done)}")

    queue = []
    for p in p5_list:
        for c in beRest:
            sub = p + c
            if sub not in already_done:
                queue.append(sub)

    print(f"У чарзе на паглыбленне: {len(queue):,} 6-літарных прэфіксаў.")

    session = get_session()
    records_batch = []
    state_batch = []
    processed = 0
    t0 = time.time()
    last_log = time.time()

    def worker(q):
        payload = {'q': q, 'm': '2', 't': '0', 'u': '1', 's': ''}
        raw = fetch_with_retry(session, payload)
        items = [clean_record(x) for x in raw]
        return q, items

    with ThreadPoolExecutor(max_workers=6) as executor:
        idx = 0
        while idx < len(queue):
            chunk = queue[idx:idx + 60]
            idx += 60

            futures = [executor.submit(worker, q) for q in chunk]
            for fut in as_completed(futures):
                q, items = fut.result()
                processed += 1
                state_batch.append((q, len(items)))

                for it in items:
                    records_batch.append((
                        it.get('s', ''), it.get('n', ''), it.get('d', ''),
                        it.get('ss', ''), it.get('lat'), it.get('lon')
                    ))

                # If a 6-letter prefix ALSO hits 120 and len < 7, drill down to 7 letters!
                if len(items) >= 120 and len(q) < 7:
                    for nextChar in beRest:
                        sub_sub = q + nextChar
                        if sub_sub not in already_done:
                            queue.append(sub_sub)

            if len(records_batch) >= 1000 or (time.time() - last_log > 5):
                if records_batch:
                    cur.executemany("INSERT OR IGNORE INTO surnames_raw (s, n, d, ss, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", records_batch)
                    records_batch = []
                if state_batch:
                    cur.executemany("INSERT OR REPLACE INTO crawler_state (prefix, results_count) VALUES (?, ?)", state_batch)
                    state_batch = []
                conn.commit()
                elapsed = time.time() - t0
                speed = processed / (elapsed or 1)
                cur.execute("SELECT count(*) FROM surnames_raw")
                total_raw = cur.fetchone()[0]
                print(f"[Фаза 1] Праверана: {processed:,} / {len(queue):,} | У базе: {total_raw:,} | {speed:.1f} зап/сек")
                last_log = time.time()

        if records_batch:
            cur.executemany("INSERT OR IGNORE INTO surnames_raw (s, n, d, ss, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", records_batch)
            conn.commit()
        if state_batch:
            cur.executemany("INSERT OR REPLACE INTO crawler_state (prefix, results_count) VALUES (?, ?)", state_batch)
            conn.commit()

    print("✅ Фаза 1 завершана!")

def run_phase2_district_expansion(conn):
    print("\n" + "="*60)
    print("🎯 ФАЗА 2: Прабіванне столі 120 па 118 раёнах для папулярных прозвішчаў")
    print("="*60)

    cur = conn.cursor()
    # Find all surnames with >= 100 records in surnames_raw
    cur.execute("""
        SELECT s, COUNT(*) as cnt 
        FROM surnames_raw 
        WHERE s != ''
        GROUP BY s 
        HAVING cnt >= 100
        ORDER BY cnt DESC
    """)
    capped_surnames = [r[0] for r in cur.fetchall()]
    print(f"Знойдзена {len(capped_surnames)} прозвішчаў з лімітам >= 100 згадак.")

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
        raw = fetch_with_retry(session, payload)
        items = [clean_record(x) for x in raw]
        return [it for it in items if it.get('s') == sn]

    records_batch = []
    completed = 0
    added_count = 0
    t0 = time.time()
    last_log = time.time()

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
                print(f"[Фаза 2] Запытаў: {completed:,} / {len(tasks):,} | Дададзена новых згадак: {added_count:,} | {speed:.1f} зап/сек")
                last_log = time.time()

        if records_batch:
            cur.executemany("INSERT OR IGNORE INTO surnames_raw (s, n, d, ss, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", records_batch)
            conn.commit()

    print("✅ Фаза 2 завершана!")

def run_phase3_finalize(conn):
    print("\n" + "="*60)
    print("📦 ФАЗА 3: Пералінкаванне базы і экспарт")
    print("="*60)
    import json
    from db import slugify

    cur = conn.cursor()
    cur.execute("SELECT s, n, d, ss, lat, lon FROM surnames_raw WHERE s != ''")
    all_raw = cur.fetchall()
    print(f"Усяго чыстых запісаў у surnames_raw: {len(all_raw):,}")

    out_file = "F:/Downloads/surnames_perfect_dump.json"
    dump_data = [
        {'s': r[0], 'n': r[1], 'd': r[2], 'ss': r[3], 'lat': r[4], 'lon': r[5]}
        for r in all_raw
    ]
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(dump_data, f, ensure_ascii=False, indent=1)
    print(f"Захавана ў {out_file} ({os.path.getsize(out_file)/(1024*1024):.2f} MB)")

    # Clear and rebuild clean tables
    print("Перабудова табліц surnames і settlement_surnames...")
    cur.execute("DELETE FROM settlement_surnames")
    cur.execute("DELETE FROM surnames")
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('surnames')")
    conn.commit()

    # Step A: Unique surnames
    unique_snames = sorted(list(set(r[0].strip() for r in all_raw if r[0].strip())))
    print(f"Унікальных прозвішчаў: {len(unique_snames):,}. Устаўка...")
    
    sn_insert = []
    for sname in unique_snames:
        sslug = slugify(sname)
        sn_insert.append((sslug, sname, sname.lower()))

    cur.executemany("INSERT OR IGNORE INTO surnames (slug, surname_be, normalized) VALUES (?, ?, ?)", sn_insert)
    conn.commit()

    # Cache surname IDs
    cur.execute("SELECT surname_be, id FROM surnames")
    sn_cache = {r[0]: r[1] for r in cur.fetchall()}
    print(f"Кэш прозвішчаў гатовы: {len(sn_cache):,} ID.")

    # Step B: Settlements anchors
    cur.execute("SELECT id, name_be, name_ru, district, lat, lon FROM settlements")
    coord_cache4 = {}
    coord_cache3 = {}
    name_dist_cache = {}

    for row in cur.fetchall():
        sid, n_be, n_ru, dist, lat, lon = row
        if lat and lon:
            coord_cache4[(round(float(lat), 4), round(float(lon), 4))] = sid
            coord_cache3[(round(float(lat), 3), round(float(lon), 3))] = sid
        if n_be and dist:
            clean_be = re.sub(r'\(.*?\)', '', n_be).strip().lower()
            name_dist_cache[(clean_be, dist.strip().lower())] = sid
            name_dist_cache[(n_be.strip().lower(), dist.strip().lower())] = sid
        if n_ru and dist:
            clean_ru = re.sub(r'\(.*?\)', '', n_ru).strip().lower()
            name_dist_cache[(clean_ru, dist.strip().lower())] = sid
            name_dist_cache[(n_ru.strip().lower(), dist.strip().lower())] = sid

    # Step C: Link
    print("Звязванне прозвішчаў з паселішчамі...")
    links_set = set()
    for r in all_raw:
        sname, place, dist, ss, lat, lon = r
        sn_id = sn_cache.get(sname.strip())
        if not sn_id:
            continue

        matched_sid = None
        if lat and lon:
            try:
                c4 = (round(float(lat), 4), round(float(lon), 4))
                matched_sid = coord_cache4.get(c4)
                if not matched_sid:
                    c3 = (round(float(lat), 3), round(float(lon), 3))
                    matched_sid = coord_cache3.get(c3)
            except Exception:
                pass

        if not matched_sid and place and dist:
            clean_p = re.sub(r'\(.*?\)', '', place).strip().lower()
            clean_d = dist.strip().lower()
            matched_sid = name_dist_cache.get((clean_p, clean_d)) or name_dist_cache.get((place.lower(), clean_d))

        if matched_sid:
            links_set.add((matched_sid, sn_id, f"БелНДЦЭД ({place}, {dist})"))

    print(f"Устаўка {len(links_set):,} сувязяў у базу...")
    batch = list(links_set)
    for i in range(0, len(batch), 20000):
        chunk = batch[i:i+20000]
        cur.executemany("INSERT OR IGNORE INTO settlement_surnames (settlement_id, surname_id, mention_source) VALUES (?, ?, ?)", chunk)
        conn.commit()

    conn.commit()
    print("🎉 ВЫНІКОВЫ ІМПАРТ І ЛІНКАВАННЕ ЗАВЕРШАНЫ НА 100%!")

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        run_phase1_deep_expansion(conn)
        run_phase2_district_expansion(conn)
        run_phase3_finalize(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
