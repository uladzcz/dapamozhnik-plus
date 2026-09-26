"""
Full Ingestion Script for Recovering 5,327 Missing Settlements and Linking All Orphaned Surnames.
Ensures 100% database completeness from surnames_raw into settlements and settlement_surnames.
"""
import sqlite3
import re
import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from db import get_db_connection, slugify

def clean_place_name(raw_name):
    name = raw_name.strip()
    stype = 'вёска'
    
    if ', г.' in name or name.endswith(' (г.)') or name.startswith('г. '):
        stype = 'Горад'
        name = re.sub(r',?\s*г\.?$', '', name)
        name = re.sub(r'\(г\.?\)', '', name)
        name = re.sub(r'^г\.?\s*', '', name)
    elif 'г.п.' in name or '(г.п.)' in name:
        stype = 'Гарадскі пасёлак'
        name = re.sub(r'\(г\.?п\.?\)', '', name)
        name = re.sub(r',?\s*г\.?п\.?$', '', name)
    elif 'раб. пас.' in name:
        stype = 'Рабочы пасёлак'
        name = re.sub(r'\(раб\.\s*пас\..*?\)', '', name)
    elif '(хут.)' in name or name.startswith('х. '):
        stype = 'Хутар'
        name = re.sub(r'\(хут\.?\)', '', name)
        name = re.sub(r'^х\.?\s*', '', name)
    elif '(пас.)' in name or name.startswith('пас. '):
        stype = 'Пасёлак'
        name = re.sub(r'\(пас\.?\)', '', name)
        name = re.sub(r'^пас\.?\s*', '', name)
        
    return name.strip(), stype

def norm_str(s):
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r'\(.*?\)', '', s)
    s = re.sub(r'\bг\.?\b', '', s)
    s = re.sub(r'\bв\.?\b', '', s)
    s = re.sub(r'\bвёска\b', '', s)
    s = re.sub(r'\bпас\.?\b', '', s)
    s = re.sub(r'\bпасёлак\b', '', s)
    s = re.sub(r'\bхутар\b', '', s)
    s = re.sub(r'\bх\.?\b', '', s)
    s = re.sub(r'не існуе\s*/?', '', s)
    s = re.sub(r'да \d+-х\s*', '', s)
    s = re.sub(r'[^а-яёіўa-z0-9]', '', s)
    return s

def norm_dist(d):
    if not d:
        return ""
    d = d.lower().strip()
    d = re.sub(r'\b(р-н|раён|район)\b', '', d)
    d = re.sub(r'[^а-яёіўa-z0-9]', '', d)
    return d

def run_ingestion():
    t0 = time.time()
    print("=" * 60)
    print("🚀 Пачатак аднаўлення 5 327 паселішчаў і сінхранізацыі прозвішчаў...")
    print("=" * 60)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA journal_mode = MEMORY")
    cur.execute("PRAGMA cache_size = 100000")

    # Step 1: Index existing settlements
    print("Крок 1: Індэксаванне існуючых паселішчаў...")
    cur.execute("SELECT id, name_be, name_ru, district, lat, lon FROM settlements")
    settlements = cur.fetchall()
    print(f"  Знойдзена існуючых паселішчаў у базе: {len(settlements):,}")

    coord_index_3 = {}
    name_dist_index = {}

    for sid, n_be, n_ru, dist, lat, lon in settlements:
        nd = norm_dist(dist)
        if lat and lon:
            try:
                c3 = (round(float(lat), 3), round(float(lon), 3))
                coord_index_3[c3] = sid
            except:
                pass
        nb = norm_str(n_be)
        nr = norm_str(n_ru)
        if nb:
            name_dist_index[(nb, nd)] = sid
        if nr:
            name_dist_index[(nr, nd)] = sid

    # Step 2: Read all surnames_raw
    print("Крок 2: Чытанне ўсіх запісаў surnames_raw...")
    cur.execute("SELECT s, n, d, ss, lat, lon FROM surnames_raw WHERE s != ''")
    all_raw = cur.fetchall()
    print(f"  Усяго сырых запісаў: {len(all_raw):,}")

    # Determine which are missing
    new_settlements_dict = {} # key -> list of raw items
    matched_existing_links = [] # (settlement_id, surname_str, source)

    for s, n, d, ss, lat, lon in all_raw:
        clean_n, stype = clean_place_name(n)
        nb = norm_str(clean_n)
        nd = norm_dist(d)

        sid = name_dist_index.get((nb, nd))
        if not sid and lat and lon:
            try:
                c3 = (round(float(lat), 3), round(float(lon), 3))
                sid = coord_index_3.get(c3)
            except:
                pass

        if sid:
            matched_existing_links.append((sid, s, f"БелНДЦЭД ({n}, {d})"))
        else:
            key = (clean_n, d, ss, lat, lon, stype, n)
            new_settlements_dict.setdefault(key, []).append((s, f"БелНДЦЭД ({n}, {d})"))

    print(f"  Знойдзена сувязяў з існуючымі паселішчамі: {len(matched_existing_links):,}")
    print(f"  Знойдзена новых унікальных паселішчаў для стварэння: {len(new_settlements_dict):,}")

    # Step 3: Insert new settlements
    print("Крок 3: Стварэнне і ўстаўка новых паселішчаў...")
    cur.execute("SELECT slug FROM settlements")
    existing_slugs = set(r[0] for r in cur.fetchall())

    new_settlement_rows = []
    created_settlements_map = {} # key -> sid

    for key in new_settlements_dict.keys():
        clean_n, d, ss, lat, lon, stype, raw_n = key
        base_slug = slugify(f"{clean_n}-{d}")
        slug = base_slug
        counter = 1
        while slug in existing_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1
        existing_slugs.add(slug)

        alt = raw_n if raw_n != clean_n else ""
        try:
            flat = float(lat) if lat else None
            flon = float(lon) if lon else None
        except:
            flat, flon = None, None

        new_settlement_rows.append((
            slug,
            clean_n,
            clean_n, # name_ru fallback
            stype,
            d,
            ss,
            alt,
            flat,
            flon
        ))

    cur.executemany("""
        INSERT INTO settlements (
            slug, name_be, name_ru, settlement_type, district, selsoviet, alt_names, lat, lon
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, new_settlement_rows)
    conn.commit()
    print(f"   паспяхова ўстаўлена {len(new_settlement_rows):,} новых паселішчаў!")

    # Step 4: Map new settlements to their inserted IDs
    print("Крок 4: Супастаўленне ID новых паселішчаў...")
    for key in new_settlements_dict.keys():
        clean_n, d, ss, lat, lon, stype, raw_n = key
        cur.execute("""
            SELECT id FROM settlements 
            WHERE name_be = ? AND district = ? AND settlement_type = ?
            ORDER BY id DESC LIMIT 1
        """, (clean_n, d, stype))
        row = cur.fetchone()
        if row:
            created_settlements_map[key] = row[0]

    # Step 5: Ensure all unique surnames exist in surnames table
    print("Крок 5: Праверка і дапаўненне табліцы surnames...")
    cur.execute("SELECT surname_be, id FROM surnames")
    surname_id_cache = {row[0]: row[1] for row in cur.fetchall()}

    all_distinct_surnames = set()
    for s, _, _, _, _, _ in all_raw:
        all_distinct_surnames.add(s)

    new_surnames_to_insert = []
    for sname in all_distinct_surnames:
        if sname not in surname_id_cache:
            new_surnames_to_insert.append((slugify(sname), sname, sname.lower()))

    if new_surnames_to_insert:
        print(f"  Даданне {len(new_surnames_to_insert):,} новых прозвішчаў у табліцу surnames...")
        cur.executemany("INSERT OR IGNORE INTO surnames (slug, surname_be, normalized) VALUES (?, ?, ?)", new_surnames_to_insert)
        conn.commit()
        # Reload cache
        cur.execute("SELECT surname_be, id FROM surnames")
        surname_id_cache = {row[0]: row[1] for row in cur.fetchall()}

    # Step 6: Insert all settlement-surname links
    print("Крок 6: Генерацыя і ўстаўка ўсіх сувязяў у settlement_surnames...")
    all_links_to_insert = set()

    # Existing links
    for sid, s, src in matched_existing_links:
        sn_id = surname_id_cache.get(s)
        if sn_id and sid:
            all_links_to_insert.add((sid, sn_id, src))

    # New settlement links
    for key, items in new_settlements_dict.items():
        sid = created_settlements_map.get(key)
        if not sid:
            continue
        for s, src in items:
            sn_id = surname_id_cache.get(s)
            if sn_id:
                all_links_to_insert.add((sid, sn_id, src))

    print(f"  Усяго унікальных сувязяў для запісу: {len(all_links_to_insert):,}...")
    batch = list(all_links_to_insert)
    batch_size = 25000
    for i in range(0, len(batch), batch_size):
        chunk = batch[i:i + batch_size]
        cur.executemany("INSERT OR IGNORE INTO settlement_surnames (settlement_id, surname_id, mention_source) VALUES (?, ?, ?)", chunk)
        conn.commit()
        print(f"    Запісана {min(i + batch_size, len(batch)):,} / {len(batch):,} сувязяў...")

    conn.commit()

    # Final DB counts
    cur.execute("SELECT count(*) FROM settlements")
    final_settlements_cnt = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM surnames")
    final_surnames_cnt = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM settlement_surnames")
    final_links_cnt = cur.fetchone()[0]

    # Check Barysau
    cur.execute("""
        SELECT st.id, st.name_be, st.settlement_type, st.district, count(ss.surname_id)
        FROM settlements st
        LEFT JOIN settlement_surnames ss ON st.id = ss.settlement_id
        WHERE st.name_be = 'Барысаў' AND st.district LIKE '%Барысаў%'
        GROUP BY st.id
    """)
    barysau_info = cur.fetchall()

    conn.close()

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(f"🎉 ПОСПЕХ! Аднаўленне завершана за {elapsed:.1f} сек.")
    print(f"  • Агулам паселішчаў у базе: {final_settlements_cnt:,}")
    print(f"  • Агулам унікальных прозвішчаў: {final_surnames_cnt:,}")
    print(f"  • Агулам звязаных прозвішчаў (links): {final_links_cnt:,}")
    print(f"  • Барысаў у базе: {barysau_info}")
    print("=" * 60)

if __name__ == "__main__":
    run_ingestion()
