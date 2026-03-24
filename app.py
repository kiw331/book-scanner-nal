# 파일명: app.py
# 지시사항: 
# 1. 파일 저장 시간 형식을 "%m%d%H%M" (월일시분)으로 변경.
# 2. 개별 사진 삭제 버튼을 직관적인 ❌ 아이콘으로 변경하고 이미지 상단에 배치.
# 3. Streamlit 환경의 한계를 고려하여 이미지와 겹치지는 않되 최대한 간결한 UI로 구성.

import streamlit as st
import google.generativeai as genai
import pandas as pd
from PIL import Image
import io
import xml.dom.minidom
from datetime import datetime

# 커스텀 모듈 임포트
from modules.ocr_engine import extract_books_from_images
from modules.nal_search import fetch_nal_data, parse_and_sort_nal_response

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

# ==========================================
# 2. 세션 상태 관리 (초기화)
# ==========================================
if "image_data_store" not in st.session_state:
    st.session_state.image_data_store = {}
if "ocr_list" not in st.session_state:
    st.session_state.ocr_list = []
if "search_results" not in st.session_state:
    st.session_state.search_results = None
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# ==========================================
# 3. 탭 구성 및 각 탭별 메인 로직
# ==========================================
tab1, tab2 = st.tabs(["📸 사진 촬영 및 업로드", "🔍 국회도서관 API 테스트"])

with tab1:
    st.subheader("도서 사진 추가")
    st.info("💡 **모바일 팁**: 아래 버튼을 누르고 **[카메라]**를 선택해 고화질로 바로 촬영하거나, 갤러리에서 기존 사진을 고를 수 있습니다.")
    
    uploaded_files = st.file_uploader("사진을 선택하거나 촬영하세요 (여러 장 가능)", 
                                      type=['jpg', 'jpeg', 'png'], 
                                      accept_multiple_files=True,
                                      key=f"uploads_{st.session_state.uploader_key}")
    
    if uploaded_files:
        for f in uploaded_files:
            st.session_state.image_data_store[f.name] = f.getvalue()

    # ==========================================
    # 4. 이미지 미리보기 (Image Preview) 
    # ==========================================
    if st.session_state.image_data_store:
        st.divider()
        
        col_header1, col_header2 = st.columns([4, 1])
        with col_header1:
            st.subheader(f"🖼️ 분석 대기 중인 사진 ({len(st.session_state.image_data_store)}장)")
        with col_header2:
            if st.button("🗑️ 대기열 전체 삭제", type="secondary", use_container_width=True):
                st.session_state.image_data_store.clear()
                st.session_state.ocr_list = []
                st.session_state.search_results = None 
                st.session_state.pop("last_files_hash", None)
                st.session_state.uploader_key += 1 
                st.rerun()

        cols = st.columns(5)
        for i, (name, data) in enumerate(list(st.session_state.image_data_store.items())):
            with cols[i % 5]:
                # 💡 사진 상단 우측에 ❌ 버튼 배치
                btn_col1, btn_col2 = st.columns([3, 1])
                with btn_col2:
                    if st.button("❌", key=f"delete_{name}", help="이 사진 삭제"):
                        st.session_state.image_data_store.pop(name, None)
                        st.session_state.ocr_list = []
                        st.session_state.search_results = None 
                        st.session_state.pop("last_files_hash", None)
                        st.session_state.uploader_key += 1 
                        st.rerun()
                
                # 이미지 렌더링
                try:
                    img = Image.open(io.BytesIO(data))
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
            st.session_state.search_results = None 
            st.session_state.last_files_hash = current_files_hash

        if not st.session_state.ocr_list:
            if st.button("🔍 도서 제목 분석 시작 (OCR)", type="primary", use_container_width=True):
                progress_bar = st.progress(0)
                extracted_data = extract_books_from_images(model, st.session_state.image_data_store, progress_bar.progress)
                
                if extracted_data:
                    st.session_state.ocr_list = extracted_data
                    st.rerun()
                else:
                    st.warning("도서명을 추출하지 못했습니다. 화면에 표시된 에러 메시지를 확인해주세요.")

        if st.session_state.ocr_list:
            st.subheader("📝 추출된 도서 리스트 (편집 가능)")
            df = pd.DataFrame(st.session_state.ocr_list)
            
            edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, column_config={"source_image": None})

            if st.button("📚 국회도서관 소장 여부 확인 및 결과 생성", use_container_width=True):
                work_df = edited_df.reset_index(drop=True)
                work_df['행번호'] = work_df.index
                
                first_occurrences = work_df.drop_duplicates(subset=['original'], keep='first')
                first_idx_map = dict(zip(first_occurrences['original'], first_occurrences['행번호']))
                
                def get_duplicate_marker(row):
                    first_idx = first_idx_map.get(row['original'])
                    return "" if row['행번호'] == first_idx else first_idx
                
                work_df['중복 행번호'] = work_df.apply(get_duplicate_marker, axis=1)

                unique_queries = first_occurrences['original'].tolist()
                nal_results_map = {}
                
                progress_bar = st.progress(0)
                for i, query in enumerate(unique_queries):
                    try:
                        xml_content = fetch_nal_data(NAL_API_KEY, query, displaylines=100)
                        count, found_books = parse_and_sort_nal_response(xml_content, query)
                        
                        unique_books = []
                        seen_titles = set()
                        for b in found_books:
                            if b["title"] not in seen_titles:
                                unique_books.append(b)
                                seen_titles.add(b["title"])
                        unique_books = unique_books[:1]
                        
                        nal_results_map[query] = {
                            "소장수": count,
                            "국회도서관 확인명": "\n".join([b["title"] for b in unique_books]) if unique_books else "정보 없음",
                            "저자": "\n".join([b["author"] for b in unique_books]) if unique_books else "정보 없음",
                            "발행처": "\n".join([b["publisher"] for b in unique_books]) if unique_books else "정보 없음"
                        }
                    except Exception as e:
                        nal_results_map[query] = {"소장수": "에러", "국회도서관 확인명": "-", "저자": "-", "발행처": "-"}
                    
                    progress_bar.progress((i + 1) / len(unique_queries))

                final_results = []
                for idx, row in work_df.iterrows():
                    q = row['original']
                    nal_data = nal_results_map.get(q, {})
                    
                    final_results.append({
                        "원문": q,
                        "번역": row.get('display', ''),
                        "응답개수(소장수)": nal_data.get("소장수", "에러"),
                        "국회도서관 확인명": nal_data.get("국회도서관 확인명", "-"),
                        "저자": nal_data.get("저자", "-"),
                        "발행처": nal_data.get("발행처", "-"),
                        "중복 행번호": row['중복 행번호'],
                        "비고": ""
                    })

                st.session_state.search_results = final_results 
                st.session_state.final_work_df = work_df

            if st.session_state.search_results is not None:
                st.subheader("✅ 전체 분석 결과 (CSV 형식)")
                
                res_df = pd.DataFrame(st.session_state.search_results)
                work_df = st.session_state.final_work_df
                
                def highlight_found(row):
                    if str(row['응답개수(소장수)']) not in ['0', '에러']:
                        return ['background-color: #FFF9C4'] * len(row)
                    return [''] * len(row)
                
                styled_res_df = res_df.style.apply(highlight_found, axis=1)
                st.dataframe(styled_res_df, use_container_width=True)
                
                # ==========================================
                # 6. 다운로드 버튼 섹션
                # ==========================================
                st.divider()
                st.subheader("📥 다운로드")
                
                # 💡 시간 형식 변경 적용 (마지막 % 제거)
                current_time = datetime.now().strftime("%m%d%H%M")
                
                csv_bytes = res_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="결과 저장하기", 
                    data=csv_bytes, 
                    file_name=f"nal{current_time}_results.csv", 
                    mime="text/csv",
                    type="primary"
                )
                
                st.markdown("#### 🖼️ 분석 원본 사진 다운로드")
                st.write("각 사진이 담당한 CSV 행(Row) 번호가 파일명에 표기됩니다.")
                
                img_cols = st.columns(4)
                col_idx = 0
                
                for img_name, img_bytes in st.session_state.image_data_store.items():
                    img_rows = work_df[work_df['source_image'] == img_name]
                    
                    if not img_rows.empty:
                        start_idx = img_rows.index.min()
                        end_idx = img_rows.index.max()
                        new_img_name = f"nal{current_time}_{start_idx}_{end_idx}.jpg"
                    else:
                        new_img_name = f"nal{current_time}_none_{img_name.split('.')[0]}.jpg"
                    
                    with img_cols[col_idx % 4]:
                        st.download_button(
                            label=f"⬇️ {new_img_name}",
                            data=img_bytes,
                            file_name=new_img_name,
                            mime="image/jpeg"
                        )
                    col_idx += 1

with tab2:
    st.subheader("🔍 국회도서관 API 검색 테스트")
    st.write("유사도 정렬이 적용된 API 원본 응답을 확인합니다.")
    test_search_term = st.text_input("검색할 도서명/논문명을 입력하세요", placeholder="예: the R book")
    
    if st.button("API 검색 테스트", type="primary"):
        if test_search_term:
            with st.spinner("국회도서관 데이터를 불러오는 중..."):
                try:
                    xml_content = fetch_nal_data(NAL_API_KEY, test_search_term, displaylines=100)
                    total_count, found_books = parse_and_sort_nal_response(xml_content, test_search_term)
                    
                    st.write(f"**검색 결과 총 건수 (total):** {total_count}건")
                    
                    if found_books:
                        st.dataframe(pd.DataFrame(found_books), use_container_width=True)
                    else:
                        st.warning("상세 정보(record/recode)가 없습니다.")
                    
                    with st.expander("원본 XML 응답 보기"):
                        dom = xml.dom.minidom.parseString(xml_content)
                        st.code(dom.toprettyxml(), language="xml")
                except Exception as e:
                    st.error(f"API 호출 중 오류가 발생했습니다: {e}")
        else:
            st.warning("검색어를 입력해 주세요.")