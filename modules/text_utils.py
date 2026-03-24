"""
파일명: modules/text_utils.py
지시사항: HTML 태그 제거 및 두 문자열 간의 유사도를 계산하는 텍스트 처리 헬퍼 함수들을 포함합니다. (특수문자 정규화 제거됨)
"""
import re

def clean_html_tags(text):
    if not text:
        return ""
    clean_text = re.sub(r'<[^>]+>', '', text)
    clean_text = clean_text.replace('<![CDATA[', '').replace(']]>', '')
    return clean_text.strip()

def calculate_similarity(query, title):
    if not query or not title:
        return 0
    
    # 이전 로직으로 롤백 (단순 소문자 변환 및 양끝 기호만 제거)
    norm_query = query.lower().strip()
    norm_title = title.lower().strip(' /.-')
    
    score = 0
    if norm_query == norm_title:
        score += 1000
    elif norm_query in norm_title:
        score += 500
    elif norm_title in norm_query:
        score += 400
    
    q_words = set(norm_query.split())
    t_words = set(norm_title.split())
    overlap = len(q_words.intersection(t_words))
    score += overlap * 10
    
    return score