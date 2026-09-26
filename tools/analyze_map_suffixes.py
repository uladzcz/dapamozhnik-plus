import sqlite3
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('dapamozhnik.db')
cur = conn.cursor()

# Map features from user's image:
suffixes_to_test = [
    ("ік/ык", ["%ік", "%ык"]),
    ("еня/эня", ["%еня", "%эня"]),
    ("ін/ын", ["%ін", "%ын"]),
    ("анка/янка", ["%анка", "%янка"]),
    ("ук/юк/чук", ["%ук", "%юк", "%чук"]),
    ("віч/іч/ыч", ["%віч", "%іч", "%ыч"]),
    ("ёнак/онак", ["%ёнак", "%онак"]),
    ("скі/цкі", ["%скі", "%цкі"]),
    ("оў/аў/еў/эў", ["%оў", "%аў", "%еў", "%эў"]),
    ("энка/енка", ["%энка", "%енка"])
]

cur.execute("SELECT district, count(*) FROM settlements WHERE district != '' GROUP BY district")
dist_totals = dict(cur.fetchall())

print("="*70)
print(f"{'Суфікс':<15} | {'Прозвішчаў':<10} | {'Вёсак':<10} | {'Галоўны рэгіён / раёны'}")
print("="*70)

for label, pats in suffixes_to_test:
    conds = " OR ".join(["sn.surname_be LIKE ?" for _ in pats])
    
    # Count surnames
    cur.execute(f"SELECT count(*) FROM surnames sn WHERE {conds}", pats)
    sn_cnt = cur.fetchone()[0]

    # Count settlements & get top district
    cur.execute(f"""
        SELECT st.district, count(DISTINCT st.id) as cnt
        FROM settlements st
        JOIN settlement_surnames ss ON st.id = ss.settlement_id
        JOIN surnames sn ON ss.surname_id = sn.id
        WHERE {conds} AND st.district != ''
        GROUP BY st.district
        ORDER BY cnt DESC
    """, pats)
    dist_rows = cur.fetchall()
    total_st = sum(r[1] for r in dist_rows)
    
    top_dist_str = ""
    if dist_rows:
        # Sort by percentage
        dist_pcts = []
        for d, c in dist_rows:
            tot = dist_totals.get(d, 0)
            if tot > 0:
                dist_pcts.append((d, c, tot, round(c*100.0/tot, 1)))
        dist_pcts.sort(key=lambda x: x[3], reverse=True)
        top_dist_str = ", ".join([f"{d} ({pct}%)" for d, c, tot, pct in dist_pcts[:3]])

    print(f"{label:<15} | {sn_cnt:<10} | {total_st:<10} | {top_dist_str}")
