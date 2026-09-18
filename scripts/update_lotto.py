"""
로또 대시보드 자동 업데이트 스크립트

하는 일:
  1. data/lotto_history.csv 에서 마지막 회차를 확인하고, 다음 회차가 이미 추첨되었으면
     당첨번호 + 당첨점(1등/2등) 데이터를 동행복권에서 가져와 CSV에 이어붙인다.
  2. 최신 뉴스 8건을 구글 뉴스 RSS에서 가져온다.
  3. 위 모든 걸 합쳐 대시보드가 그대로 fetch() 할 수 있는 docs/latest.json 을 새로 만든다.

이 스크립트는 반드시 저장소 루트 디렉터리에서 실행해야 한다 (data/, docs/ 상대경로 사용).
    예) python scripts/update_lotto.py
구글 계정/서비스 키 등 외부 인증이 전혀 필요 없다.
"""

import csv
import json
import os
import time
from collections import defaultdict
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests

LOTTO_CSV = "data/lotto_history.csv"
SHOP_CSV = "data/shop_history.csv"
OUTPUT_JSON = "docs/latest.json"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


# ----------------------------------------------------------------------
# CSV 유틸
# ----------------------------------------------------------------------
def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]  # header, data


def append_csv(path, rows):
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)


# ----------------------------------------------------------------------
# 1. 동행복권에서 다음 회차 당첨번호 가져오기
# ----------------------------------------------------------------------
def fetch_lotto_round(epsd, retries=3, delay=2):
    url = "https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do"
    params = {
        "srchDir": "center",
        "srchLtEpsd": str(epsd),
        "_": str(int(time.time() * 1000)),
    }
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, headers=REQUEST_HEADERS, params=params, timeout=10)
            lst = res.json().get("data", {}).get("list", [])
            return next((x for x in lst if x.get("ltEpsd") == epsd), None)
        except Exception as e:
            print(f"⚠️ {epsd}회차 당첨번호 조회 실패 ({attempt}/{retries}차 시도): {e}")
            if attempt < retries:
                time.sleep(delay)
    print(f"❌ {epsd}회차 당첨번호 조회 최종 실패 — 일시적 네트워크 문제일 수 있습니다. 다음 실행에서 다시 시도됩니다.")
    return None


# ----------------------------------------------------------------------
# 2. 동행복권에서 해당 회차 당첨점(1등/2등) 가져오기
# ----------------------------------------------------------------------
def fetch_shop_round(epsd, retries=3, delay=2):
    url = "https://www.dhlottery.co.kr/wnprchsplcsrch/selectLtWnShp.do"
    params = {"srchWnShpRnk": "all", "srchLtEpsd": str(epsd)}
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, headers=REQUEST_HEADERS, params=params, timeout=10)
            return res.json().get("data", {}).get("list", [])
        except Exception as e:
            print(f"⚠️ {epsd}회차 당첨점 조회 실패 ({attempt}/{retries}차 시도): {e}")
            if attempt < retries:
                time.sleep(delay)
    print(f"❌ {epsd}회차 당첨점 조회 최종 실패")
    return []


# ----------------------------------------------------------------------
# 3. 로또 관련 최신 뉴스 (구글 뉴스 RSS, 키 불필요)
# ----------------------------------------------------------------------
def fetch_news(limit=8):
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://news.google.com/rss/search?q={quote('로또 당첨번호 1등')}&hl=ko&gl=KR&ceid=KR:ko"
    items = []
    try:
        res = requests.get(url, headers=headers, timeout=5)
        root = ET.fromstring(res.content)
        for item in root.findall(".//item")[:limit]:
            title_el = item.find("title")
            link_el = item.find("link")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            if title and link:
                items.append({"title": title, "url": link})
    except Exception as e:
        print(f"⚠️ 뉴스 수집 오류: {e}")
    return items


# ----------------------------------------------------------------------
# 메인
# ----------------------------------------------------------------------
def main():
    _, lotto_rows = read_csv(LOTTO_CSV)
    last_epsd = int(lotto_rows[-1][0])
    target = last_epsd + 1
    added_any = False

    # 밀린 회차가 여러 개 있어도(예: 시드 데이터가 오래됐거나, 자동 실행이 한 번 빠졌거나)
    # 한 번의 실행에서 최신 회차까지 전부 따라잡는다.
    while True:
        print(f"🔄 {target}회차 확인 중...")
        new_round = fetch_lotto_round(target)
        if not new_round:
            print(f"ℹ️ {target}회차는 아직 추첨 전이거나 데이터가 없습니다. 여기서 멈춥니다.")
            break

        lotto_row = [
            new_round.get("ltEpsd"), new_round.get("ltRflYmd"),
            new_round.get("tm1WnNo"), new_round.get("tm2WnNo"), new_round.get("tm3WnNo"),
            new_round.get("tm4WnNo"), new_round.get("tm5WnNo"), new_round.get("tm6WnNo"),
            new_round.get("bnsWnNo"), new_round.get("wholEpsdSumNtslAmt"),
            new_round.get("rnk1WnNope"), new_round.get("rnk1WnAmt"),
            new_round.get("rnk2WnNope"), new_round.get("rnk2WnAmt"),
            new_round.get("rnk3WnNope"), new_round.get("rnk3WnAmt"),
            new_round.get("rnk4WnNope"), new_round.get("rnk4WnAmt"),
            new_round.get("rnk5WnNope"), new_round.get("rnk5WnAmt"),
        ]
        append_csv(LOTTO_CSV, [lotto_row])
        lotto_rows.append([str(v) for v in lotto_row])
        print(f"✅ {target}회차 당첨번호 추가 완료")

        shop_list = fetch_shop_round(target)
        new_shop_rows = []
        for shop in shop_list:
            rnk = shop.get("wnShpRnk")
            if rnk in (1, 2):
                new_shop_rows.append([
                    target, shop.get("rnum", ""), rnk,
                    (shop.get("atmtPsvYnTxt") or "").strip(),
                    (shop.get("atmtPsvYn") or "").strip(),
                    (shop.get("shpNm") or "").strip(),
                    (shop.get("ltShpId") or "").strip(),
                    (shop.get("shpTelno") or "").strip(),
                    (shop.get("slrOperSttsCd") or "").strip(),
                    (shop.get("tm1ShpLctnAddr") or "").strip(),
                    (shop.get("tm2ShpLctnAddr") or "").strip(),
                    (shop.get("tm3ShpLctnAddr") or "").strip(),
                    (shop.get("shpAddr") or "").strip(),
                    shop.get("shpLat", ""), shop.get("shpLot", ""),
                    (shop.get("l645LtNtslYn") or "").strip(),
                    (shop.get("st5LtNtslYn") or "").strip(),
                    (shop.get("st10LtNtslYn") or "").strip(),
                    (shop.get("st20LtNtslYn") or "").strip(),
                    (shop.get("pt720NtslYn") or "").strip(),
                ])
        if new_shop_rows:
            append_csv(SHOP_CSV, new_shop_rows)
            n1 = sum(1 for r in new_shop_rows if str(r[2]) == "1")
            n2 = sum(1 for r in new_shop_rows if str(r[2]) == "2")
            print(f"✅ {target}회차 당첨점 추가 완료 (1등 {n1}곳 / 2등 {n2}곳)")
        else:
            print(f"⚠️ {target}회차 당첨점 데이터가 아직 서버에 없습니다.")

        added_any = True
        target += 1
        time.sleep(1)  # 동행복권 서버에 짧은 시간 안에 요청이 몰리지 않도록 약간 대기

    if not added_any:
        print("ℹ️ 새로 추가된 회차가 없습니다. 기존 데이터로 뉴스만 갱신합니다.")

    # ---- 최신 상태로 다시 읽어서 latest.json 생성 ----
    _, lotto_rows = read_csv(LOTTO_CSV)
    _, shop_rows = read_csv(SHOP_CSV)

    # 원본 CSV에 같은 회차가 중복으로 들어있는 경우를 대비해 걸러낸다 (첫 항목만 유지)
    def dedup_by_round(rows):
        seen = set()
        out = []
        for r in rows:
            if r and r[0] not in seen:
                seen.add(r[0])
                out.append(r)
        return out

    lotto_rows = dedup_by_round(lotto_rows)

    latest = lotto_rows[-1]
    latest_epsd = str(latest[0])

    def clean(v):
        return str(v).replace(",", "").strip()

    latest_obj = {
        "drawNo": latest[0],
        "drawDate": latest[1],
        "numbers": latest[2:8],
        "bonusNo": latest[8],
        "totSellAmt": clean(latest[9]) if len(latest) > 9 else "",
        "firstWinCount": clean(latest[10]) if len(latest) > 10 else "",
        "firstWinAmt": clean(latest[11]) if len(latest) > 11 else "",
        "secondWinCount": clean(latest[12]) if len(latest) > 12 else "",
        "secondWinAmt": clean(latest[13]) if len(latest) > 13 else "",
    }

    recent50 = lotto_rows[-50:]

    # 이번 회차 1등 매장 (같은 매장이 여러 게임에 당첨되면 currentWins로 집계)
    this_round_rank1 = [s for s in shop_rows if s[0] == latest_epsd and s[2] == "1"]
    current_wins = defaultdict(int)
    rep_row = {}
    for s in this_round_rank1:
        sid = s[6]
        current_wins[sid] += 1
        rep_row[sid] = s

    # 전체 이력 기준 매장별 누적 1등/2등 횟수 (판매점ID 기준)
    cum1, cum2 = defaultdict(int), defaultdict(int)
    for s in shop_rows:
        sid = s[6]
        if s[2] == "1":
            cum1[sid] += 1
        elif s[2] == "2":
            cum2[sid] += 1

    latest_shops = []
    for sid, row in rep_row.items():
        region = row[9] if len(row) > 9 and row[9] else ""
        if not region and len(row) > 12 and row[12]:
            region = row[12].split(" ")[0]
        latest_shops.append({
            "type": row[3] or "자동",
            "region": region,
            "name": row[5],
            "address": row[12],
            "count1": cum1[sid],
            "count2": cum2[sid],
            "currentWins": current_wins[sid],
        })
    latest_shops.sort(key=lambda x: -x["count1"])

    output = {
        "status": "success",
        "latest": latest_obj,
        "recent50": recent50,
        "latestShops": latest_shops,
        "latestNews": fetch_news(),
        "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    print(f"🎉 latest.json 생성 완료 (기준 회차: {latest_epsd}회, 매장 {len(latest_shops)}곳, 뉴스 {len(output['latestNews'])}건)")


if __name__ == "__main__":
    main()
