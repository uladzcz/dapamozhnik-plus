import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('dapamozhnik.db')
cur = conn.cursor()

# 1. Check -эйка, -ейка, -айка
print("=== 1. Даследаванне -эйка / -ейка / -айка ===")
cur.execute("""
    SELECT count(DISTINCT sn.id), count(DISTINCT st.id)
    FROM surnames sn
    JOIN settlement_surnames ss ON sn.id = ss.surname_id
    JOIN settlements st ON ss.settlement_id = st.id
    WHERE sn.surname_be LIKE '%эйка'
""")
eyka_s, eyka_v = cur.fetchone()
print(f"-эйка: {eyka_s} прозвішчаў, {eyka_v} паселішчаў")

cur.execute("""
    SELECT count(DISTINCT sn.id), count(DISTINCT st.id)
    FROM surnames sn
    JOIN settlement_surnames ss ON sn.id = ss.surname_id
    JOIN settlements st ON ss.settlement_id = st.id
    WHERE sn.surname_be LIKE '%ейка'
""")
yejka_s, yejka_v = cur.fetchone()
print(f"-ейка: {yejka_s} прозвішчаў, {yejka_v} паселішчаў")

cur.execute("""
    SELECT count(DISTINCT sn.id), count(DISTINCT st.id)
    FROM surnames sn
    JOIN settlement_surnames ss ON sn.id = ss.surname_id
    JOIN settlements st ON ss.settlement_id = st.id
    WHERE sn.surname_be LIKE '%айка'
""")
ayka_s, ayka_v = cur.fetchone()
print(f"-айка: {ayka_s} прозвішчаў, {ayka_v} паселішчаў")

cur.execute("""
    SELECT count(DISTINCT sn.id), count(DISTINCT st.id)
    FROM surnames sn
    JOIN settlement_surnames ss ON sn.id = ss.surname_id
    JOIN settlements st ON ss.settlement_id = st.id
    WHERE sn.surname_be LIKE '%эйка' OR sn.surname_be LIKE '%ейка' OR sn.surname_be LIKE '%айка'
""")
tot_s, tot_v = cur.fetchone()
print(f"РАЗАМ (-эйка / -ейка / -айка): {tot_s} прозвішчаў, {tot_v} паселішчаў")

# Top surnames for -эйка / -ейка / -айка
cur.execute("""
    SELECT sn.surname_be, count(DISTINCT st.id) as cnt
    FROM surnames sn
    JOIN settlement_surnames ss ON sn.id = ss.surname_id
    JOIN settlements st ON ss.settlement_id = st.id
    WHERE sn.surname_be LIKE '%эйка' OR sn.surname_be LIKE '%ейка' OR sn.surname_be LIKE '%айка'
    GROUP BY sn.surname_be
    ORDER BY cnt DESC LIMIT 15
""")
print("Топ прозвішчы (-эйка/-ейка/-айка):", [f"{r[0]} ({r[1]})" for r in cur.fetchall()])

print("\n=== 2. Параўнальны аналіз -ік/-ык vs -ак/-як ===")
# 2. -ік / -ык
cur.execute("""
    SELECT count(DISTINCT sn.id), count(DISTINCT st.id)
    FROM surnames sn
    JOIN settlement_surnames ss ON sn.id = ss.surname_id
    JOIN settlements st ON ss.settlement_id = st.id
    WHERE sn.surname_be LIKE '%ік' OR sn.surname_be LIKE '%ык'
""")
ik_s, ik_v = cur.fetchone()
print(f"-ік / -ык: {ik_s} прозвішчаў, {ik_v} паселішчаў")

# Top surnames for -ік / -ык
cur.execute("""
    SELECT sn.surname_be, count(DISTINCT st.id) as cnt
    FROM surnames sn
    JOIN settlement_surnames ss ON sn.id = ss.surname_id
    JOIN settlements st ON ss.settlement_id = st.id
    WHERE sn.surname_be LIKE '%ік' OR sn.surname_be LIKE '%ык'
    GROUP BY sn.surname_be
    ORDER BY cnt DESC LIMIT 10
""")
print("Топ прозвішчы (-ік / -ык):", [f"{r[0]} ({r[1]})" for r in cur.fetchall()])

# Top districts for -ік / -ык
cur.execute("""
    SELECT st.district, count(DISTINCT st.id) as cnt
    FROM settlements st
    JOIN settlement_surnames ss ON st.id = ss.settlement_id
    JOIN surnames sn ON ss.surname_id = sn.id
    WHERE (sn.surname_be LIKE '%ік' OR sn.surname_be LIKE '%ык') AND st.district != ''
    GROUP BY st.district
    ORDER BY cnt DESC LIMIT 7
""")
print("Топ раёны па колькасці вёсак (-ік / -ык):", [f"{r[0]} ({r[1]})" for r in cur.fetchall()])

# 3. -ак / -як
cur.execute("""
    SELECT count(DISTINCT sn.id), count(DISTINCT st.id)
    FROM surnames sn
    JOIN settlement_surnames ss ON sn.id = ss.surname_id
    JOIN settlements st ON ss.settlement_id = st.id
    WHERE sn.surname_be LIKE '%ак' OR sn.surname_be LIKE '%як'
""")
ak_s, ak_v = cur.fetchone()
print(f"\n-ак / -як: {ak_s} прозвішчаў, {ak_v} паселішчаў")

# Top surnames for -ак / -як
cur.execute("""
    SELECT sn.surname_be, count(DISTINCT st.id) as cnt
    FROM surnames sn
    JOIN settlement_surnames ss ON sn.id = ss.surname_id
    JOIN settlements st ON ss.settlement_id = st.id
    WHERE sn.surname_be LIKE '%ак' OR sn.surname_be LIKE '%як'
    GROUP BY sn.surname_be
    ORDER BY cnt DESC LIMIT 10
""")
print("Топ прозвішчы (-ак / -як):", [f"{r[0]} ({r[1]})" for r in cur.fetchall()])

# Top districts for -ак / -як
cur.execute("""
    SELECT st.district, count(DISTINCT st.id) as cnt
    FROM settlements st
    JOIN settlement_surnames ss ON st.id = ss.settlement_id
    JOIN surnames sn ON ss.surname_id = sn.id
    WHERE (sn.surname_be LIKE '%ак' OR sn.surname_be LIKE '%як') AND st.district != ''
    GROUP BY st.district
    ORDER BY cnt DESC LIMIT 7
""")
print("Топ раёны па колькасці вёсак (-ак / -як):", [f"{r[0]} ({r[1]})" for r in cur.fetchall()])

conn.close()
