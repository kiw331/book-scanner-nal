"""
파일명: app.py
지시사항: 서적 OCR 및 국회도서관 API 연동 웹 애플리케이션입니다.
- API 검색 건수를 100건으로 확대하여 검색 사각지대를 없앴습니다.
- 유사도 점수 기반 정렬 후, 요약표가 너무 길어지는 것을 방지하기 위해 가장 정확도가 높은 상위 3개의 도서 정보만 화면에 출력하도록 필터링 로직(unique_books[:3])을 추가했습니다.
"""

import streamlit as st
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
import xml.dom.minidom
import pandas as pd
import json
from PIL import Image
import io
import re

# ==========================================
# 0. 헬퍼 함수 (텍스트 정제 및 유사도 계산)
# ==========================================
def clean_html_tags(text):
    if not text:
        return ""
    clean_text = re.sub(r'<[^>]+>', '', text)
    clean_text = clean_text.replace('<![CDATA[', '').replace(']]>', '')
    return clean_text.strip()

def calculate_similarity(query, title):
    if not query or not title:
        return 0
    
    score = 0
    if query == title:
        score += 1000
    elif query in title:
        score += 500
    elif title in query:
        score += 400
    
    q_words = set(query.split())
    t_words = set(title.split())
    overlap = len(q_words.intersection(t_words))
    score += overlap * 10
    
    return score

# ==========================================
# 1. 초기 설정 및 보안 (Secrets)
# ==========================================
try:
    GEMINI_API_KEY = st.secrets["GEMINI_KEY"]
    NAL_API_KEY = st.secrets["NAL_KEY"]
except Exception:
    st.error("API 키 설정이 필요합니다. Streamlit Cloud의 Secrets 설정을 확인하세요.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-3-flash-preview')

st.set_page_config(page_title="서적 OCR 정리", layout="wide", page_icon="📚")
st.title("📚 서적 OCR 및 국회도서관 검색")

st.markdown("""
    <style>
    [data-testid="stCameraInput"] { width: 100% !important; max-width: 100% !important; }
    [data-testid="stCameraInput"] video { width: 100% !important; height: auto !important; border-radius: 10px; }
    .thumb-container { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
    .thumb-item { border: 2px solid #ddd; border-radius: 5px; overflow: hidden; position: relative; }
    .thumb-item img { display: block; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 세션 상태 관리 (초기화)
# ==========================================
if "image_data_store" not in st.session_state:
    st.session_state.image_data_store = {}

if "camera_enabled" not in st.session_state:
    st.session_state.camera_enabled = False

if "ocr_list" not in st.session_state:
    st.session_state.ocr_list = []

# ==========================================
# 3. 입력 섹션 및 API 테스트 (탭 구성)
# ==========================================
tab1, tab2, tab3 = st.tabs(["📁 사진 다중 업로드", "📸 카메라 촬영", "🔍 국회도서관 API 테스트"])

with tab1:
    st.subheader("갤러리 업로드 (고화질 권장)")
    st.info("휴대폰의 기본 카메라로 선명하게 촬영한 뒤 업로드하시면 인식률이 가장 좋습니다.")
    uploaded_files = st.file_uploader("사진들을 선택하세요 (여러 장 가능)", 
                                      type=['jpg', 'jpeg', 'png'], 
                                      accept_multiple_files=True)
    if uploaded_files:
        for f in uploaded_files:
            st.session_state.image_data_store[f.name] = f.getvalue()
        st.success(f"{len(uploaded_files)}장의 사진이 대기열에 추가되었습니다.")

with tab2:
    st.subheader("실시간 촬영")
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if not st.session_state.camera_enabled:
            if st.button("📷 카메라 시작", use_container_width=True):
                st.session_state.camera_enabled = True
                st.rerun()
    
    with col_btn2:
        if st.session_state.camera_enabled:
            if st.button("❌ 카메라 종료", use_container_width=True, type="primary"):
                st.session_state.camera_enabled = False
                st.rerun()
                
    if st.session_state.camera_enabled:
        cam_file = st.camera_input("책장을 정면에서 촬영해주세요")
        if cam_file:
            st.session_state.image_data_store["camera_shot.jpg"] = cam_file.getvalue()
            st.success("사진이 촬영되어 분석 대기열에 추가되었습니다.")

with tab3:
    st.subheader("🔍 국회도서관 API 검색 테스트")
    st.write("유사도 정렬이 적용된 API 원본 응답을 확인합니다.")
    
    test_search_term = st.text_input("검색할 도서명/논문명을 입력하세요", placeholder="예: the R book")
    
    if st.button("API 검색 테스트", type="primary"):
        if test_search_term:
            with st.spinner("국회도서관 데이터를 불러오는 중..."):
                params = {
                    'ServiceKey': NAL_API_KEY,
                    'search': f"자료명,{test_search_term}",
                    'displaylines': 100 # 100건으로 증가
                }
                try:
                    res = requests.get("http://apis.data.go.kr/9720000/searchservice/basic", params=params)
                    root = ET.fromstring(res.content)
                    total_count = root.findtext('total') or "0"
                    
                    st.write(f"**검색 결과 총 건수 (total):** {total_count}건")
                    
                    test_results = []
                    records = root.findall('.//recode') + root.findall('.//record')
                    
                    for record in records:
                        item_dict = {}
                        title_for_scoring = ""
                        for item in record.findall('item'):
                            name = item.findtext('name')
                            value = item.findtext('value')
                            if name:
                                clean_val = clean_html_tags(value) if value else ""
                                item_dict[name] = clean_val
                                if name in ["자료명", "논문명", "서명", "Main Title"]:
                                    title_for_scoring = clean_val
                        
                        if item_dict:
                            item_dict["_score"] = calculate_similarity(test_search_term, title_for_scoring)
                            test_results.append(item_dict)
                            
                    if test_results:
                        test_results.sort(key=lambda x: x["_score"], reverse=True)
                        
                        for item in test_results:
                            item.pop("_score", None)
                            
                        st.dataframe(pd.DataFrame(test_results), use_container_width=True)
                    else:
                        st.warning("상세 정보(record/recode)가 없습니다.")
                    
                    with st.expander("원본 XML 응답 보기"):
                        dom = xml.dom.minidom.parseString(res.content)
                        pretty_xml = dom.toprettyxml()
                        st.code(pretty_xml, language="xml")
                        
                except Exception as e:
                    st.error(f"API 호출 중 오류가 발생했습니다: {e}")
        else:
            st.warning("검색어를 입력해 주세요.")

# ==========================================
# 4. 이미지 미리보기 (Image Preview) 섹션
# ==========================================
if st.session_state.image_data_store:
    st.divider()
    st.subheader(f"🖼️ 분석 대기 중인 사진 ({len(st.session_state.image_data_store)}장)")
    
    if st.button("🗑️ 대기열 전체 삭제", type="secondary"):
        st.session_state.image_data_store = {}
        st.session_state.ocr_list = []
        st.rerun()

    cols = st.columns(5)
    for i, (name, data) in enumerate(st.session_state.image_data_store.items()):
        with cols[i % 5]:
            try:
                img = Image.open(io.BytesIO(data))
                img.thumbnail((200, 200))
                st.image(img, caption=name, use_container_width=True)
            except Exception as e:
                st.error(f"{name} 로드 실패: {e}")

# ==========================================
# 5. 분석 및 결과 확인
# ==========================================
if st.session_state.image_data_store:
    st.divider()
    current_files_hash = str(list(st.session_state.image_data_store.keys()))
    if "last_files_hash" not in st.session_state or st.session_state.last_files_hash != current_files_hash:
        st.session_state.ocr_list = []
        st.session_state.last_files_hash = current_files_hash

    if not st.session_state.ocr_list:
        if st.button("🔍 도서 제목 분석 시작 (OCR)", type="primary", use_container_width=True):
            all_books = []
            progress_bar = st.progress(0)
            file_names = list(st.session_state.image_data_store.keys())
            
            for i, name in enumerate(file_names):
                data = st.session_state.image_data_store[name]
                prompt = "이 사진 속 책 제목들을 추출해줘. 세로쓰기를 고려해줘. 결과는 반드시 {'books': [{'original': '원문한자', 'display': '한글독음'}]} 형식의 JSON으로만 답해줘."
                try:
                    response = model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': data}])
                    raw_text = response.text.replace('```json', '').replace('```', '').strip()
                    ocr_data = json.loads(raw_text)
                    all_books.extend(ocr_data.get('books', []))
                except Exception:
                    continue
                progress_bar.progress((i + 1) / len(file_names))
            
            df_tmp = pd.DataFrame(all_books)
            if not df_tmp.empty:
                df_tmp['상태'] = df_tmp.duplicated(subset=['original'], keep='first').map({True: '⚠️ 중복', False: '정상'})
                st.session_state.ocr_list = df_tmp.to_dict('records')
            st.rerun()

    if st.session_state.ocr_list:
        st.subheader("📝 추출된 도서 리스트 (편집 가능)")
        df = pd.DataFrame(st.session_state.ocr_list)
        
        def highlight_dup(row):
            return ['background-color: #FFCDD2' if row['상태'] == '⚠️ 중복' else '' for _ in row]

        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

        if st.button("📚 국회도서관 소장 여부 확인 (중복 제외 검색)", use_container_width=True):
            final_results = []
            unique_targets = edited_df.drop_duplicates(subset=['original'])
            
            progress_bar = st.progress(0)
            for i, (idx, row) in enumerate(unique_targets.iterrows()):
                search_query = row['original']
                params = {
                    'ServiceKey': NAL_API_KEY,
                    'search': f"자료명, {search_query}",
                    'displaylines': 100 # 100건 검색으로 풀 확대
                }
                
                try:
                    res = requests.get("http://apis.data.go.kr/9720000/searchservice/basic", params=params)
                    root = ET.fromstring(res.content)
                    count = root.findtext('total') or "0"
                    
                    found_books = []
                    records = root.findall('.//recode') + root.findall('.//record')
                    
                    for record in records:
                        title, author, publisher = "", "", ""
                        for item in record.findall('item'):
                            tag_name = item.findtext('name')
                            tag_value = clean_html_tags(item.findtext('value'))
                            
                            if tag_name in ["자료명", "논문명", "서명", "Main Title"]:
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
                    
                    unique_books = []
                    seen_titles = set()
                    for b in found_books:
                        if b["title"] not in seen_titles:
                            unique_books.append(b)
                            seen_titles.add(b["title"])
                    
                    # 🔥 여기서 가장 유사도가 높은 상위 3개만 자름
                    unique_books = unique_books[:3]
                    
                    display_titles = "\n".join([b["title"] for b in unique_books]) if unique_books else "정보 없음"
                    display_authors = "\n".join([b["author"] for b in unique_books]) if unique_books else "정보 없음"
                    display_publishers = "\n".join([b["publisher"] for b in unique_books]) if unique_books else "정보 없음"
                    
                    final_results.append({
                        "원문(한자)": search_query,
                        "소장수": count,
                        "국회도서관 확인명": display_titles,
                        "저자": display_authors,
                        "발행처": display_publishers
                    })
                except Exception:
                    final_results.append({
                        "원문(한자)": search_query, 
                        "소장수": "에러", 
                        "국회도서관 확인명": "-",
                        "저자": "-",
                        "발행처": "-"
                    })
                
                progress_bar.progress((i + 1) / len(unique_targets))

            st.subheader("✅ 검색 결과 요약")
            
            res_df = pd.DataFrame(final_results)
            
            def highlight_found(row):
                if str(row['소장수']) not in ['0', '에러']:
                    return ['background-color: #FFF9C4'] * len(row)
                return [''] * len(row)
            
            styled_res_df = res_df.style.apply(highlight_found, axis=1)
            st.dataframe(styled_res_df, use_container_width=True)
            
            csv = res_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 결과를 CSV로 저장", data=csv, file_name="nal_search_result.csv", mime="text/csv")