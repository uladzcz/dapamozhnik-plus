import requests, msgpack, urllib3
import sqlite3
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
s = requests.Session()
s.headers.update(headers)

def slugify(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^\w\-]', '', text)
    return text

stems = [
    'артак', 'артач', 'арнов', 'арасав', 'арасов', 'арасенк', 'арахоўк', 'араховк',
    'аркан', 'арчылаў', 'орчилов', 'арлаўшч', 'ардунов', 'арбейк', 'арсун', 'армян',
    'арановіч', 'аранович', 'арасевіч', 'арасевич', 'арапеш', 'арпец', 'аропец',
    'аран-Подг', 'аракан'
]

print("1. Fetching authentic Тар* settlements from helper.archonline.by...")
collected = {}
for stem in stems:
    try:
        r = s.post('https://helper.archonline.by/data', data={'q': stem, 'm': 1, 't': '0', 'u': '1', 's': ''}, verify=False, timeout=6)
        if r.status_code == 200:
            res = msgpack.unpackb(r.content, raw=False)
            for it in res:
                be = (it.get(b'place_be') or b'').decode('utf-8', errors='replace').strip()
                ru = (it.get(b'place_ru') or b'').decode('utf-8', errors='replace').strip()
                n = (it.get(b'n') or b'').decode('utf-8', errors='replace').strip()
                d = (it.get(b'd') or b'').decode('utf-8', errors='replace').strip()
                lat = it.get(b'lat')
                lon = it.get(b'lon')
                names_to_check = [be, ru, n]
                is_tar = any('Тар' in name or 'Тор' in name or 'Тара' in name for name in names_to_check)
                if is_tar:
                    key = (be, ru, d, str(lat), str(lon))
                    if key not in collected:
                        collected[key] = it
    except Exception as e:
        print(f"Error {stem}: {e}")

print(f"Collected {len(collected)} authentic settlements.")

conn = sqlite3.connect('dapamozhnik.db')
cur = conn.cursor()

inserted = 0
new_settlements = []

for (be, ru, d, lat_str, lon_str), item in collected.items():
    # Check if already exists in settlements
    cur.execute("""
        SELECT id, name_be, name_ru, district FROM settlements 
        WHERE (name_be = ? OR name_ru = ?) AND district = ?
    """, (be, ru, d))
    existing = cur.fetchone()
    if existing:
        new_settlements.append((existing[0], existing[1], existing[2], existing[3]))
        continue

    def get_str(k):
        val = item.get(k.encode('utf-8'))
        if val is None:
            return ""
        if isinstance(val, bytes):
            return val.decode('utf-8', errors='replace').strip()
        return str(val).strip()

    name_be = get_str('place_be') or get_str('n') or "Невядомая"
    name_ru = get_str('place_ru') or get_str('n') or name_be
    district = get_str('d')
    selsoviet = get_str('ss1981_ru') or get_str('ss2011') or get_str('ss')
    stype = get_str('unit_type') or "вёска"
    powiat_18 = get_str('c18')
    estate_18 = get_str('estate')
    owner_18 = get_str('owner_be')
    estate_19 = get_str('estate_1863')
    owner_19 = get_str('owner_ru')
    belonging = get_str('ownership')
    uezd = get_str('county') or get_str('c19')
    volost = get_str('volost')
    parish_orth = get_str('parish_east19') or get_str('parish_east20')
    parish_cath = get_str('parish_roman') or get_str('parish_roman19') or get_str('parish_roman20')
    is_abandoned = 1 if ("не існуе" in name_be.lower() or "не існуе" in name_ru.lower()) else 0

    try:
        lat = float(item.get(b'lat')) if item.get(b'lat') is not None and item.get(b'lat') != b'' else None
    except Exception:
        lat = None
    try:
        lon = float(item.get(b'lon')) if item.get(b'lon') is not None and item.get(b'lon') != b'' else None
    except Exception:
        lon = None

    base_slug = slugify(f"{name_be}-{district}")
    slug = base_slug
    idx = 1
    while True:
        cur.execute("SELECT id FROM settlements WHERE slug = ?", (slug,))
        if not cur.fetchone():
            break
        idx += 1
        slug = f"{base_slug}-{idx}"

    cur.execute("""
        INSERT INTO settlements (
            slug, name_be, name_ru, settlement_type, district, selsoviet,
            powiat_18, estate_18, owner_18, estate_19, owner_19, belonging,
            uezd, volost, parish_orthodox, parish_catholic, is_abandoned,
            lat, lon
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        slug, name_be, name_ru, stype, district, selsoviet,
        powiat_18, estate_18, owner_18, estate_19, owner_19, belonging,
        uezd, volost, parish_orth, parish_cath, is_abandoned,
        lat, lon
    ))
    new_id = cur.lastrowid
    new_settlements.append((new_id, name_be, name_ru, district))
    inserted += 1

conn.commit()
print(f"2. Newly inserted {inserted} settlements into settlements table.")

# 3. Targeted linking to surnames_raw
print("3. Linking settlements to surnames...")
total_links = 0
for st_id, n_be, n_ru, dist in new_settlements:
    clean_be = n_be.replace("не існуе / ", "").replace("да 1980-х ", "").replace("да 1942 ", "").replace("да 1950-х ", "").split(" (")[0].strip()
    clean_ru = n_ru.replace("не існуе / ", "").replace("да 1980-х ", "").split(" (")[0].strip()

    cur.execute("""
        INSERT OR IGNORE INTO settlement_surnames (settlement_id, surname_id)
        SELECT DISTINCT ?, sn.id
        FROM surnames_raw sr
        JOIN surnames sn ON sn.surname_be = sr.s
        WHERE sr.d = ? AND (sr.n = ? OR sr.n = ? OR sr.n = ? OR sr.n = ?)
    """, (st_id, dist, n_be, n_ru, clean_be, clean_ru))
    total_links += cur.rowcount

conn.commit()
print(f"Linked {total_links} settlement-surname relations.")

# 4. Verification
cur.execute("SELECT id, name_be, name_ru, district, lat, lon FROM settlements WHERE name_be LIKE '%Тартак%' OR name_ru LIKE '%Тартак%'")
tartaks = cur.fetchall()
print(f"\n4. Verification: Found {len(tartaks)} Tartak settlements in dapamozhnik.db:")
for t in tartaks:
    cur.execute("SELECT count(*) FROM settlement_surnames WHERE settlement_id = ?", (t[0],))
    cnt = cur.fetchone()[0]
    print(f"  • ID {t[0]}: {t[1]} / {t[2]} ({t[3]} р-н) [{t[4]}, {t[5]}] -> {cnt} surnames linked")

conn.close()
print("\n Done successfully!")
