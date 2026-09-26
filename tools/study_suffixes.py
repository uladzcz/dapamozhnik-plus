import sqlite3
import re
from collections import Counter
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('dapamozhnik.db')
cur = conn.cursor()

# 1. Fetch all surnames
cur.execute("SELECT id, surname_be FROM surnames WHERE surname_be != ''")
rows = cur.fetchall()
print(f"Total surnames to analyze: {len(rows):,}")

# Frequency of each surname in settlements
cur.execute("SELECT surname_id, count(*) FROM settlement_surnames GROUP BY surname_id")
surname_freqs = dict(cur.fetchall())

# Analyze endings of length 2, 3, 4, 5
endings_count = Counter()
endings_mentions = Counter()

# Common endings patterns
for sid, name in rows:
    name_clean = name.strip().lower()
    freq = surname_freqs.get(sid, 0)
    
    # Check suffixes of lengths 2, 3, 4, 5
    for l in [2, 3, 4, 5]:
        if len(name_clean) > l:
            suf = name_clean[-l:]
            endings_count[(l, suf)] += 1
            endings_mentions[(l, suf)] += freq

print("\n" + "="*80)
print(f"{'Даўжыня':<8} | {'Суфікс':<12} | {'Унікальных прозвішчаў':<22} | {'Агулам згадак у вёсках'}")
print("="*80)

for l in [2, 3, 4, 5]:
    # Top 15 by number of unique surnames
    top = [item for item in endings_count.items() if item[0][0] == l]
    top.sort(key=lambda x: x[1], reverse=True)
    print(f"\n--- ТОП-15 суфіксаў даўжынёй {l} літары ---")
    for (length, suf), cnt in top[:15]:
        mentions = endings_mentions[(length, suf)]
        print(f"{length:<8} | -{suf:<11} | {cnt:<22,} | {mentions:<12,}")

conn.close()
