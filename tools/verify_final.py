import sqlite3
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('C:/Users/bafur/.gemini/antigravity/scratch/dapamozhnik_plus/dapamozhnik.db')
cur = conn.cursor()

cur.execute('SELECT count(*) FROM settlements')
print('Settlements:', cur.fetchone()[0])
cur.execute('SELECT count(*) FROM surnames')
print('Surnames:', cur.fetchone()[0])
cur.execute('SELECT count(*) FROM settlement_surnames')
print('Settlement_surnames links:', cur.fetchone()[0])

print('\n--- Праверка Каралёў ---')
cur.execute("""
    SELECT s.id, s.surname_be, count(ss.settlement_id) 
    FROM surnames s 
    LEFT JOIN settlement_surnames ss ON s.id = ss.surname_id 
    WHERE s.surname_be LIKE 'Каралё%' 
    GROUP BY s.id
""")
for r in cur.fetchall():
    print(f"  {r[1]} (id={r[0]}): {r[2]} паселішчаў")

print('\n--- Новы ТОП-15 самых распаўсюджаных прозвішчаў (без столі 120!) ---')
cur.execute("""
    SELECT s.surname_be, count(ss.settlement_id) as cnt
    FROM surnames s
    JOIN settlement_surnames ss ON s.id = ss.surname_id
    GROUP BY s.id
    ORDER BY cnt DESC
    LIMIT 15
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} паселішчаў")

print('\n--- Некалькі вёсак для Каралёў ---')
cur.execute("""
    SELECT st.name_be, st.district, st.lat, st.lon
    FROM settlement_surnames ss
    JOIN settlements st ON ss.settlement_id = st.id
    JOIN surnames s ON ss.surname_id = s.id
    WHERE s.surname_be = 'Каралёў'
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"  * {r[0]} ({r[1]} р-н) [{r[2]}, {r[3]}]")
