import requests
import msgpack
import urllib3
import time
import sys, io
from concurrent.futures import ThreadPoolExecutor
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
urllib3.disable_warnings()

URL = "https://helper.archonline.by/data"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Origin': 'https://helper.archonline.by',
    'Referer': 'https://helper.archonline.by/'
}

s = requests.Session()
s.headers.update(headers)

def fetch_q(q):
    data = {'q': q, 'm': '2', 't': '0', 'u': '1', 's': ''}
    for _ in range(3):
        try:
            r = s.post(URL, data=data, verify=False, timeout=8)
            if r.status_code == 200:
                res = msgpack.unpackb(r.content, raw=False)
                return q, len(res)
            elif r.status_code in (403, 429):
                time.sleep(1.5)
        except Exception:
            time.sleep(1.0)
    return q, 0

prefixes = [f'Ка{c}' for c in 'абвгдеёжзійклмнопрстуўфхцчшыьэюя']
t0 = time.time()
with ThreadPoolExecutor(max_workers=5) as ex:
    results = list(ex.map(fetch_q, prefixes))

elapsed = time.time() - t0
print(f"Fetched {len(prefixes)} queries in {elapsed:.2f}s ({len(prefixes)/elapsed:.1f} req/s)")
for q, cnt in results[:10]:
    print(f"  {q}: {cnt} items")
