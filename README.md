# 캠핑장 빈자리 알림 (camp-alert)

엑스티켓(camp.xticket.kr) 캠핑장의 예약 현황을 GitHub Actions로 주기적으로 조회하고, 감시 중인 날짜에 새로 빈자리가 생기면 텔레그램으로 알림을 보냅니다. 기본값은 앵봉산 가족캠핑장입니다.

## 동작 방식

1. 캠핑장 메인 페이지를 열어 세션을 받은 뒤, 월별 날짜별 잔여 수를 조회합니다.
2. 감시 날짜 중 잔여가 있는 날만 시설(데크캠핑장, 글램핑)별로 예약 가능한 사이트 이름을 확인합니다.
3. 직전 조회 결과와 비교해 새로 열린 사이트가 있을 때만 알림을 보냅니다(같은 자리로 반복 알림이 오지 않습니다).
4. 워크플로는 5분마다 시작되고, 한 번 실행될 때 약 4분 동안 1분 간격으로 조회합니다. 따라서 실제 조회 간격은 대략 1분입니다.

## 설정 순서

### 1. 텔레그램 봇 만들기

1. 텔레그램에서 `@BotFather`에게 `/newbot`을 보내고 안내대로 이름을 정하면 봇 토큰(`123456:ABC...` 형식)을 받습니다.
2. 방금 만든 봇과의 대화창을 열어 아무 메시지나 한 번 보냅니다.
3. 브라우저에서 `https://api.telegram.org/bot<봇토큰>/getUpdates`를 열면 결과 안의 `"chat":{"id":123456789,...}` 숫자가 Chat ID입니다.

### 2. GitHub 저장소 만들기

1. GitHub에서 새 저장소를 만들고 이 폴더의 파일(`monitor.py`, `.github/workflows/camp-alert.yml`, `README.md`, `.gitignore`)을 그대로 올립니다.
2. 저장소는 **Public**을 권장합니다. Public 저장소는 Actions 사용 시간이 무제한이지만, Private 저장소는 무료 한도(월 2,000분)를 금방 넘습니다. 토큰은 아래 Secrets에 들어가므로 코드가 공개되어도 노출되지 않습니다.

### 3. Secrets와 Variables 등록

저장소의 **Settings → Secrets and variables → Actions**에서 등록합니다.

| 구분 | 이름 | 값 예시 | 설명 |
|---|---|---|---|
| Secret | `TELEGRAM_BOT_TOKEN` | `123456:ABC...` | 봇 토큰 |
| Secret | `TELEGRAM_CHAT_ID` | `123456789` | Chat ID |
| Variable | `WATCH_MONTHS` | `202611,202612` | 감시할 달 |
| Variable | `WEEKDAYS` | `fri,sat` | 그 달 중 감시할 요일(기본 금·토, `금,토`처럼 한글도 가능) |
| Variable | `TARGET_DATES` | `20261107,20261114` | 특정 날짜만 지정할 때(위 두 항목과 함께 써도 됨) |
| Variable | `GROUPS` | `데크캠핑장` | 특정 시설만 볼 때(비우면 데크·글램핑 모두) |
| Variable | `SHOP_ENCODE` | (비워둠) | 다른 엑스티켓 캠핑장을 감시할 때 그 주소의 `shopEncode` 값 |
| Variable | `LOOP_MINUTES` / `INTERVAL_SEC` | `4` / `60` | 반복 시간과 조회 간격(기본값 권장) |

`WATCH_MONTHS`와 `TARGET_DATES` 중 하나는 반드시 설정해야 합니다. 지난 날짜는 자동으로 제외됩니다.

### 4. 첫 실행으로 확인

**Actions 탭 → camp-alert → Run workflow**를 누르면 현재 감시 날짜별 빈자리 현황이 텔레그램으로 한 번 옵니다. 이 메시지가 오면 설정이 끝난 것이고, 이후에는 5분마다 자동으로 돌면서 새 빈자리가 생길 때만 알림이 옵니다.

## 알아둘 점

- GitHub의 예약 실행은 서버 사정에 따라 몇 분씩 늦어지거나 가끔 건너뛸 수 있습니다. 몇 초 단위의 선착순 경쟁을 보장하지는 않습니다.
- 저장소에 60일 동안 커밋이 없으면 GitHub가 예약 실행을 자동으로 멈춥니다. 그 전에 아무 파일이나 수정해 커밋하거나 Actions 탭에서 다시 켜면 됩니다.
- GitHub Actions 서버는 해외에 있습니다. 혹시 캠핑장 사이트가 해외 접속을 막아 실행 로그에 연결 오류가 나면, 같은 스크립트를 집 컴퓨터에서 돌리는 방식으로 바꿔야 합니다.
- 조회 간격을 1분보다 짧게 줄이지 않는 것을 권합니다. 과도한 조회는 접속 차단이나 이용약관 문제로 이어질 수 있습니다.
- 알림만 보내고 예약은 하지 않습니다. 알림을 받으면 메시지의 링크로 들어가 직접 예약하시면 됩니다.

## 로컬에서 시험 실행

```bash
pip install requests
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... WATCH_MONTHS=202611 FORCE_REPORT=1 python monitor.py
```
