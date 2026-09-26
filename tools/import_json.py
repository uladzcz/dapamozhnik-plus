"""
Importer for full helper.archonline.by dumps.
Takes a JSON file exported from helper and populates dapamozhnik.db.
"""
import json
import os
import sys
from db import get_db_connection, slugify

def import_dump(json_path: str):
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    conn = get_db_connection()
    cur = conn.cursor()

    settlements = data if isinstance(data, list) else data.get("settlements", [])
    print(f"Importing {len(settlements)} settlements...")

    # Clear old test data for fresh full import
    cur.execute("DELETE FROM settlement_surnames")
    cur.execute("DELETE FROM settlements")
    cur.execute("DELETE FROM surnames")
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('settlements', 'surnames')")
    conn.commit()

    imported_count = 0
    for item in settlements:
        # Extract names
        name_be = item.get("place_be") or item.get("name_be") or item.get("Назва (бел.)") or item.get("name") or ""
        name_ru = item.get("place_ru") or item.get("name_ru") or item.get("Название (рус.)") or item.get("n") or ""
        if not name_be and not name_ru:
            name_be = item.get("n") or "Невядомая"

        # Alternative names
        alt_names = item.get("place_vars_be") or item.get("place_vars_ru") or item.get("vars") or item.get("alt_names") or ""

        # Types and regions
        stype = item.get("unit_type") or item.get("settlement_type") or item.get("Тип") or "вёска"
        district = item.get("d") or item.get("dist") or item.get("district") or item.get("Раён") or ""
        region = item.get("region_be") or item.get("region_ru") or item.get("region") or ""
        gubernia = item.get("gubernia") or ""
        
        # Selsoviets
        selsoviet = item.get("ss") or item.get("selsoviet") or item.get("Сельсавет") or ""
        selsoviet_81 = item.get("ss1981_be") or item.get("ss1981_ru") or item.get("ss81") or ""
        selsoviet_11 = item.get("ss2011") or item.get("ss11") or ""

        # XVIII century
        powiat_18 = item.get("c18") or item.get("powiat_18") or item.get("Павет (XVIII ст.)") or ""
        estate_18 = item.get("estate") or item.get("estate_18") or item.get("Маёнтак (XVIII ст.)") or ""
        owner_18 = item.get("owner_be") or item.get("owner_18") or item.get("Уласнік (XVIII ст.)") or ""
        parish_roman_18 = item.get("parish_roman") or ""

        # XIX century
        estate_19 = item.get("estate_1863") or item.get("estate_19") or item.get("Имение (до 1863 г.)") or ""
        owner_19 = item.get("owner_ru") or item.get("owner_19") or item.get("Владелец (XIX в.)") or ""
        belonging = item.get("ownership") or item.get("belonging") or item.get("Принадлежность (дорев.)") or ""
        uezd = item.get("c19") or item.get("county") or item.get("uezd") or item.get("Уезд") or ""
        volost = item.get("volost") or item.get("Волость") or ""
        parish_orth_19 = item.get("parish_east19") or ""
        parish_roman_19 = item.get("parish_roman19") or ""

        # Parishes (primary / 20th c.)
        parish_orth_20 = item.get("parish_east20") or item.get("parish_east") or item.get("parish_orthodox") or item.get("Приход (прав., нач. XX в.)") or item.get("Приход (прав.)") or ""
        parish_roman_20 = item.get("parish_roman20") or item.get("parish_catholic") or item.get("Приход (кат., нач. XX в.)") or item.get("Приход (кат.)") or ""
        primary_parish = item.get("parish") or ""

        parish_orth = parish_orth_20 or parish_orth_19 or primary_parish
        parish_cath = parish_roman_20 or parish_roman_19 or parish_roman_18

        # Statistics & Coordinates
        households = str(item.get("households") or "")
        inhabitants = str(item.get("inhabitants") or "")
        data_year = item.get("data_year")
        lat = item.get("lat") or item.get("latitude")
        lon = item.get("lon") or item.get("lng") or item.get("longitude")

        # Stable human-readable slug
        base_name = name_be or name_ru
        slug = slugify(f"{base_name}-{district}-{imported_count + 1}")

        cur.execute("""
        INSERT INTO settlements (
            slug, name_be, name_ru, settlement_type, district, selsoviet,
            powiat_18, estate_18, owner_18, estate_19, owner_19,
            belonging, uezd, volost, parish_orthodox, parish_catholic,
            lat, lon, alt_names, region, selsoviet_81, selsoviet_11,
            households, inhabitants, parish_roman_18, parish_orth_19,
            parish_roman_19, parish_orth_20, parish_roman_20, data_year, gubernia
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            slug, name_be, name_ru, stype, district, selsoviet,
            powiat_18, estate_18, owner_18, estate_19, owner_19,
            belonging, uezd, volost, parish_orth, parish_cath,
            lat, lon, alt_names, region, selsoviet_81, selsoviet_11,
            households, inhabitants, parish_roman_18, parish_orth_19,
            parish_roman_19, parish_orth_20, parish_roman_20, data_year, gubernia
        ))
        sid = cur.lastrowid
        imported_count += 1

        # Surnames: can be list or string
        surnames_raw = item.get("person") or item.get("surnames") or item.get("прозвішчы") or []
        surnames_list = []
        if isinstance(surnames_raw, str):
            # Split comma, semicolon, space
            surnames_list = [s.strip() for s in re.split(r'[,;\n]+', surnames_raw) if s.strip()]
        elif isinstance(surnames_raw, list):
            surnames_list = [str(s).strip() for s in surnames_raw if str(s).strip()]

        for sname in surnames_list:
            if not sname:
                continue
            sslug = slugify(sname)
            cur.execute("INSERT OR IGNORE INTO surnames (slug, surname_be, normalized) VALUES (?, ?, ?)",
                        (sslug, sname, sname.lower()))
            cur.execute("SELECT id FROM surnames WHERE slug = ?", (sslug,))
            s_row = cur.fetchone()
            if s_row:
                cur.execute("INSERT OR IGNORE INTO settlement_surnames (settlement_id, surname_id, mention_source) VALUES (?, ?, ?)",
                            (sid, s_row[0], "Архіўныя спісы"))

    conn.commit()
    conn.close()
    print(f"Successfully imported {imported_count} settlements into database!")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        import_dump(sys.argv[1])
    else:
        print("Usage: py import_json.py <path_to_dump.json>")
