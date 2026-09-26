import requests, msgpack, urllib3
import sqlite3
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
s = requests.Session()
s.headers.update(headers)

stems = [
    'артак', 'артач', 'арнов', 'арасав', 'арасов', 'арасенк', 'арахоўк', 'араховк',
    'аркан', 'арчылаў', 'орчилов', 'арлаўшч', 'ардунов', 'арбейк', 'арсун', 'армян',
    'арановіч', 'аранович', 'арасевіч', 'арасевич', 'арапеш', 'арпец', 'аропец',
    'аран-Подг', 'аракан'
]

collected = {}

for stem in stems:
    try:
        r = s.post('https://helper.archonline.by/data', data={'q': stem, 'm': 1, 't': '0', 'u': '1', 's': ''}, verify=False, timeout=5)
        if r.status_code == 200:
            res = msgpack.unpackb(r.content, raw=False)
            for it in res:
                be = (it.get(b'place_be') or b'').decode('utf-8', errors='replace').strip()
                ru = (it.get(b'place_ru') or b'').decode('utf-8', errors='replace').strip()
                n = (it.get(b'n') or b'').decode('utf-8', errors='replace').strip()
                d = (it.get(b'd') or b'').decode('utf-8', errors='replace').strip()
                lat = it.get(b'lat')
                lon = it.get(b'lon')
                # Keep only ones that actually start with or are Тар* / Тор*
                names_to_check = [be, ru, n]
                is_tar = any('Тар' in name or 'Тор' in name or 'Тара' in name for name in names_to_check)
                if is_tar:
                    key = (be, ru, d, lat, lon)
                    if key not in collected:
                        collected[key] = it
        else:
            print(f"Stem '{stem}' HTTP {r.status_code}")
    except Exception as e:
        print(f"Stem '{stem}' error: {e}")

print(f"\nSuccessfully collected {len(collected)} authentic Тар* settlements from helper.archonline.by:")
for (be, ru, d, lat, lon) in sorted(collected.keys()):
    print(f"  • {be} / {ru} ({d} р-н) [{lat}, {lon}]")
