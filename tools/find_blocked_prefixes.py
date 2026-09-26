import requests, urllib3
import sys, io
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
session = requests.Session()
session.headers.update(headers)

be_upper = ["А", "Б", "В", "Г", "Д", "Е", "Ё", "Ж", "З", "І", "Й", "К", "Л", "М", "Н", "О", "П", "Р", "С", "Т", "У", "Ў", "Ф", "Х", "Ц", "Ч", "Ш", "Ы", "Э", "Ю", "Я"]
be_lower = ["а","б","в","г","д","е","ё","ж","з","і","й","к","л","м","н","о","п","р","с","т","у","ў","ф","х","ц","ч","ш","ы","ь","э","ю","я"]

all_2 = [u + l for u in be_upper for l in be_lower]
print(f"Testing {len(all_2)} 2-letter combinations with ThreadPoolExecutor...")

def check(q):
    try:
        r = session.post('https://helper.archonline.by/data', data={'q': q, 'm': 0, 't': '0', 'u': '1', 's': ''}, verify=False, timeout=5)
        return q, r.status_code
    except Exception:
        return q, -1

blocked_2 = []
with ThreadPoolExecutor(max_workers=8) as ex:
    futures = [ex.submit(check, q) for q in all_2]
    for fut in as_completed(futures):
        q, code = fut.result()
        if code == 403:
            blocked_2.append(q)

print(f"Finished! Blocked 2-letter prefixes (403): {sorted(blocked_2)}")
