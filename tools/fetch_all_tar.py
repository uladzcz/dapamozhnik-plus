import requests, msgpack, urllib3
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
s = requests.Session()
s.headers.update(headers)

# Common Belarusian toponym roots for Тар*:
queries = [
    'Тартак', 'Тартакі', 'Тартачек', 'Тарнова', 'Тарноўка', 'Тарноўцы', 'Таркан', 'Тарканы',
    'Тарлаўшчына', 'Тарпаў', 'Тарсуны', 'Тарчылава', 'Тарчылава Старое', 'Тарханы',
    'Тарасава', 'Тарасово', 'Тарасенкі', 'Тарасенки', 'Тарахаўка', 'Тараховка',
    'Тарановічы', 'Тарановичи', 'Тарасевічы', 'Тарасевичи', 'Тарані', 'Тарани',
    'Тараскава', 'Тарасково', 'Тарасы', 'Тарашчукі', 'Тарашчуки',
    'Тарапешы', 'Таропец', 'Тарпец', 'Тарбеева', 'Тарбейка',
    'Тарлакі', 'Тарлічы', 'Тармяны', 'Тарнова', 'Тарнаполь'
]

results = {}
for q in queries:
    try:
        r = s.post('https://helper.archonline.by/data', data={'q': q, 'm': 1, 't': '0', 'u': '1', 's': ''}, verify=False, timeout=5)
        if r.status_code == 200:
            items = msgpack.unpackb(r.content, raw=False)
            if items:
                print(f"'{q}': {len(items)} found")
                for it in items:
                    be = (it.get(b'place_be') or b'').decode('utf-8', errors='replace')
                    ru = (it.get(b'place_ru') or b'').decode('utf-8', errors='replace')
                    d = (it.get(b'd') or b'').decode('utf-8', errors='replace')
                    key = (be, ru, d, it.get(b'lat'), it.get(b'lon'))
                    results[key] = it
        else:
            print(f"'{q}': status {r.status_code}")
    except Exception as e:
        print(f"'{q}': error {e}")

print(f"\nTotal unique settlements collected: {len(results)}")
for (be, ru, d, lat, lon) in sorted(results.keys()):
    print(f"  {be} / {ru} ({d} р-н) [{lat}, {lon}]")
