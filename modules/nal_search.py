"""
파일명: modules/nal_search.py
지시사항: 국회도서관 API를 호출하고 XML 응답을 파싱하여, 검색어와 가장 유사도가 높은 상위 도서 정보를 반환합니다.
"""
import requests
import xml.etree.ElementTree as ET
from modules.text_utils import clean_html_tags, calculate_similarity
import re

def fetch_nal_data(api_key, search_term, displaylines=100):
    # 💡 [수정] API 전송 전 특수문자 제거 (영문, 숫자, 한글, 공백만 남김)
    safe_search_term = re.sub(r'[^\w\s가-힣]', '', search_term)
    
    params = {
        'ServiceKey': api_key,
        'search': f"자료명,{safe_search_term}",  # 정제된 검색어로 전송
        'displaylines': displaylines 
    }
    response = requests.get("http://apis.data.go.kr/9720000/searchservice/basic", params=params)
    response.raise_for_status()
    return response.content

def parse_and_sort_nal_response(xml_content, search_query):
    root = ET.fromstring(xml_content)
    count = root.findtext('total') or "0"
    
    found_books = []
    records = root.findall('.//recode') + root.findall('.//record')
    
    for record in records:
        title, author, publisher = "", "", ""
        for item in record.findall('item'):
            tag_name = item.findtext('name')
            tag_value = clean_html_tags(item.findtext('value'))
            
            if tag_name in ["자료명", "논문명", "서명", "Main Title", "기사명"]: # '기사명' 추가
                title = tag_value
            elif tag_name in ["저자명", "저자", "Author"]:
                author = tag_value
            elif tag_name in ["발행자", "발행처", "Publisher"]:
                publisher = tag_value
                
        if title:
            score = calculate_similarity(search_query, title)
            found_books.append({
                "title": title, 
                "author": author, 
                "publisher": publisher, 
                "score": score
            })
            
    found_books.sort(key=lambda x: x["score"], reverse=True)
    return count, found_books