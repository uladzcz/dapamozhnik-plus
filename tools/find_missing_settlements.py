import sqlite3
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('dapamozhnik.db')
cur = conn.cursor()

print("1. Checking settlements in surnames_raw that have no match in settlements table...")

# Find all distinct (n, d) pairs in surnames_raw
cur.execute("SELECT DISTINCT n, d, lat, lon FROM surnames_raw WHERE n != '' AND d != ''")
raw_settlements = cur.fetchall()
print(f"Total unique (village, district) pairs in surnames_raw: {len(raw_settlements):,}")

# Check which ones do not exist in settlements table
cur.execute("SELECT name_be, name_ru, district FROM settlements")
db_settlements = set()
for r in cur.fetchall():
    be = (r[0] or '').strip().lower()
    ru = (r[1] or '').strip().lower()
    d = (r[2] or '').strip().lower()
    db_settlements.add((be, d))
    db_settlements.add((ru, d))
    # Also without prefixes like "не існуе / "
    clean_be = be.replace("не існуе / ", "").replace("да 1980-х ", "").split(" (")[0].strip()
    clean_ru = ru.replace("не існуе / ", "").replace("да 1980-х ", "").split(" (")[0].strip()
    db_settlements.add((clean_be, d))
    db_settlements.add((clean_ru, d))

missing = []
for n, d, lat, lon in raw_settlements:
    n_lower = n.strip().lower()
    d_lower = d.strip().lower()
    clean_n = n_lower.replace("не існуе / ", "").replace("да 1980-х ", "").split(" (")[0].strip()
    
    if (n_lower, d_lower) not in db_settlements and (clean_n, d_lower) not in db_settlements:
        missing.append((n, d, lat, lon))

print(f"\nMissing settlements count: {len(missing)}")
print("\nFirst 30 missing settlements:")
for n, d, lat, lon in missing[:30]:
    print(f"  • {n} ({d} р-н) [{lat}, {lon}]")

conn.close()
