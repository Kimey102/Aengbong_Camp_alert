import requests, json
B="https://camp.xticket.kr"; E="a12d6508ae5ea0562923cb1f2762761f3413ab4c988a6c8aa92ea7873e263bec"
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36","Accept-Language":"ko-KR,ko;q=0.9"}
X={"X-Requested-With":"XMLHttpRequest","Accept":"application/json, text/javascript, */*; q=0.01","Origin":B,"Referer":f"{B}/web/main?shopEncode={E}","Content-Type":"application/x-www-form-urlencoded; charset=UTF-8"}
def out(k,v): print(f"::warning::{k}: {str(v)[:250]}", flush=True)
s=requests.Session(); s.headers.update(UA)
r=s.get(f"{B}/web/main?shopEncode={E}", headers={"Accept":"text/html"}, timeout=20)
out("main", f"{r.status_code} len={len(r.text)} hist={[h.status_code for h in r.history]}")
try: out("ip", requests.get("https://ipinfo.io/json",timeout=10).json())
except Exception as e: out("ip", e)
si=s.post(B+"/Web/Book/GetShopInformation.json", data={"shop_encode":E}, headers=X, timeout=20).json()
d=si.get("data",{}); out("shop", {k:d.get(k) for k in ["play_month","book_days","reservation_yn","book_kind"]})
for m in [d.get("play_month"), "202611"]:
    t=s.post(B+"/Web/Book/GetBookPlayDate.json", data={"play_month":m}, headers=X, timeout=20).text
    out(f"playdate {m}", t[:200])
t=s.post(B+"/Web/Book/GetBookProductGroup.json", data={"start_date":"20261113","end_date":"20261113"}, headers=X, timeout=20).text
out("groups", t[:150])
