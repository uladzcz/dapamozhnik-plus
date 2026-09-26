"""
High-performance Importer for surnames dump (surnames_full_dump.json) from helper.archonline.by (mode m=2).
Populates `surnames` and `settlement_surnames` in dapamozhnik.db.
"""
import json
import os
import sys
import sqlite3
import re
import time
from db import get_db_connection, slugify

def import_surnames(json_path: str):
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    t0 = time.time()
    print(f"Loading {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    items = data if isinstance(data, list) else data.get("surnames", [])
    total_records = len(items)
    print(f"Found {total_records:,} surname records to process.")

    conn = get_db_connection()
    cur = conn.cursor()

    # Optimize SQLite for bulk insert
    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA journal_mode = MEMORY")
    cur.execute("PRAGMA cache_size = 100000")

    # Step 1: Extract and batch insert all unique surnames
    print("Step 1: Extracting unique surnames...")
    unique_surnames = {}
    for item in items:
        sname = (item.get("s") or item.get("surname") or item.get("title") or "").strip()
        if sname and sname not in unique_surnames:
            unique_surnames[sname] = slugify(sname)

    print(f"Found {len(unique_surnames):,} unique surnames. Inserting into DB...")
    
    # Load already existing surnames
    cur.execute("SELECT surname_be, id FROM surnames")
    existing_surnames = {row[0]: row[1] for row in cur.fetchall()}
    
    new_to_insert = []
    for sname, sslug in unique_surnames.items():
        if sname not in existing_surnames:
            new_to_insert.append((sslug, sname, sname.lower()))

    if new_to_insert:
        cur.executemany("INSERT OR IGNORE INTO surnames (slug, surname_be, normalized) VALUES (?, ?, ?)", new_to_insert)
        conn.commit()

    # Reload all surname IDs
    cur.execute("SELECT surname_be, id FROM surnames")
    surname_id_cache = {row[0]: row[1] for row in cur.fetchall()}
    print(f"Surname index ready with {len(surname_id_cache):,} surnames.")

    # Step 2: Index settlements for fast matching
    print("Step 2: Indexing settlements...")
    cur.execute("SELECT id, name_be, name_ru, district, lat, lon FROM settlements")
    settlements_by_coord3 = {}
    settlements_by_coord4 = {}
    settlements_by_name = {}

    for row in cur.fetchall():
        sid, n_be, n_ru, dist, lat, lon = row
        if lat and lon:
            c3 = (round(float(lat), 3), round(float(lon), 3))
            c4 = (round(float(lat), 4), round(float(lon), 4))
            settlements_by_coord3[c3] = sid
            settlements_by_coord4[c4] = sid

        if n_be and dist:
            clean_be = re.sub(r'\(.*?\)', '', n_be).strip().lower()
            settlements_by_name[(clean_be, dist.strip().lower())] = sid
            settlements_by_name[(n_be.strip().lower(), dist.strip().lower())] = sid
        if n_ru and dist:
            clean_ru = re.sub(r'\(.*?\)', '', n_ru).strip().lower()
            settlements_by_name[(clean_ru, dist.strip().lower())] = sid
            settlements_by_name[(n_ru.strip().lower(), dist.strip().lower())] = sid

    print(f"Settlements index ready ({len(settlements_by_coord3)} coordinate anchors).")

    # Step 3: Link surnames to settlements
    print("Step 3: Linking surnames to settlements...")
    links_set = set()
    unmatched_count = 0

    for item in items:
        sname = (item.get("s") or item.get("surname") or item.get("title") or "").strip()
        if not sname:
            continue
        sn_id = surname_id_cache.get(sname)
        if not sn_id:
            continue

        lat = item.get("lat")
        lon = item.get("lon")
        place_name = (item.get("n") or "").strip()
        district = (item.get("d") or "").strip()

        matched_sid = None
        if lat and lon:
            try:
                c4 = (round(float(lat), 4), round(float(lon), 4))
                matched_sid = settlements_by_coord4.get(c4)
                if not matched_sid:
                    c3 = (round(float(lat), 3), round(float(lon), 3))
                    matched_sid = settlements_by_coord3.get(c3)
            except Exception:
                pass

        if not matched_sid and place_name and district:
            clean_p = re.sub(r'\(.*?\)', '', place_name).strip().lower()
            clean_d = district.strip().lower()
            matched_sid = settlements_by_name.get((clean_p, clean_d)) or settlements_by_name.get((place_name.lower(), clean_d))

        if matched_sid:
            links_set.add((matched_sid, sn_id, f"БелНДЦЭД ({place_name}, {district})"))
        else:
            unmatched_count += 1

    print(f"Inserting {len(links_set):,} settlement-surname links into database...")
    batch = list(links_set)
    batch_size = 20000
    for i in range(0, len(batch), batch_size):
        chunk = batch[i:i + batch_size]
        cur.executemany("INSERT OR IGNORE INTO settlement_surnames (settlement_id, surname_id, mention_source) VALUES (?, ?, ?)", chunk)
        conn.commit()
        print(f"  Inserted {min(i + batch_size, len(batch)):,} / {len(batch):,} links...")

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print("\n" + "="*50)
    print(f"🎉 SUCCESS! Surnames imported in {elapsed:.1f}s")
    print(f"- Total records processed: {total_records:,}")
    print(f"- Unique surnames in database: {len(surname_id_cache):,}")
    print(f"- Unique links to settlements: {len(links_set):,}")
    print(f"- Unmatched records: {unmatched_count:,} ({unmatched_count / total_records * 100:.1f}%)")
    print("="*50)

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "F:/Downloads/surnames_full_dump.json"
    import_surnames(target)
