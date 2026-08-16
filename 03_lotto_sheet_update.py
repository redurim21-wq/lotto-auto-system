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
        sheet_cache = doc.add_worksheet(title="JSON_CACHE", rows="20", cols="5")
        
except Exception as e:
    print(f"❌ 구글 시트 연결 실패: {e}")
    exit()

# ==========================================
# 1. 최신 뉴스 수집
# ==========================================
def fetch_lotto_news():
    print("📡 뉴스 수집 시도 중...")
    news_items = []
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        url_google = f"https://news.google.com/rss/search?q={quote('로또 당첨번호 1등')}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url_google, headers=headers, timeout=5)
        root = ET.fromstring(res.content)
        
        for item in root.findall('.//item')[:8]:
            title = item.find('title').text if item.find('title') is not None else ''
            link = item.find('link').text if item.find('link') is not None else ''
            pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ''
            if " - " in title: title = title.rsplit(" - ", 1)[0]
            if title and link:
                news_items.append({"title": title.strip(), "link": link.strip(), "date": pubDate[:16], "source": "google"})
        if news_items:
            print(f"✅ 뉴스 {len(news_items)}건 수집 성공")
            return news_items
    except: pass
    return []

# ==========================================
# 2. 당첨번호 및 당첨점(명당) 최신회차 업데이트
# ==========================================
lotto_rows = sheet_lotto.get_all_values()
lotto_data = lotto_rows[1:]
last_epsd = int(lotto_data[-1][0])
target_epsd = last_epsd + 1

print(f"🔄 현재 시트 마지막 회차: {last_epsd}회")
print(f"📡 {target_epsd}회차 데이터 수집 시도 중...")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

# ----------------------------------------------------
# [STEP 2-1] 당첨번호 상세 수집 (기존과 동일)
# ----------------------------------------------------
url_lotto = "https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do"
params_lotto = {"srchDir": "center", "srchLtEpsd": str(target_epsd), "_": str(int(time.time() * 1000))}

target_lotto_data = None
try:
    res_lotto = requests.get(url_lotto, headers=headers, params=params_lotto, timeout=10)
    lotto_json = res_lotto.json()
    lotto_list = lotto_json.get('data', {}).get('list', [])
    target_lotto_data = next((item for item in lotto_list if item.get("ltEpsd") == target_epsd), None)
except Exception as e:
    print(f"⚠️ 당첨번호 수집 중 오류: {e}")

if target_lotto_data:
    new_lotto_row = [
        target_lotto_data.get("ltEpsd"), target_lotto_data.get("ltRflYmd"),
        target_lotto_data.get("tm1WnNo"), target_lotto_data.get("tm2WnNo"), target_lotto_data.get("tm3WnNo"),
        target_lotto_data.get("tm4WnNo"), target_lotto_data.get("tm5WnNo"), target_lotto_data.get("tm6WnNo"), target_lotto_data.get("bnsWnNo"),
        target_lotto_data.get("wholEpsdSumNtslAmt"),
        target_lotto_data.get("rnk1WnNope"), target_lotto_data.get("rnk1WnAmt"),
        target_lotto_data.get("rnk2WnNope"), target_lotto_data.get("rnk2WnAmt"),
        target_lotto_data.get("rnk3WnNope"), target_lotto_data.get("rnk3WnAmt"),
        target_lotto_data.get("rnk4WnNope"), target_lotto_data.get("rnk4WnAmt"),
        target_lotto_data.get("rnk5WnNope"), target_lotto_data.get("rnk5WnAmt"),
        target_lotto_data.get("winType1"), target_lotto_data.get("winType2"), target_lotto_data.get("winType3"),
        target_lotto_data.get("rnk1SumWnAmt"), target_lotto_data.get("rlvtEpsdSumNtslAmt"), target_lotto_data.get("sumWnNope")
    ]
    sheet_lotto.append_row(new_lotto_row)
    print(f"✅ {target_epsd}회차 당첨번호 시트 업데이트 완료")

    # ----------------------------------------------------
    # [STEP 2-2] 당첨점 수집 (🚨 대표님의 완벽한 20열 원본 구조로 복구!)
    # ----------------------------------------------------
    print(f"📡 {target_epsd}회차 당첨점 기존 20개 컬럼 형식에 맞춰 수집 중...")
    url_shop_api = "https://www.dhlottery.co.kr/wnprchsplcsrch/selectLtWnShp.do"
    params_shop_api = {"srchWnShpRnk": "all", "srchLtEpsd": str(target_epsd)}
    
    try:
        res_shop = requests.get(url_shop_api, headers=headers, params=params_shop_api, timeout=10)
        api_json = res_shop.json()
        shop_list = api_json.get("data", {}).get("list", [])
        
        new_shop_rows = []
        for shop in shop_list:
            if shop.get("wnShpRnk") == 1 or shop.get("excelRnk") == "1등":
                # 대표님이 말씀하신 20열 순서에 완벽히 매핑
                new_shop_rows.append([
                    target_epsd,                                    # [0] 회차
                    shop.get("rnum", ""),                           # [1] 순번
                    shop.get("wnShpRnk", ""),                       # [2] 당첨등수
                    (shop.get("atmtPsvYnTxt") or "").strip(),       # [3] 당첨유형 (자동/수동)
                    (shop.get("atmtPsvYn") or "").strip(),          # [4] 당첨유형_코드
                    (shop.get("shpNm") or "").strip(),              # [5] 판매점명
                    (shop.get("ltShpId") or "").strip(),            # [6] 판매점ID
                    (shop.get("shpTelno") or "").strip(),           # [7] 전화번호
                    (shop.get("slrOperSttsCd") or "").strip(),      # [8] 운영코드
                    (shop.get("tm1ShpLctnAddr") or "").strip(),     # [9] 시도
                    (shop.get("tm2ShpLctnAddr") or "").strip(),     # [10] 시군구
                    (shop.get("tm3ShpLctnAddr") or "").strip(),     # [11] 상세주소
                    (shop.get("shpAddr") or "").strip(),            # [12] 전체주소
                    shop.get("shpLat", ""),                         # [13] 위도
                    shop.get("shpLot", ""),                         # [14] 경도
                    (shop.get("l645LtNtslYn") or "").strip(),       # [15] 로또645판매
                    (shop.get("st5LtNtslYn") or "").strip(),        # [16] 연금복권판매
                    (shop.get("st10LtNtslYn") or "").strip(),       # [17] 스피또1000판매
                    (shop.get("st20LtNtslYn") or "").strip(),       # [18] 스피또2000판매
                    (shop.get("pt720NtslYn") or "").strip()         # [19] 신규연금복권판매
                ])
                    
        if new_shop_rows:
            sheet_shop.append_rows(new_shop_rows)
            print(f"✅ {target_epsd}회차 당첨점 {len(new_shop_rows)}곳 구글 시트(20열) 저장 완벽 복구 완료!")
        else:
            print(f"⚠️ {target_epsd}회차 당첨점 데이터가 서버에 없습니다.")
            
    except Exception as e:
        print(f"❌ 당첨점 JSON 수집 오류: {e}")

    # 새 데이터 리로드
    lotto_rows = sheet_lotto.get_all_values()
    lotto_data = lotto_rows[1:]
else:
    print(f"✅ {target_epsd}회차는 아직 추첨 전이거나 데이터가 없습니다.")


# ==========================================
# 3. 대시보드 초고속 캐시(JSON_CACHE) 생성
# ==========================================
print("⚡ 대시보드 초고속 캐시(JSON) 생성 시작...")

def safe_float(val):
    try: return float(val)
    except: return None

latest_lotto = lotto_data[-1]
latest_epsd_str = str(latest_lotto[0])

# 최근 5회차 데이터
processed_recent5 = []
for r in lotto_data[-5:]:
    processed_recent5.append({
        "drawNo": r[0], "drawDate": r[1],
        "numbers": [r[2], r[3], r[4], r[5], r[6], r[7]],
        "bonusNo": r[8],
        "winCount": r[10] if len(r) > 10 else '',
        "winAmt": r[11] if len(r) > 11 else ''
    })

# 번호 빈도수 통계
freq_map = {str(i): 0 for i in range(1, 46)}
for r in lotto_data[-50:]:
    for num_idx in range(2, 8):
        if num_idx < len(r):
            num = str(r[num_idx]).strip()
            if num in freq_map: freq_map[num] += 1

# 명당 지도용 데이터 (🚨 20열 구조에 맞춘 인덱스 완벽 수정)
all_shops = sheet_shop.get_all_values()[1:]
recent_shops = []
store_win_counts = {}
target_min_epsd = int(latest_lotto[0]) - 50

# 자동/수동/반자동 카운트
auto_cnt = int(latest_lotto[20]) if len(latest_lotto) > 20 and str(latest_lotto[20]).isdigit() else 0
manual_cnt = int(latest_lotto[21]) if len(latest_lotto) > 21 and str(latest_lotto[21]).isdigit() else 0
semi_cnt = int(latest_lotto[22]) if len(latest_lotto) > 22 and str(latest_lotto[22]).isdigit() else 0

for s in all_shops:
    if not s or not s[0].isdigit(): continue
    shop_epsd = int(s[0])
    store_name = s[5] if len(s) > 5 else ''    # [5] 판매점명
    type_name = s[3] if len(s) > 3 else ''     # [3] 당첨유형
    
    if store_name:
        store_win_counts[store_name] = store_win_counts.get(store_name, 0) + 1
        
    if auto_cnt == 0 and manual_cnt == 0 and str(shop_epsd) == latest_epsd_str:
        if type_name == "자동": auto_cnt += 1
        elif type_name == "수동": manual_cnt += 1
        elif type_name == "반자동": semi_cnt += 1

    if shop_epsd >= target_min_epsd:
        recent_shops.append(s)

processed_shops = []
for s in recent_shops:
    processed_shops.append({
        "epsd": int(s[0]),
        "name": s[5] if len(s) > 5 else '',                           # [5] 판매점명
        "type": s[3] if len(s) > 3 else '자동',                       # [3] 당첨유형
        "address": s[12] if len(s) > 12 else '',                      # [12] 전체주소
        "tel": s[7] if len(s) > 7 else '',                            # [7] 전화번호
        "region": s[9] if len(s) > 9 else '',                         # [9] 시도
        "sido": s[9] if len(s) > 9 else '',
        "sigungu": s[10] if len(s) > 10 else '',                      # [10] 시군구
        "detailAddr": s[11] if len(s) > 11 else '',                   # [11] 상세주소
        "lat": safe_float(s[13]) if len(s) > 13 else None,            # 🚨 [13] 위도 (정확한 매핑!)
        "lng": safe_float(s[14]) if len(s) > 14 else None,            # 🚨 [14] 경도 (정확한 매핑!)
        "shopId": s[6] if len(s) > 6 else '',                         # [6] 판매점ID
        "count": store_win_counts.get(s[5] if len(s)>5 else '', 1)
    })

def clean_str(val): return str(val).replace(',', '').strip()

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
        "secondWinCount": clean_str(latest_lotto[12]) if len(latest_lotto) > 12 else '',
        "secondWinAmt": clean_str(latest_lotto[13]) if len(latest_lotto) > 13 else '',
        "thirdWinCount": clean_str(latest_lotto[14]) if len(latest_lotto) > 14 else '',
        "thirdWinAmt": clean_str(latest_lotto[15]) if len(latest_lotto) > 15 else '',
        "fourthWinCount": clean_str(latest_lotto[16]) if len(latest_lotto) > 16 else '',
        "fourthWinAmt": clean_str(latest_lotto[17]) if len(latest_lotto) > 17 else '',
        "fifthWinCount": clean_str(latest_lotto[18]) if len(latest_lotto) > 18 else '',
        "fifthWinAmt": clean_str(latest_lotto[19]) if len(latest_lotto) > 19 else '',
        "autoCount": auto_cnt,
        "manualCount": manual_cnt,
        "semiCount": semi_cnt,
        "firstSumWinAmt": clean_str(latest_lotto[23]) if len(latest_lotto) > 23 else '',
        "epsdSellAmt": clean_str(latest_lotto[24]) if len(latest_lotto) > 24 else '',
        "totalWinCount": clean_str(latest_lotto[25]) if len(latest_lotto) > 25 else ''
    },
    "recent5": processed_recent5,
    "freq50": freq_map,
    "shops": processed_shops,
    "news": fetch_lotto_news(),
    "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S")
}

# 5만자 분할 저장
cache_json_str = json.dumps(dashboard_cache, ensure_ascii=False)
chunk_size = 40000 
chunks = [cache_json_str[i:i+chunk_size] for i in range(0, len(cache_json_str), chunk_size)]

sheet_cache.clear()
values = [[chunk] for chunk in chunks]
sheet_cache.update(range_name=f"A1:A{len(values)}", values=values)

print(f"🎉 5만자 분할 저장 완료! (총 {len(cache_json_str)}자 / {len(chunks)}개 셀 사용)")
print("🎉 대시보드 올인원 초고속 캐시(JSON_CACHE) 생성 완료!")