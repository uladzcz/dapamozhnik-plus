import sqlite3
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('dapamozhnik.db')
cur = conn.cursor()

cur.execute("SELECT district, count(*) FROM settlements WHERE district != '' GROUP BY district")
dist_totals = dict(cur.fetchall())

overlooked = [
    ("ец/эц", ["%ец", "%эц"]),
    ("ак/як", ["%ак", "%як"]),
    ("ейка/айка", ["%ейка", "%айка"]),
    ("кевіч", ["%кевіч"]),
    ("ла/йла", ["%ла", "%йла"]),
    ("ута/юта", ["%ута", "%юта"]),
    ("ка (агулам)", ["%ка"]),
    ("ко", ["%ко"])
]

print("="*85)
print(f"{'Суфікс':<15} | {'Прозвішчаў':<10} | {'Вёсак':<8} | {'ТОП раёны па долі (%)'}")
print("="*85)

for label, pats in overlooked:
    conds = " OR ".join(["sn.surname_be LIKE ?" for _ in pats])
    cur.execute(f"SELECT count(*) FROM surnames sn WHERE {conds}", pats)
    sn_cnt = cur.fetchone()[0]

    cur.execute(f"""
        SELECT st.district, count(DISTINCT st.id) as cnt
        FROM settlements st
        JOIN settlement_surnames ss ON st.id = ss.settlement_id
        JOIN surnames sn ON ss.surname_id = sn.id
        WHERE {conds} AND st.district != ''
        GROUP BY st.district
    """, pats)
    dist_rows = cur.fetchall()
    total_st = sum(r[1] for r in dist_rows)

    dist_pcts = []
    for d, c in dist_rows:
        tot = dist_totals.get(d, 0)
        if tot > 0:
            dist_pcts.append((d, c, tot, round(c*100.0/tot, 1)))
    dist_pcts.sort(key=lambda x: x[3], reverse=True)
    top_str = ", ".join([f"{d} ({pct}%)" for d, c, tot, pct in dist_pcts[:4]])

    print(f"{label:<15} | {sn_cnt:<10} | {total_st:<8} | {top_str}")

conn.close()
