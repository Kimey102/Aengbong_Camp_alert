#!/usr/bin/env python3
"""엑스티켓(camp.xticket.kr) 캠핑장 빈자리 감시 → 텔레그램 알림.

동작 순서
1. 메인 페이지(main?shopEncode=...)를 열어 세션 쿠키를 받는다.
2. GetBookPlayDate.json 으로 월별 날짜별 잔여 수(book_remain_count)를 조회한다.
3. 감시 대상 날짜 중 잔여가 있는 날만 GetBookProduct010001.json 으로
   시설(데크/글램핑 등)별 예약 가능 사이트(select_yn == "1") 이름을 확인한다.
4. 직전 상태(state.json)와 비교해 새로 열린 사이트가 있으면 텔레그램으로 알린다.

설정은 모두 환경변수로 받는다(README 참고).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import sys
import time
from pathlib import Path

import requests

BASE = "https://camp.xticket.kr"
KST = dt.timezone(dt.timedelta(hours=9))

SHOP_ENCODE = os.environ.get(
    "SHOP_ENCODE",
    "a12d6508ae5ea0562923cb1f2762761f3413ab4c988a6c8aa92ea7873e263bec",
)
STAYS = os.environ.get("STAYS", "").strip()                    # 예: 20261113:2,20261120:2 (입실일:박수)
TARGET_DATES = os.environ.get("TARGET_DATES", "").strip()      # 예: 20261107,20261114 (1박)
WATCH_MONTHS = os.environ.get("WATCH_MONTHS", "").strip()      # 예: 202611,202612
WEEKDAYS = os.environ.get("WEEKDAYS", "fri,sat").strip()       # WATCH_MONTHS와 함께 사용
GROUPS = os.environ.get("GROUPS", "").strip()                  # 예: 데크캠핑장 (비우면 전체)
LOOP_MINUTES = float(os.environ.get("LOOP_MINUTES", "0"))      # 한 번 실행에서 반복할 시간(분)
INTERVAL_SEC = int(os.environ.get("INTERVAL_SEC", "60"))       # 반복 간격(초)
STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
FORCE_REPORT = os.environ.get("FORCE_REPORT", "") in ("1", "true", "yes")

WEEKDAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6,
}
WEEKDAY_KO = "월화수목금토일"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


class SessionExpired(Exception):
    pass


def log(msg: str) -> None:
    now = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def main_url() -> str:
    return f"{BASE}/web/main?shopEncode={SHOP_ENCODE}"


# ---------------------------------------------------------------- 사이트 조회
class XTicket:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.shop_name = ""

    def open(self) -> None:
        r = self.s.get(main_url(), timeout=20)
        r.raise_for_status()
        info = self._post("/Web/Book/GetShopInformation.json", {})
        self.shop_name = (info.get("data") or {}).get("shop_name", "") or self.shop_name

    def _post(self, path: str, data: dict) -> dict:
        r = self.s.post(
            BASE + path, data=data, timeout=20, headers={"Referer": main_url()}
        )
        r.raise_for_status()
        j = r.json()
        err = j.get("error") or j.get("error1")
        if err:
            if j.get("redirect") or "세션" in str(err.get("message", "")):
                raise SessionExpired(err.get("message"))
            raise RuntimeError(f"{path}: {err.get('message')}")
        return j

    def month_remain(self, yyyymm: str) -> dict[str, int]:
        j = self._post("/Web/Book/GetBookPlayDate.json", {"play_month": yyyymm})
        return {
            d["play_date"]: int(d.get("book_remain_count") or 0)
            for d in j["data"]["bookPlayDateList"]
        }

    def groups(self, date: str) -> list[dict]:
        j = self._post(
            "/Web/Book/GetBookProductGroup.json",
            {"start_date": date, "end_date": date},
        )
        return j["data"]["bookProductGroupList"]

    def available_sites(self, group_code: str, date: str, nights: int = 1) -> list[str]:
        """입실일부터 nights박 동안 연속으로 비어 있는 사이트 이름."""
        end = (dt.datetime.strptime(date, "%Y%m%d") + dt.timedelta(days=nights - 1)).strftime("%Y%m%d")
        j = self._post(
            "/Web/Book/GetBookProduct010001.json",
            {
                "product_group_code": group_code,
                "start_date": date,
                "end_date": end,
                "book_days": str(nights),
                "two_stay_days": "0",
            },
        )
        return [
            p["product_name"]
            for p in j["data"]["bookProductList"]
            if str(p.get("select_yn")) == "1"
        ]


# ---------------------------------------------------------------- 대상 날짜
def nights_of(key: str) -> list[str]:
    """'20261113:2' -> ['20261113', '20261114'] (숙박하는 밤들)."""
    start, _, n = key.partition(":")
    d0 = dt.datetime.strptime(start, "%Y%m%d")
    return [(d0 + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(int(n or 1))]


def target_dates(today: dt.date) -> list[str]:
    """감시 대상 키 목록. 1박은 '20261107', 연박은 '20261113:2' 형식."""
    dates: set[str] = set()
    if STAYS:
        dates.update(x.strip() for x in STAYS.split(",") if x.strip())
    if TARGET_DATES:
        dates.update(x.strip() for x in TARGET_DATES.split(",") if x.strip())
    if WATCH_MONTHS:
        wanted = {
            WEEKDAY_MAP[w.strip().lower()]
            for w in WEEKDAYS.split(",")
            if w.strip().lower() in WEEKDAY_MAP
        } or set(range(7))
        for m in (x.strip() for x in WATCH_MONTHS.split(",") if x.strip()):
            d = dt.date(int(m[:4]), int(m[4:6]), 1)
            while d.month == int(m[4:6]):
                if d.weekday() in wanted:
                    dates.add(d.strftime("%Y%m%d"))
                d += dt.timedelta(days=1)
    return sorted(x for x in dates if x >= today.strftime("%Y%m%d"))


def _fmt_day(d: dt.date) -> str:
    return f"{d.month}/{d.day}({WEEKDAY_KO[d.weekday()]})"


def fmt_date(key: str) -> str:
    start, _, n = key.partition(":")
    d = dt.datetime.strptime(start, "%Y%m%d").date()
    nights = int(n or 1)
    if nights <= 1:
        return _fmt_day(d)
    return f"{_fmt_day(d)}~{_fmt_day(d + dt.timedelta(days=nights))} {nights}박"


# ---------------------------------------------------------------- 상태/알림
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def telegram(text: str) -> None:
    if not (TG_TOKEN and TG_CHAT):
        log("텔레그램 설정이 없어 콘솔에만 출력합니다:\n" + text)
        return
    r = requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    if not r.ok:
        log(f"텔레그램 전송 실패: {r.status_code} {r.text[:200]}")


# ---------------------------------------------------------------- 1회 점검
def check_once(api: XTicket, dates: list[str]) -> dict[str, dict[str, list[str]]]:
    """{날짜: {시설명: [가능 사이트...]}} — 잔여가 없는 날짜는 빈 dict."""
    months = sorted({n[:6] for d in dates for n in nights_of(d)})
    remain: dict[str, int] = {}
    for m in months:
        remain.update(api.month_remain(m))

    wanted_groups = {g.strip() for g in GROUPS.split(",") if g.strip()}
    result: dict[str, dict[str, list[str]]] = {}
    for d in dates:
        result[d] = {}
        nights = nights_of(d)
        if any(remain.get(n, 0) <= 0 for n in nights):
            continue  # 하룻밤이라도 만석이면 연박 불가
        for g in api.groups(nights[0]):
            name = g["product_group_name"]
            if wanted_groups and name not in wanted_groups:
                continue
            sites = api.available_sites(g["product_group_code"], nights[0], len(nights))
            if sites:
                result[d][name] = sites
            time.sleep(0.5)
    return result


def diff_and_notify(prev: dict, cur: dict, first_run: bool) -> None:
    title = api_name()
    if first_run or FORCE_REPORT:
        lines = [f"[{title}] 감시 상태 보고"]
        for d, groups in cur.items():
            if groups:
                cnt = ", ".join(f"{g} {len(s)}곳" for g, s in groups.items())
                lines.append(f"- {fmt_date(d)}: {cnt}")
            else:
                lines.append(f"- {fmt_date(d)}: 빈자리 없음")
        lines.append(f"\n예약: {main_url()}")
        telegram("\n".join(lines))
        return

    new_lines = []
    for d, groups in cur.items():
        before = prev.get(d, {})
        for g, sites in groups.items():
            opened = [s for s in sites if s not in before.get(g, [])]
            if opened:
                shown = ", ".join(opened[:8]) + (" 외" if len(opened) > 8 else "")
                new_lines.append(f"- {fmt_date(d)} {g}: {shown}")
    if new_lines:
        telegram(
            f"[{title}] 빈자리 발생\n" + "\n".join(new_lines) + f"\n\n예약: {main_url()}"
        )
        log("알림 전송:\n" + "\n".join(new_lines))
    else:
        log("새로 열린 자리 없음")


_API: XTicket | None = None


def api_name() -> str:
    return (_API.shop_name if _API and _API.shop_name else "캠핑장")


def main() -> int:
    global _API
    today = dt.datetime.now(KST).date()
    dates = target_dates(today)
    if not dates:
        print("::error::감시할 날짜가 없습니다. Variables에 STAYS(또는 TARGET_DATES, WATCH_MONTHS)를 등록하세요.", flush=True)
        return 1
    log(f"감시 대상 {len(dates)}일: {', '.join(fmt_date(d) for d in dates)}")

    state = load_state()
    first_run = not state
    _API = XTicket()
    _API.open()

    deadline = time.time() + LOOP_MINUTES * 60
    while True:
        try:
            cur = check_once(_API, dates)
        except SessionExpired:
            log("세션 만료, 다시 접속합니다")
            _API = XTicket()
            _API.open()
            cur = check_once(_API, dates)
        diff_and_notify(state, cur, first_run)
        state, first_run = cur, False
        save_state(state)
        if time.time() + INTERVAL_SEC > deadline:
            break
        time.sleep(INTERVAL_SEC + random.uniform(-5, 5))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.exceptions.RequestException as e:
        print(f"::error::캠핑장 사이트 접속 실패({type(e).__name__}): {str(e)[:300]}", flush=True)
        raise
    except Exception as e:
        print(f"::error::{type(e).__name__}: {str(e)[:300]}", flush=True)
        raise
