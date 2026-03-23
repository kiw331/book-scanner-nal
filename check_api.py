import requests
import toml
import os
import xml.etree.ElementTree as ET
import xml.dom.minidom 

# config/secrets.toml 파일 경로 지정
CONFIG_PATH = os.path.join("config", "secrets.toml")

try:
    secrets = toml.load(CONFIG_PATH)
    NAL_API_KEY = secrets["NAL_KEY"]
except Exception as e:
    print(f"❌ 설정 파일을 읽을 수 없습니다: {e}")
    exit()

SEARCH_TERM = "THE R BOOK" # 확인하고 싶은 검색어 (한자 또는 한글)

# 2. API 호출
url = "http://apis.data.go.kr/9720000/searchservice/basic"
params = {
    'ServiceKey': NAL_API_KEY,
    'search': f"자료명,{SEARCH_TERM}",
    'displaylines': 3
}

print(f"🔍 검색어 '{SEARCH_TERM}'으로 API 호출 중...\n")

try:
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    # 3. 전체 XML 구조 예쁘게 출력
    dom = xml.dom.minidom.parseString(response.content)
    pretty_xml = dom.toprettyxml()
    print("=== [원본 XML 응답 구조] ===")
    print(pretty_xml)
    print("===========================\n")

    # 4. 상세 분석
    root = ET.fromstring(response.content)
    total_count = root.findtext('total') or "0"
    print(f"📊 검색 결과 총 건수 (total): {total_count}")

    # recode 또는 record 태그 모두 확인
    items = root.findall('.//recode') or root.findall('.//record')
    
    if not items:
        print("❌ 상세 기록(recode/record)이 검색 결과에 포함되어 있지 않습니다.")
    else:
        for i, record in enumerate(items):
            print(f"\n--- [기록 {i+1} 상세 항목 리스트] ---")
            for item in record.findall('item'):
                name = item.findtext('name')
                value = item.findtext('value')
                print(f"태그명: {name:15} | 값: {value}")

except Exception as e:
    print(f"❗ 오류 발생: {e}")