"""
FastAPI Backend for Dapamozhnik Plus.
Supports:
- Intelligent ranked search (Name-only by default, All-fields optional)
- Interactive parishes, estates, and permanent Wikipedia deep linking
- Multi-surname comparison with distinct color palettes & unified mask
- Suffix (Фіналі) geographical analysis & density
- District density percentages categorized into 4 tiers
- Geographic hierarchy grouping (Modern district, XIX c. Uezd, XVIII c. Powiat, Volost)
- GeoJSON & CSV exports
"""
import sqlite3
import csv
import io
import json
import re
from typing import Optional, List
from collections import Counter
from fastapi import FastAPI, Query, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from db import get_db_connection, slugify, py_lower, py_norm, py_fuzzy_norm

app = FastAPI(
    title="Дапаможнік+ (Гістарычныя паселішчы і прозвішчы Беларусі)",
    description="Адкрыты архіўны партал без абмежавання 12 вынікаў і з пастаяннымі спасылкамі для Вікіпедыі."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache for total historical settlements per district
_DISTRICT_TOTALS = None

def get_district_totals() -> dict:
    global _DISTRICT_TOTALS
    if _DISTRICT_TOTALS is None:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT district, COUNT(*) FROM settlements WHERE district != '' GROUP BY district")
        _DISTRICT_TOTALS = {row[0]: row[1] for row in cur.fetchall()}
        conn.close()
    return _DISTRICT_TOTALS

def to_ascii_filename(text: str) -> str:
    trans = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'і': 'i', 'й': 'j', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ў': 'w', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'ы': 'y',
        'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    res = []
    for ch in text.lower():
        res.append(trans.get(ch, ch))
    s = "".join(res)
    s = re.sub(r'[^a-zA-Z0-9_\-]', '', s)
    return s or "export"

PALETTE = [
    {"name": "Чырвоны", "hex": "#ef4444", "light": "#fee2e2"},
    {"name": "Сіні", "hex": "#3b82f6", "light": "#dbeafe"},
    {"name": "Зялёны", "hex": "#10b981", "light": "#d1fae5"},
    {"name": "Бурштынавы", "hex": "#f59e0b", "light": "#fef3c7"},
    {"name": "Фіялетавы", "hex": "#8b5cf6", "light": "#ede9fe"},
    {"name": "Ружовы", "hex": "#ec4899", "light": "#fce7f3"},
    {"name": "Бірузовы", "hex": "#06b6d4", "light": "#cffafe"},
]

def classify_density(pct: float) -> dict:
    if pct >= 15.0:
        return {"level": "very_high", "label": "Вельмі высокая (≥15%)", "color": "#dc2626", "bg": "#fef2f2"}
    elif pct >= 7.0:
        return {"level": "high", "label": "Высокая (7–14.9%)", "color": "#ea580c", "bg": "#fff7ed"}
    elif pct >= 3.0:
        return {"level": "medium", "label": "Сярэдняя (3–6.9%)", "color": "#ca8a04", "bg": "#fefce8"}
    else:
        return {"level": "rare", "label": "Рэдкая (<3%)", "color": "#64748b", "bg": "#f8fafc"}

def build_wildcard_pattern(raw: str) -> str:
    s = raw.strip()
    if not s:
        return ""
    has_wildcard = any(c in s for c in ("*", "?", "%", "_"))
    if has_wildcard:
        needs_trailing_wildcard = not s.startswith("*") and not s.startswith("%") and not s.endswith("*") and not s.endswith("%")
        pat = s.replace("*", "%").replace("?", "_")
        if needs_trailing_wildcard:
            pat = pat + "%"
        return pat.lower()
    return s.lower()

@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1, description="Пошукавы запыт"),
    type: str = Query("all", pattern="^(all|settlements|surnames)$"),
    all_fields: bool = Query(False, description="Шукаць па ўсіх палях (раён, воласць, маёнтак, прыход)"),
    limit: Optional[int] = Query(500, description="Ліміт вынікаў")
):
    conn = get_db_connection()
    cur = conn.cursor()
    query_clean = q.strip()
    norm_q = py_norm(query_clean)
    fuzzy_q = py_fuzzy_norm(query_clean)

    stop_words = {'в', 'в.', 'вёска', 'веска', 'дер', 'дер.', 'деревня', 'д.', 'што', 'каля', 'пад', 'ля', 'урочышча', 'пасёлак', 'хутар', 'засценак'}
    raw_tokens = [w for w in re.split(r'[\s\-,]+', query_clean) if len(w) > 1 and py_norm(w) not in stop_words]
    tokens = [py_norm(w) for w in raw_tokens]

    results = {"settlements": [], "surnames": []}

    if type in ("all", "settlements"):
        if not all_fields:
            if len(tokens) > 1:
                # Multi-token matching (handles reversed word order, spaces instead of hyphens, compound names)
                conds = []
                params = []
                for tok in tokens:
                    ftok = py_fuzzy_norm(tok)
                    conds.append("(py_norm(name_be) LIKE ? OR py_norm(name_ru) LIKE ? OR py_fuzzy_norm(name_be) LIKE ? OR py_fuzzy_norm(name_ru) LIKE ?)")
                    params.extend([f"%{tok}%", f"%{tok}%", f"%{ftok}%", f"%{ftok}%"])
                
                where_clause = " AND ".join(conds)
                cur.execute(f"""
                    SELECT id, slug, name_be, name_ru, settlement_type, district, selsoviet,
                           powiat_18, estate_18, owner_18, estate_19, owner_19, belonging,
                           uezd, volost, parish_orthodox, parish_catholic, lat, lon,
                           CASE 
                               WHEN py_norm(name_be) = ? OR py_norm(name_ru) = ? THEN 1
                               WHEN py_fuzzy_norm(name_be) = ? OR py_fuzzy_norm(name_ru) = ? THEN 2
                               ELSE 3
                           END as rank_score
                    FROM settlements
                    WHERE {where_clause}
                    ORDER BY rank_score ASC, (settlement_type = 'Город') DESC, name_be ASC
                    LIMIT ?
                """, (norm_q, norm_q, fuzzy_q, fuzzy_q, *params, limit))
            else:
                # Single word search with exact, prefix, substring, and phonetic fuzzy fallback
                cur.execute("""
                    SELECT id, slug, name_be, name_ru, settlement_type, district, selsoviet,
                           powiat_18, estate_18, owner_18, estate_19, owner_19, belonging,
                           uezd, volost, parish_orthodox, parish_catholic, lat, lon,
                           CASE 
                               WHEN py_norm(name_be) = ? OR py_norm(name_ru) = ? THEN 1
                               WHEN py_norm(name_be) LIKE ? OR py_norm(name_ru) LIKE ? THEN 2
                               WHEN py_fuzzy_norm(name_be) = ? OR py_fuzzy_norm(name_ru) = ? THEN 3
                               WHEN py_fuzzy_norm(name_be) LIKE ? OR py_fuzzy_norm(name_ru) LIKE ? THEN 4
                               ELSE 5
                           END as rank_score
                    FROM settlements
                    WHERE py_norm(name_be) LIKE ? OR py_norm(name_ru) LIKE ?
                       OR py_fuzzy_norm(name_be) LIKE ? OR py_fuzzy_norm(name_ru) LIKE ?
                    ORDER BY rank_score ASC, (settlement_type = 'Город') DESC, name_be ASC
                    LIMIT ?
                """, (norm_q, norm_q, f"{norm_q}%", f"{norm_q}%", fuzzy_q, fuzzy_q, f"{fuzzy_q}%", f"{fuzzy_q}%",
                      f"%{norm_q}%", f"%{norm_q}%", f"%{fuzzy_q}%", f"%{fuzzy_q}%", limit))
        else:
            # All fields search: Search name, district, volost, uezd, estate, parish
            cur.execute("""
                SELECT id, slug, name_be, name_ru, settlement_type, district, selsoviet,
                       powiat_18, estate_18, owner_18, estate_19, owner_19, belonging,
                       uezd, volost, parish_orthodox, parish_catholic, lat, lon,
                       CASE 
                           WHEN py_norm(name_be) = ? OR py_norm(name_ru) = ? THEN 1
                           WHEN py_norm(name_be) LIKE ? OR py_norm(name_ru) LIKE ? THEN 2
                           ELSE 3
                       END as rank_score
                FROM settlements
                WHERE py_norm(name_be) LIKE ? OR py_norm(name_ru) LIKE ? OR py_norm(district) LIKE ?
                   OR py_norm(volost) LIKE ? OR py_norm(uezd) LIKE ? OR py_norm(estate_18) LIKE ? OR py_norm(estate_19) LIKE ?
                   OR py_norm(parish_orthodox) LIKE ? OR py_norm(parish_catholic) LIKE ?
                   OR py_fuzzy_norm(name_be) LIKE ? OR py_fuzzy_norm(name_ru) LIKE ?
                ORDER BY rank_score ASC, (settlement_type = 'Город') DESC, name_be ASC
                LIMIT ?
            """, (norm_q, norm_q, f"{norm_q}%", f"{norm_q}%",
                  f"%{norm_q}%", f"%{norm_q}%", f"%{norm_q}%",
                  f"%{norm_q}%", f"%{norm_q}%", f"%{norm_q}%", f"%{norm_q}%",
                  f"%{norm_q}%", f"%{norm_q}%", f"%{fuzzy_q}%", f"%{fuzzy_q}%", limit))

        results["settlements"] = [dict(row) for row in cur.fetchall()]

    if type in ("all", "surnames"):
        if any(c in query_clean for c in ("*", "?")):
            w_pat = build_wildcard_pattern(query_clean)
            cur.execute("""
                SELECT s.id, s.slug, s.surname_be, COUNT(ss.settlement_id) as settlements_count,
                       1 as rank_score
                FROM surnames s
                LEFT JOIN settlement_surnames ss ON s.id = ss.surname_id
                WHERE py_norm(s.surname_be) LIKE ? OR py_fuzzy_norm(s.surname_be) LIKE ?
                GROUP BY s.id
                ORDER BY settlements_count DESC, s.surname_be ASC
                LIMIT ?
            """, (w_pat, w_pat, limit))
        else:
            cur.execute("""
                SELECT s.id, s.slug, s.surname_be, COUNT(ss.settlement_id) as settlements_count,
                       CASE 
                           WHEN py_norm(s.surname_be) = ? THEN 1
                           WHEN py_norm(s.surname_be) LIKE ? THEN 2
                           WHEN py_fuzzy_norm(s.surname_be) = ? THEN 3
                           ELSE 4
                       END as rank_score
                FROM surnames s
                LEFT JOIN settlement_surnames ss ON s.id = ss.surname_id
                WHERE py_norm(s.surname_be) LIKE ? OR py_fuzzy_norm(s.surname_be) LIKE ? OR s.normalized LIKE ?
                GROUP BY s.id
                ORDER BY rank_score ASC, settlements_count DESC, s.surname_be ASC
                LIMIT ?
            """, (norm_q, f"{norm_q}%", fuzzy_q, f"%{norm_q}%", f"%{fuzzy_q}%", f"%{norm_q}%", limit))
        results["surnames"] = [dict(row) for row in cur.fetchall()]

    conn.close()
    return results

@app.get("/api/settlements/viewport")
def get_settlements_in_viewport(
    south: float = Query(...),
    west: float = Query(...),
    north: float = Query(...),
    east: float = Query(...),
    limit: int = Query(350)
):
    """Returns settlements with coordinates within a map bounding box for local browsing."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, slug, name_be, name_ru, settlement_type, district, selsoviet,
               powiat_18, estate_18, owner_18, estate_19, owner_19, belonging,
               uezd, volost, parish_orthodox, parish_catholic, lat, lon
        FROM settlements
        WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
        LIMIT ?
    """, (min(south, north), max(south, north), min(west, east), max(west, east), limit))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"count": len(rows), "settlements": rows}

@app.get("/api/parish")
def get_by_parish(name: str = Query(...)):
    """Returns all settlements belonging to a specific Orthodox or Catholic parish."""
    conn = get_db_connection()
    cur = conn.cursor()
    pat = f"%{name.strip()}%"
    cur.execute("""
        SELECT * FROM settlements
        WHERE parish_orthodox LIKE ? OR parish_catholic LIKE ?
        ORDER BY district, name_be, name_ru
    """, (pat, pat))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"parish": name, "total": len(rows), "settlements": rows}

@app.get("/api/estate")
def get_by_estate(name: str = Query(...)):
    """Returns all settlements belonging to a specific Estate (18th or 19th c.)."""
    conn = get_db_connection()
    cur = conn.cursor()
    pat = f"%{name.strip()}%"
    cur.execute("""
        SELECT * FROM settlements
        WHERE estate_18 LIKE ? OR estate_19 LIKE ?
        ORDER BY district, name_be, name_ru
    """, (pat, pat))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"estate": name, "total": len(rows), "settlements": rows}

@app.get("/api/settlement/{identifier}")
def get_settlement(identifier: str):
    conn = get_db_connection()
    cur = conn.cursor()

    if identifier.isdigit():
        cur.execute("SELECT * FROM settlements WHERE id = ?", (int(identifier),))
    else:
        cur.execute("SELECT * FROM settlements WHERE slug = ?", (identifier,))
    
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Населены пункт не знойдзены")

    settlement = dict(row)

    cur.execute("""
        SELECT s.id, s.slug, s.surname_be, ss.mention_source
        FROM surnames s
        JOIN settlement_surnames ss ON s.id = ss.surname_id
        WHERE ss.settlement_id = ?
        ORDER BY s.surname_be ASC
    """, (settlement["id"],))
    settlement["surnames"] = [dict(r) for r in cur.fetchall()]

    display_name = settlement['name_be'] if settlement['name_be'] != 'не існуе' else settlement['name_ru']
    settlement["wiki_link"] = f"https://helper-plus.by/settlement/{settlement['slug']}"
    settlement["wiki_ref"] = f"<ref>{{{{артыкул |аўтар = Дапаможнік+ |загаловак = {display_name} ({settlement['district']} раён) |выданне = Гістарычныя паселішчы і прозвішчы Беларусі |url = {settlement['wiki_link']}}}}}</ref>"

    conn.close()
    return settlement

@app.get("/api/surname/{identifier}")
def get_surname(identifier: str):
    conn = get_db_connection()
    cur = conn.cursor()

    if identifier.isdigit():
        cur.execute("SELECT * FROM surnames WHERE id = ?", (int(identifier),))
    else:
        cur.execute("SELECT * FROM surnames WHERE slug = ? OR surname_be = ?", (identifier, identifier))
    
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Прозвішча не знойдзена")

    surname = dict(row)

    cur.execute("""
        SELECT st.*, ss.mention_source
        FROM settlements st
        JOIN settlement_surnames ss ON st.id = ss.settlement_id
        WHERE ss.surname_id = ?
        ORDER BY st.district, st.name_be, st.name_ru
    """, (surname["id"],))
    settlements = [dict(r) for r in cur.fetchall()]
    surname["settlements"] = settlements
    surname["total_occurrences"] = len(settlements)

    # Compute district density relative to total settlements in district
    totals = get_district_totals()
    d_counter = Counter(s["district"] for s in settlements if s.get("district"))
    
    density_list = []
    for dist, count in d_counter.items():
        total_in_dist = totals.get(dist, 0)
        pct = round((count / total_in_dist) * 100, 1) if total_in_dist > 0 else 0.0
        cls = classify_density(pct)
        density_list.append({
            "district": dist,
            "count": count,
            "total_district_settlements": total_in_dist,
            "percentage": pct,
            "level": cls["level"],
            "level_label": cls["label"],
            "color": cls["color"],
            "bg": cls["bg"]
        })
    
    density_list.sort(key=lambda x: (x["percentage"], x["count"]), reverse=True)
    surname["district_density"] = density_list

    surname["wiki_link"] = f"https://helper-plus.by/surname/{surname['slug']}"
    surname["wiki_ref"] = f"<ref>{{{{артыкул |аўтар = Дапаможнік+ |загаловак = Арэал прозвішча {surname['surname_be']} |выданне = Гістарычныя паселішчы і прозвішчы Беларусі |url = {surname['wiki_link']}}}}}</ref>"

    conn.close()
    return surname

@app.get("/api/analysis/density")
def get_density_analysis(
    surnames: str = Query(..., description="Прозвішчы або маскі праз коску, напр. 'Літвін,Ліцвін' ці 'Каралёў', 'Літ*', 'Ч*хо'")
):
    """Calculates geographic density for one or multiple surnames relative to total district settlements."""
    conn = get_db_connection()
    cur = conn.cursor()

    items = [x.strip() for x in surnames.split(",") if x.strip()]
    if not items:
        conn.close()
        return {"districts": [], "total_matches": 0, "points": []}

    conditions = []
    params = []
    for it in items:
        pat = build_wildcard_pattern(it)
        if any(c in it for c in ("*", "?", "%", "_")):
            conditions.append("(py_lower(sn.surname_be) LIKE ?)")
            params.append(pat)
        else:
            conditions.append("(py_lower(sn.surname_be) = ? OR sn.slug = ?)")
            params.extend([it.lower(), slugify(it)])

    where_clause = " OR ".join(conditions)

    cur.execute(f"""
        SELECT DISTINCT st.id, st.slug, st.name_be, st.name_ru, st.settlement_type, st.district, st.uezd, st.powiat_18, st.volost, st.selsoviet, st.lat, st.lon, sn.surname_be
        FROM settlements st
        JOIN settlement_surnames ss ON st.id = ss.settlement_id
        JOIN surnames sn ON ss.surname_id = sn.id
        WHERE {where_clause}
        ORDER BY st.district, st.name_be
    """, params)

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    totals = get_district_totals()

    # Group distinct settlements by district
    st_by_dist = {}
    unique_settlements_dict = {}

    for r in rows:
        st_id = r["id"]
        if st_id not in unique_settlements_dict:
            unique_settlements_dict[st_id] = r

        d = r.get("district")
        if d:
            if d not in st_by_dist:
                st_by_dist[d] = {}
            if st_id not in st_by_dist[d]:
                st_by_dist[d][st_id] = {
                    "id": r["id"],
                    "slug": r.get("slug"),
                    "name_be": r["name_be"],
                    "name_ru": r.get("name_ru"),
                    "settlement_type": r.get("settlement_type"),
                    "district": r.get("district"),
                    "selsoviet": r.get("selsoviet"),
                    "volost": r.get("volost"),
                    "lat": r.get("lat"),
                    "lon": r.get("lon"),
                    "surnames": [r["surname_be"]]
                }
            else:
                if r["surname_be"] not in st_by_dist[d][st_id]["surnames"]:
                    st_by_dist[d][st_id]["surnames"].append(r["surname_be"])

    density_list = []
    for dist, st_map in st_by_dist.items():
        total_in_dist = totals.get(dist, 0)
        u_count = len(st_map)
        pct = round((u_count / total_in_dist) * 100, 1) if total_in_dist > 0 else 0.0
        cls = classify_density(pct)
        settlements_list = list(st_map.values())
        settlements_list.sort(key=lambda x: x["name_be"])

        density_list.append({
            "district": dist,
            "count": u_count,
            "total_district_settlements": total_in_dist,
            "percentage": pct,
            "level": cls["level"],
            "level_label": cls["label"],
            "color": cls["color"],
            "bg": cls["bg"],
            "settlements": settlements_list
        })

    density_list.sort(key=lambda x: (x["percentage"], x["count"]), reverse=True)

    points = []
    for s_info in unique_settlements_dict.values():
        pt = dict(s_info)
        pt["color"] = "#059669"
        pt["surname"] = pt.get("surname_be")
        points.append(pt)

    return {
        "query": surnames,
        "total_mentions": len(rows),
        "unique_settlements": len(points),
        "districts": density_list,
        "points": points
    }

@app.get("/api/analysis/multi")
def compare_surnames(
    surnames: str = Query(..., description="Спіс прозвішчаў праз коску, напр. 'Літвін,Ліцвін' ці 'Казак,Казлоўскі'"),
    combine: bool = Query(False, description="Аб'яднаць у адзін супольны этнічны арэал")
):
    """
    Multi-surname comparison:
    - If combine=False: Assigns distinct colors (Red, Blue, Green, Orange, Purple) to each surname.
    - If combine=True: Merges into a single unified ethnic distribution area.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    items = [x.strip() for x in surnames.split(",") if x.strip()]
    if not items:
        conn.close()
        return {"groups": [], "combined": None}

    groups = []
    all_points = []
    totals = get_district_totals()

    for idx, raw_sn in enumerate(items[:7]):
        color_info = PALETTE[idx % len(PALETTE)]
        target_color = PALETTE[0]["hex"] if combine else color_info["hex"]

        is_wildcard = any(c in raw_sn for c in ("*", "?", "%", "_"))
        if is_wildcard:
            pat = build_wildcard_pattern(raw_sn)
            cur.execute("""
                SELECT DISTINCT st.id, st.slug, st.name_be, st.name_ru, st.settlement_type, st.district, st.selsoviet,
                                st.powiat_18, st.estate_18, st.owner_18, st.estate_19, st.owner_19, st.belonging,
                                st.uezd, st.volost, st.parish_orthodox, st.parish_catholic, st.lat, st.lon, sn.surname_be
                FROM settlements st
                JOIN settlement_surnames ss ON st.id = ss.settlement_id
                JOIN surnames sn ON ss.surname_id = sn.id
                WHERE py_lower(sn.surname_be) LIKE ?
                ORDER BY st.district, st.name_be
            """, (pat,))
        else:
            cur.execute("""
                SELECT DISTINCT st.id, st.slug, st.name_be, st.name_ru, st.settlement_type, st.district, st.selsoviet,
                                st.powiat_18, st.estate_18, st.owner_18, st.estate_19, st.owner_19, st.belonging,
                                st.uezd, st.volost, st.parish_orthodox, st.parish_catholic, st.lat, st.lon, sn.surname_be
                FROM settlements st
                JOIN settlement_surnames ss ON st.id = ss.settlement_id
                JOIN surnames sn ON ss.surname_id = sn.id
                WHERE py_lower(sn.surname_be) = ? OR sn.slug = ?
                ORDER BY st.district, st.name_be
            """, (raw_sn.lower(), slugify(raw_sn)))

        st_rows = [dict(r) for r in cur.fetchall()]
        for st in st_rows:
            st["color"] = target_color
            st["surname"] = st["surname_be"]
            all_points.append(st)

        # Group distinct settlements by district
        st_by_dist = {}
        for st in st_rows:
            d = st.get("district")
            if d:
                if d not in st_by_dist:
                    st_by_dist[d] = set()
                st_by_dist[d].add(st["id"])

        dist_density = []
        for dist, st_id_set in st_by_dist.items():
            tot = totals.get(dist, 0)
            u_count = len(st_id_set)
            pct = min(100.0, round((u_count / tot) * 100, 1)) if tot > 0 else 0.0
            cls = classify_density(pct)
            dist_density.append({
                "district": dist,
                "count": u_count,
                "total": tot,
                "pct": pct,
                "level": cls["level"],
                "color": cls["color"]
            })
        dist_density.sort(key=lambda x: (x["pct"], x["count"]), reverse=True)

        groups.append({
            "name": raw_sn,
            "color": target_color,
            "color_name": color_info["name"],
            "count": len(st_rows),
            "settlements": st_rows,
            "top_districts": dist_density[:5]
        })

    # Combined summary with distinct settlements
    unique_st_ids = set(p["id"] for p in all_points)
    combined_by_dist = {}
    for p in all_points:
        d = p.get("district")
        if d:
            if d not in combined_by_dist:
                combined_by_dist[d] = set()
            combined_by_dist[d].add(p["id"])

    combined_density = []
    for dist, st_id_set in combined_by_dist.items():
        tot = totals.get(dist, 0)
        u_count = len(st_id_set)
        pct = min(100.0, round((u_count / tot) * 100, 1)) if tot > 0 else 0.0
        cls = classify_density(pct)
        combined_density.append({
            "district": dist,
            "count": u_count,
            "total": tot,
            "percentage": pct,
            "level": cls["level"],
            "level_label": cls["label"],
            "color": cls["color"],
            "bg": cls["bg"]
        })
    combined_density.sort(key=lambda x: (x["percentage"], x["count"]), reverse=True)

    conn.close()

    return {
        "combine": combine,
        "groups": groups,
        "total_unique_settlements": len(unique_st_ids),
        "combined_density": combined_density[:15],
        "all_points": all_points
    }

@app.get("/api/analysis/suffix")
def get_by_suffix(
    suffix: str = Query(..., description="Суфікс або некалькі праз коску, напр. 'віч,іч' ці 'ёнак,онак'")
):
    """
    Analyzes geographic distribution of Belarusian surname suffixes (фіналі):
    -віч/-іч, -ёнак/-онак, -енка, -ман, -еў/-оў, -ук/-юк/-чук, -скі/-цкі, etc.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    parts = [p.strip().lstrip("-").lstrip("%") for p in suffix.split(",") if p.strip()]
    if not parts:
        conn.close()
        return {"suffix": suffix, "surnames_count": 0, "settlements_count": 0}

    # Find matching surnames
    conds = ["sn.surname_be LIKE ?" for _ in parts]
    pats = [f"%{p}" for p in parts]

    cur.execute(f"""
        SELECT sn.id, sn.surname_be, COUNT(ss.settlement_id) as freq
        FROM surnames sn
        LEFT JOIN settlement_surnames ss ON sn.id = ss.surname_id
        WHERE {" OR ".join(conds)}
        GROUP BY sn.id
        ORDER BY freq DESC
    """, pats)

    matching_surnames = [dict(r) for r in cur.fetchall()]
    top_surnames = matching_surnames[:25]

    # Find settlements with these surnames
    cur.execute(f"""
        SELECT DISTINCT st.id, st.name_be, st.name_ru, st.settlement_type, st.district, st.selsoviet,
                        st.powiat_18, st.estate_18, st.owner_18, st.estate_19, st.owner_19,
                        st.uezd, st.volost, st.parish_orthodox, st.parish_catholic, st.lat, st.lon, sn.surname_be
        FROM settlements st
        JOIN settlement_surnames ss ON st.id = ss.settlement_id
        JOIN surnames sn ON ss.surname_id = sn.id
        WHERE {" OR ".join(conds)}
    """, pats)

    st_rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    totals = get_district_totals()
    st_by_dist = {}
    for st in st_rows:
        d = st.get("district")
        if d:
            if d not in st_by_dist:
                st_by_dist[d] = set()
            st_by_dist[d].add(st["id"])

    density_list = []
    for dist, st_id_set in st_by_dist.items():
        tot = totals.get(dist, 0)
        u_count = len(st_id_set)
        pct = min(100.0, round((u_count / tot) * 100, 1)) if tot > 0 else 0.0
        cls = classify_density(pct)
        density_list.append({
            "district": dist,
            "count": u_count,
            "total_district_settlements": tot,
            "percentage": pct,
            "level": cls["level"],
            "level_label": cls["label"],
            "color": cls["color"],
            "bg": cls["bg"]
        })

    density_list.sort(key=lambda x: (x["percentage"], x["count"]), reverse=True)

    return {
        "suffix": suffix,
        "surnames_count": len(matching_surnames),
        "settlements_count": len(st_rows),
        "unique_settlements": len(set(s["id"] for s in st_rows)),
        "top_surnames": top_surnames,
        "districts_density": density_list[:20],
        "points": st_rows
    }

@app.get("/api/analysis/suffix-competition")
def compare_suffix_competition(
    suffixes: str = Query(..., description="Групы суфіксаў праз кропку з коскай, напр. 'ёнак,онак;ук,юк;еня,эня'"),
    margin_threshold: float = Query(0.1, description="Мінімальная перавага для дамінавання (0.1 = 10%)")
):
    """
    Computes territorial dominance and competition between multiple surname suffixes.
    Calculates district-level winners, dominance share %, and victory margin.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Precompute district centroids
    cur.execute("""
        SELECT district, AVG(lat) as lat, AVG(lon) as lon, COUNT(*) as total_settlements
        FROM settlements 
        WHERE district != '' AND lat IS NOT NULL AND lon IS NOT NULL
        GROUP BY district
    """)
    districts_info = {r[0]: {"lat": r[1], "lon": r[2], "total": r[3]} for r in cur.fetchall()}

    groups_raw = [g.strip() for g in suffixes.split(";") if g.strip()]
    if not groups_raw:
        conn.close()
        return {"groups": [], "districts_dominance": [], "points": []}

    groups = []
    group_district_settlements = []
    all_points = []

    for idx, raw_grp in enumerate(groups_raw[:7]):
        color_info = PALETTE[idx % len(PALETTE)]
        parts = [p.strip().lstrip("-").lstrip("%") for p in raw_grp.split(",") if p.strip()]
        conds = ["sn.surname_be LIKE ?" for _ in parts]
        pats = [f"%{p}" for p in parts]

        # Fetch all matching settlements
        cur.execute(f"""
            SELECT DISTINCT st.id, st.slug, st.name_be, st.name_ru, st.settlement_type, st.district, st.lat, st.lon, sn.surname_be
            FROM settlements st
            JOIN settlement_surnames ss ON st.id = ss.settlement_id
            JOIN surnames sn ON ss.surname_id = sn.id
            WHERE ({" OR ".join(conds)}) AND st.district != ''
        """, pats)
        st_rows = [dict(r) for r in cur.fetchall()]

        # Distinct settlements per district
        st_by_dist = {}
        seen_points_in_group = set()
        for st in st_rows:
            st["color"] = color_info["hex"]
            st["group_idx"] = idx
            st["group_label"] = raw_grp
            st["surname"] = st["surname_be"]
            if st["id"] not in seen_points_in_group:
                seen_points_in_group.add(st["id"])
                all_points.append(st)
            
            d = st.get("district")
            if d:
                if d not in st_by_dist:
                    st_by_dist[d] = set()
                st_by_dist[d].add(st["id"])

        dist_counts = {d: len(s_ids) for d, s_ids in st_by_dist.items()}
        group_district_settlements.append(dist_counts)

        groups.append({
            "group_idx": idx,
            "label": raw_grp,
            "color": color_info["hex"],
            "color_name": color_info["name"],
            "total_settlements": len(set(st["id"] for st in st_rows)),
            "total_mentions": len(st_rows)
        })

    conn.close()

    # Calculate dominance for each of the 118 districts
    districts_dominance = []
    wins_summary = {g["label"]: 0 for g in groups}
    ties_count = 0

    for dist, d_info in districts_info.items():
        counts = [group_district_settlements[i].get(dist, 0) for i in range(len(groups))]
        tot = sum(counts)
        if tot == 0:
            continue

        ranked = sorted([(counts[i], groups[i]["label"], groups[i]["color"], i) for i in range(len(counts))], reverse=True)
        top_cnt, top_label, top_color, top_idx = ranked[0]
        second_cnt = ranked[1][0] if len(ranked) > 1 else 0
        second_label = ranked[1][1] if len(ranked) > 1 else ""
        second_color = ranked[1][2] if len(ranked) > 1 else ""

        dominance_share = round(top_cnt / tot, 3)
        margin = round((top_cnt - second_cnt) / tot, 3)

        if margin < margin_threshold:
            dominant_label = f"Нічыя 50/50 ({ranked[0][1]} ~ {ranked[1][1]})"
            assigned_color = "#94a3b8"  # slate-400
            is_tie = True
            ties_count += 1
        else:
            dominant_label = top_label
            assigned_color = top_color
            is_tie = False
            wins_summary[top_label] += 1

        districts_dominance.append({
            "district": dist,
            "lat": d_info["lat"],
            "lon": d_info["lon"],
            "total_district_settlements": d_info["total"],
            "total_matches": tot,
            "dominant_label": dominant_label,
            "dominant_color": assigned_color,
            "top_color": top_color,
            "second_color": second_color,
            "tie_colors": [top_color, second_color] if is_tie and second_color else [],
            "tie_labels": [top_label, second_label] if is_tie and second_label else [],
            "dominant_group_idx": top_idx if not is_tie else -1,
            "dominance_share": round(dominance_share * 100, 1),
            "margin": round(margin * 100, 1),
            "is_tie": is_tie,
            "counts": {groups[i]["label"]: counts[i] for i in range(len(groups))}
        })

    districts_dominance.sort(key=lambda x: (x["margin"], x["total_matches"]), reverse=True)

    return {
        "groups": groups,
        "summary": {
            "wins": wins_summary,
            "ties": ties_count,
            "total_districts": len(districts_dominance)
        },
        "districts_dominance": districts_dominance,
        "points": all_points
    }

@app.get("/api/export/geojson")
def export_geojson(surname_slug: Optional[str] = None):
    conn = get_db_connection()
    cur = conn.cursor()

    if surname_slug:
        cur.execute("""
            SELECT st.* FROM settlements st
            JOIN settlement_surnames ss ON st.id = ss.settlement_id
            JOIN surnames sn ON ss.surname_id = sn.id
            WHERE sn.slug = ? OR sn.surname_be = ?
        """, (surname_slug, surname_slug))
    else:
        cur.execute("SELECT * FROM settlements LIMIT 1000")
    
    rows = cur.fetchall()
    features = []
    for r in rows:
        d = dict(r)
        if d.get("lat") and d.get("lon"):
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [d["lon"], d["lat"]]
                },
                "properties": {k: v for k, v in d.items() if k not in ("lat", "lon")}
            })
    conn.close()

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    safe_name = to_ascii_filename(surname_slug) if surname_slug else "all"
    return JSONResponse(
        content=geojson,
        headers={"Content-Disposition": f"attachment; filename=dapamozhnik_{safe_name}.geojson"}
    )

@app.get("/api/export/csv")
def export_csv(surname_slug: Optional[str] = None):
    conn = get_db_connection()
    cur = conn.cursor()

    if surname_slug:
        cur.execute("""
            SELECT st.*, sn.surname_be
            FROM settlements st
            JOIN settlement_surnames ss ON st.id = ss.settlement_id
            JOIN surnames sn ON ss.surname_id = sn.id
            WHERE sn.slug = ? OR sn.surname_be = ?
        """, (surname_slug, surname_slug))
    else:
        cur.execute("SELECT * FROM settlements LIMIT 1000")
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))

    safe_name = to_ascii_filename(surname_slug) if surname_slug else "all"
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=dapamozhnik_{safe_name}.csv"}
    )

@app.post("/api/compare")
async def compare_database(file: UploadFile = File(...)):
    content = await file.read()
    text = content.decode("utf-8-sig", errors="ignore")
    
    user_surnames = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if row:
            for cell in row:
                candidate = cell.strip()
                if candidate and len(candidate) > 2 and not candidate.isnumeric():
                    user_surnames.append(candidate)
    
    user_surnames = list(set(user_surnames))

    conn = get_db_connection()
    cur = conn.cursor()

    matched_clusters = {}
    matched_surnames = []

    for surname in user_surnames:
        cur.execute("""
            SELECT sn.surname_be, st.id as settlement_id, st.name_be, st.name_ru, st.district, st.lat, st.lon
            FROM surnames sn
            JOIN settlement_surnames ss ON sn.id = ss.surname_id
            JOIN settlements st ON ss.settlement_id = st.id
            WHERE sn.surname_be LIKE ? OR sn.normalized LIKE ?
        """, (f"%{surname}%", f"%{surname.lower()}%"))
        hits = cur.fetchall()
        if hits:
            matched_surnames.append(surname)
            for h in hits:
                sid = h["settlement_id"]
                display_name = h["name_be"] if h["name_be"] != "не існуе" else h["name_ru"]
                if sid not in matched_clusters:
                    matched_clusters[sid] = {
                        "settlement_id": sid,
                        "name_be": display_name,
                        "district": h["district"],
                        "lat": h["lat"],
                        "lon": h["lon"],
                        "matched_surnames": []
                    }
                if h["surname_be"] not in matched_clusters[sid]["matched_surnames"]:
                    matched_clusters[sid]["matched_surnames"].append(h["surname_be"])

    conn.close()

    sorted_clusters = sorted(
        matched_clusters.values(),
        key=lambda x: len(x["matched_surnames"]),
        reverse=True
    )

    return {
        "uploaded_surnames_count": len(user_surnames),
        "matched_surnames_count": len(matched_surnames),
        "matched_surnames": matched_surnames,
        "clusters": sorted_clusters
    }

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
