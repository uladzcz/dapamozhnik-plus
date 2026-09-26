import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('dapamozhnik.db')
cur = conn.cursor()

print("--- Testing Barysau ---")
cur.execute("""
    SELECT st.id, st.name_be, st.settlement_type, st.district, count(ss.surname_id)
    FROM settlements st
    LEFT JOIN settlement_surnames ss ON st.id = ss.settlement_id
    WHERE st.name_be = 'Барысаў'
    GROUP BY st.id
""")
for r in cur.fetchall():
    print(r)

print("\n--- Testing Horki (г.) ---")
cur.execute("""
    SELECT st.id, st.name_be, st.settlement_type, st.district, count(ss.surname_id)
    FROM settlements st
    LEFT JOIN settlement_surnames ss ON st.id = ss.settlement_id
    WHERE st.name_be = 'Горкі' AND st.district = 'Горацкі'
    GROUP BY st.id
""")
for r in cur.fetchall():
    print(r)

print("\n--- Testing Charnitsa (Smalyavichy) ---")
cur.execute("""
    SELECT st.id, st.name_be, st.settlement_type, st.district, count(ss.surname_id)
    FROM settlements st
    LEFT JOIN settlement_surnames ss ON st.id = ss.settlement_id
    WHERE st.name_be = 'Чарніца' AND st.district = 'Смалявіцкі'
    GROUP BY st.id
""")
for r in cur.fetchall():
    print(r)

print("\n--- Testing Disna ---")
cur.execute("""
    SELECT st.id, st.name_be, st.settlement_type, st.district, count(ss.surname_id)
    FROM settlements st
    LEFT JOIN settlement_surnames ss ON st.id = ss.settlement_id
    WHERE st.name_be = 'Дзісна'
    GROUP BY st.id
""")
for r in cur.fetchall():
    print(r)

conn.close()
