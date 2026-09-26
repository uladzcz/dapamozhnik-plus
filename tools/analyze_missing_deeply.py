import sqlite3
import re
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('dapamozhnik.db')
cur = conn.cursor()

print("Analyzing surnames_raw vs settlements...")

# Load all settlements
cur.execute("SELECT id, name_be, name_ru, district, settlement_type, lat, lon FROM settlements")
settlements = cur.fetchall()

print(f"Total rows in settlements: {len(settlements):,}")

# Build spatial and name indexes
coord_index_3 = {} # (round(lat, 3), round(lon, 3)) -> list of settlements
coord_index_2 = {} # (round(lat, 2), round(lon, 2)) -> list of settlements
name_dist_index = {} # (normalized_name, normalized_dist) -> list of settlements

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

for sid, n_be, n_ru, dist, stype, lat, lon in settlements:
    nd = norm_dist(dist)
    if lat and lon:
        c3 = (round(float(lat), 3), round(float(lon), 3))
        coord_index_3.setdefault(c3, []).append(sid)
        c2 = (round(float(lat), 2), round(float(lon), 2))
        coord_index_2.setdefault(c2, []).append(sid)
    
    nb = norm_str(n_be)
    nr = norm_str(n_ru)
    if nb:
        name_dist_index.setdefault((nb, nd), []).append(sid)
    if nr:
        name_dist_index.setdefault((nr, nd), []).append(sid)

# Now check surnames_raw
cur.execute("SELECT DISTINCT n, d, lat, lon FROM surnames_raw WHERE n != ''")
raw_items = cur.fetchall()
print(f"Distinct (n, d, lat, lon) in surnames_raw: {len(raw_items):,}")

match_by_name_and_dist = 0
match_by_coord_exact3 = 0
match_by_name_only = 0
completely_unmatched = []

for n, d, lat, lon in raw_items:
    nb = norm_str(n)
    nd = norm_dist(d)
    
    matched = False
    
    # 1. Try name + district
    if (nb, nd) in name_dist_index:
        match_by_name_and_dist += 1
        matched = True
    elif lat and lon:
        c3 = (round(float(lat), 3), round(float(lon), 3))
        if c3 in coord_index_3:
            match_by_coord_exact3 += 1
            matched = True
            
    if not matched:
        completely_unmatched.append((n, d, lat, lon))

print(f"Matched by (name + district): {match_by_name_and_dist:,}")
print(f"Matched by coordinates (~100m): {match_by_coord_exact3:,}")
print(f"Completely unmatched (truly missing from settlements table): {len(completely_unmatched):,}")

print("\nSample 25 truly missing items:")
for n, d, lat, lon in completely_unmatched[:25]:
    # Count how many surname records reference this missing place
    cur.execute("SELECT count(*), count(DISTINCT s) FROM surnames_raw WHERE n = ? AND d = ?", (n, d))
    cnt, uniq_s = cur.fetchone()
    print(f"  • '{n}' ({d} р-н) [{lat}, {lon}] -> {cnt} згадак, {uniq_s} прозвішчаў")

conn.close()
