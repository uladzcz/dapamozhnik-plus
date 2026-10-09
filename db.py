"""
Database module for Dapamozhnik Plus.
Supports all historical fields from helper.archonline.by:
- XVIII c.: Павет, Маёнтак, Уласнік
- XIX c.: Имение (до 1863), Владелец, Принадлежность, Уезд, Волость
- XX c. / Religious: Приход (прав.), Приход (кат.)
- Administrative: Назва (бел./рус.), Раён, Сельсавет, Каардынаты
"""
import sqlite3
import re
from typing import List, Dict, Any, Optional

DB_PATH = "dapamozhnik.db"

def slugify(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^\w\-]', '', text)
    return text

def py_lower(s: Optional[str]) -> str:
    return s.lower() if s else ""

def py_norm(s: Optional[str]) -> str:
    if not s:
        return ""
    t = s.lower().strip()
    t = re.sub(r"[\’\ʼ\‘\`\´]", "'", t)
    t = t.replace('ё', 'е')
    return t

def py_fuzzy_norm(s: Optional[str]) -> str:
    if not s:
        return ""
    t = py_norm(s)
    t = t.replace('міер', 'мер').replace('миер', 'мер')
    t = t.replace('о', 'а')
    t = t.replace('ы', 'і')
    t = t.replace('я', 'е')
    t = t.replace('й', 'и')
    return t

import os
import zipfile

ZIP_PATH = "dapamozhnik.db.zip"

def ensure_db(db_path: str = DB_PATH):
    if not os.path.exists(db_path) and os.path.exists(ZIP_PATH):
        print(f"Распакоўка базы даных {ZIP_PATH} -> {db_path}...")
        with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
            zf.extractall(".")
        print("База даных паспяхова распакавана!")

def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.create_function("py_lower", 1, py_lower)
    conn.create_function("py_norm", 1, py_norm)
    conn.create_function("py_fuzzy_norm", 1, py_fuzzy_norm)
    return conn

def init_db(db_path: str = DB_PATH):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Drop old table to recreate with exact fields
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE,
        name_be TEXT,
        name_ru TEXT,
        settlement_type TEXT,
        district TEXT,
        selsoviet TEXT,
        powiat_18 TEXT,
        estate_18 TEXT,
        owner_18 TEXT,
        estate_19 TEXT,
        owner_19 TEXT,
        belonging TEXT,
        uezd TEXT,
        volost TEXT,
        parish_orthodox TEXT,
        parish_catholic TEXT,
        is_abandoned INTEGER DEFAULT 0,
        lat REAL,
        lon REAL
    );
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_st_name_be ON settlements(name_be);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_st_name_ru ON settlements(name_ru);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_st_district ON settlements(district);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_st_estate18 ON settlements(estate_18);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_st_estate19 ON settlements(estate_19);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_st_parish_orth ON settlements(parish_orthodox);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_st_parish_cath ON settlements(parish_catholic);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_st_volost ON settlements(volost);")

    # Surnames table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS surnames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE,
        surname_be TEXT NOT NULL,
        normalized TEXT NOT NULL
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sn_be ON surnames(surname_be);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sn_normalized ON surnames(normalized);")

    # Settlement <-> Surname link
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settlement_surnames (
        settlement_id INTEGER,
        surname_id INTEGER,
        mention_source TEXT,
        PRIMARY KEY (settlement_id, surname_id),
        FOREIGN KEY (settlement_id) REFERENCES settlements(id) ON DELETE CASCADE,
        FOREIGN KEY (surname_id) REFERENCES surnames(id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ss_st ON settlement_surnames(settlement_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ss_sn ON settlement_surnames(surname_id);")

    conn.commit()
    conn.close()
    print("Database initialized with exact historical fields.")

if __name__ == "__main__":
    init_db()
