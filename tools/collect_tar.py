import requests, msgpack, urllib3
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
s = requests.Session()
s.headers.update(headers)

be_lower = ["а","б","в","г","д","е","ё","ж","з","і","й","к","л","м","н","о","п","р","с","т","у","ў","ф","х","ц","ч","ш","ы","ь","э","ю","я"]

print("Testing all 4-letter combinations 'тар' + letter:")
all_found = {}

for c in be_lower:
    q = "тар" + c
    r = s.post('https://helper.archonline.by/data', data={'q': q, 'm': 1, 't': '0', 'u': '1', 's': ''}, verify=False, timeout=5)
    if r.status_code == 200:
        res = msgpack.unpackb(r.content, raw=False)
        # Filter items that actually start with or contain Тар
        for it in res:
            be = (it.get(b'place_be') or b'').decode('utf-8', errors='replace')
            ru = (it.get(b'place_ru') or b'').decode('utf-8', errors='replace')
            d = (it.get(b'd') or b'').decode('utf-8', errors='replace')
            key = (be, ru, d, it.get(b'lat'), it.get(b'lon'))
            if key not in all_found:
                all_found[key] = it
        print(f"  {q}: {len(res)} results (total unique so far: {len(all_found)})")
    else:
        print(f"  {q}: HTTP {r.status_code}")

print(f"\nTotal unique settlements found across all 'тар*': {len(all_found)}")
for k in sorted(all_found.keys())[:30]:
    print(" ", k[0], "/", k[1], f"({k[2]} р-н)")
