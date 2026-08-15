import requests
import time
import gspread
import json
import xml.etree.ElementTree as ET
from urllib.parse import quote
from oauth2client.service_account import ServiceAccountCredentials

print("🚀 로또 통합 자동화 & 초고속 JSON 캐시 생성 시스템 가동 중...")

# ==========================================
# 구글 시트 연결
# ==========================================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

try:
    creds = ServiceAccountCredentials.from_json_keyfile_name("lotto_key.json", scope)
    client = gspread.authorize(creds)

    SPREADSHEET_NAME = "로또_통합_DB"
    doc = client.open(SPREADSHEET_NAME)

    sheet_lotto = doc.worksheet("당첨번호")
    sheet_shop = doc.worksheet("명당")
    
    try:
        sheet_cache = doc.worksheet("JSON_CACHE")
    except:
        sheet_cache = doc.add_worksheet(title="JSON_CACHE", rows="10", cols="5")
        
except Exception as e:
    print(f"❌ 구글 시트 연결 실패: {e}")
    exit()


# ==========================================
# 1. 최신 뉴스 8건 수집 (Google 우선 + Bing 폴백 + 철저한 예외 처리)
# ==========================================
def fetch_lotto_news():
    print("📡 뉴스 수집 시도 중...")

    # 1순위: Google News RSS (안정적), 2순위: Bing RSS
    sources = [
        f"https://news.google.com/rss/search?q={quote('로또')}&hl=ko&gl=KR&ceid=KR:ko",
        f"https://www.bing.com/news/search?q={quote('로또')}&format=rss",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    }

    for rss_url in sources:
        try:
            res = requests.get(rss_url, headers=headers, timeout=10)

            # content-type이 xml이 아니면 차단/에러 페이지일 가능성 높음
            content_type = res.headers.get("Content-Type", "")
            if res.status_code != 200 or "xml" not in content_type:
                print(f"⚠️ {rss_url} 응답 이상 (status={res.status_code}, type={content_type})")
                continue

            root = ET.fromstring(res.content)
            news_items = []

            for item in root.findall('.//item')[:8]: # 8건 추출
                title_el = item.find('title')
                link_el = item.find('link')

                title = title_el.text.strip() if title_el is not None and title_el.text else None
                link = link_el.text.strip() if link_el is not None and link_el.text else None

                if title and link:
                    # 구글 뉴스의 경우 뒤에 붙는 ' - 언론사명' 제거
                    clean_title = title.split(' - ')[0] if 'google' in rss_url else title
                    news_items.append({"title": clean_title, "url": link})

            if news_items:
                print(f"✅ 뉴스 {len(news_items)}건 수집 성공 ({rss_url.split('/')[2]})")
                return news_items
            else:
                print(f"⚠️ {rss_url} 파싱은 됐지만 유효한 item 없음")

        except ET.ParseError as e:
            print(f"⚠️ XML 파싱 실패 ({rss_url}): {e}")
        except requests.RequestException as e:
            print(f"⚠️ 요청 실패 ({rss_url}): {e}")
        except Exception as e:
            print(f"⚠️ 알 수 없는 오류 ({rss_url}): {e}")

    print("⚠️ 모든 소스 실패, 기본값 뉴스로 대체합니다.")
    return [
        {"title": "[정보] 이번 주 로또 추첨 결과 및 당첨금 안내", "url": "https://dhlottery.co.kr"},
        {"title": "로또 1등 당첨자 배출 명당 모음", "url": "https://dhlottery.co.kr"},
        {"title": "동행복권 미수령 당첨금 확인 안내", "url": "https://dhlottery.co.kr"},
        {"title": "로또 당첨번호 통계 분석 및 패턴", "url": "https://dhlottery.co.kr"},
        {"title": "이번 주 로또, 수동 당첨자가 유독 많은 이유는?", "url": "https://dhlottery.co.kr"},
        {"title": "역대 로또 1등 최다 배출점 전국 지도 확인", "url": "https://dhlottery.co.kr"},
        {"title": "로또 당첨금 수령 방법 및 필요 서류 안내", "url": "https://dhlottery.co.kr"},
        {"title": "최근 10주간 가장 많이 나온 '뜨거운 숫자'는?", "url": "https://dhlottery.co.kr"}
    ]

# ==========================================
# 2. 당첨번호 수집 및 구글 시트 업데이트
# ==========================================
lotto_rows = sheet_lotto.get_all_values()
lotto_data = lotto_rows[1:]

last_epsd = int(lotto_data[-1][0])
target_epsd = last_epsd + 1

print(f"🔄 현재 시트 마지막 회차: {last_epsd}회")
print(f"📡 {target_epsd}회차 데이터 수집 시도 중...")

url_lotto = f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={target_epsd}"
res = requests.get(url_lotto, headers={"User-Agent": "Mozilla/5.0"})

try:
    data = res.json()
except Exception as e:
    data = {"returnValue": "fail"}

if data.get("returnValue") == "success":
    new_lotto_row = [
        str(data.get("drwNo")), data.get("drwNoDate"),
        str(data.get("drwtNo1")), str(data.get("drwtNo2")), str(data.get("drwtNo3")),
        str(data.get("drwtNo4")), str(data.get("drwtNo5")), str(data.get("drwtNo6")),
        str(data.get("bnusNo")),
        f"{data.get('totSellamnt'):,}",
        str(data.get("firstPrzwnerCo")), f"{data.get('firstWinamnt'):,}",
        "추후업데이트", "추후업데이트" 
    ]
    sheet_lotto.append_row(new_lotto_row)
    print(f"✅ {target_epsd}회차 당첨번호 구글 시트 업데이트 완료")
else:
    print(f"✅ {target_epsd}회차는 아직 추첨 전이거나 데이터가 없습니다.")

# ==========================================
# 3. 대시보드용 JSON 데이터 사전 연산 (초고속 캐싱)
# ==========================================
print("⚡ 대시보드 초고속 캐시(JSON) 생성 시작...")

all_lotto_rows = sheet_lotto.get_all_values()[1:]
all_shop_rows = sheet_shop.get_all_values()[1:]

latest_lotto = all_lotto_rows[-1]
latest_draw_no = latest_lotto[0]

# 1등 당첨점 추출
first_prize_shops = [s for s in all_shop_rows if len(s) > 2 and str(s[2]) == '1']

# 명당별 누적 1등 횟수 계산
store_win_counts = {}
for s in first_prize_shops:
    store_name = s[5] if len(s) > 5 else ''
    if store_name:
        store_win_counts[store_name] = store_win_counts.get(store_name, 0) + 1

# 최신 회차 1등 명당만 추출하여 누적 횟수 내림차순 정렬
latest_shops_raw = [s for s in first_prize_shops if len(s) > 0 and str(s[0]) == str(latest_draw_no)]
latest_shops_raw.sort(key=lambda s: store_win_counts.get(s[5] if len(s) > 5 else '', 0), reverse=True)

processed_shops = []
for s in latest_shops_raw:
    store_name = s[5] if len(s) > 5 else ''
    region_raw = s[9] if len(s) > 9 else ''
    sigungu_raw = s[10] if len(s) > 10 else ''
    sigungu_first = sigungu_raw.split()[0] if sigungu_raw else ''
    
    processed_shops.append({
        "type": s[3] if len(s) > 3 else "자동",
        "region": f"{region_raw} {sigungu_first}".strip(),
        "name": store_name,
        "count": store_win_counts.get(store_name, 1),
        "address": s[12] if len(s) > 12 else f"{region_raw} {sigungu_raw}"
    })

# 금액 콤마 제거 유틸
def clean_str(val):
    return str(val).replace(',', '').strip()

# 캐시 JSON 조립
dashboard_cache = {
    "status": "success",
    "latest": {
        "drawNo": latest_lotto[0],
        "drawDate": latest_lotto[1],
        "numbers": [latest_lotto[2], latest_lotto[3], latest_lotto[4], latest_lotto[5], latest_lotto[6], latest_lotto[7]],
        "bonusNo": latest_lotto[8],
        "totSellAmt": clean_str(latest_lotto[9]),
        "firstWinCount": clean_str(latest_lotto[10]),
        "firstWinAmt": clean_str(latest_lotto[11]),
        "secondWinCount": clean_str(latest_lotto[12]) if len(latest_lotto) > 12 else "0",
        "secondWinAmt": clean_str(latest_lotto[13]) if len(latest_lotto) > 13 else "0"
    },
    "recent50": all_lotto_rows[-50:][::-1],
    "latestShops": processed_shops,
    "latestNews": fetch_lotto_news() # 💡 제안해주신 견고한 수집 로직 실행
}

# 구글 시트에 업데이트 (경고 문구 없애는 방식 적용)
sheet_cache.update(range_name='A1', values=[[json.dumps(dashboard_cache, ensure_ascii=False)]])
print("🎉 대시보드 올인원 초고속 캐시(JSON_CACHE) 생성 완료!")