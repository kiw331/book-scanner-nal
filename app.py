import streamlit as st
import google.generativeai as genai
import pandas as pd
from PIL import Image
import io
import xml.dom.minidom

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

st.markdown("""
    <style>
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

if "ocr_list" not in st.session_state:
    st.session_state.ocr_list = []

# 💡 [추가] 검색 결과를 저장할 세션 추가
if "search_results" not in st.session_state:
    st.session_state.search_results = None

# ==========================================
# 3. 탭 구성 및 각 탭별 메인 로직
# ==========================================
tab1, tab2 = st.tabs(["📸 사진 촬영 및 업로드", "🔍 국회도서관 API 테스트"])

with tab1:
    st.subheader("도서 사진 추가")
    st.info("💡 **모바일 팁**: 아래 버튼을 누르고 **[카메라]**를 선택해 고화질로 바로 촬영하거나, 갤러리에서 기존 사진을 고를 수 있습니다.")
    uploaded_files = st.file_uploader("사진을 선택하거나 촬영하세요 (여러 장 가능)", 
                                      type=['jpg', 'jpeg', 'png'], 
                                      accept_multiple_files=True)
    if uploaded_files:
        for f in uploaded_files:
            st.session_state.image_data_store[f.name] = f.getvalue()
        st.success(f"{len(uploaded_files)}장의 사진이 대기열에 추가되었습니다.")

    # ==========================================
    # 4. 이미지 미리보기 (Image Preview) 섹션 (tab1 내부)
    # ==========================================
    if st.session_state.image_data_store:
        st.divider()
        st.subheader(f"🖼️ 분석 대기 중인 사진 ({len(st.session_state.image_data_store)}장)")
        
        if st.button("🗑️ 대기열 전체 삭제", type="secondary"):
            st.session_state.image_data_store = {}
            st.session_state.ocr_list = []
            st.session_state.search_results = None # 💡 대기열 지울 때 검색 결과도 초기화
            st.rerun()

        cols = st.columns(5)
        for i, (name, data) in enumerate(st.session_state.image_data_store.items()):
            with cols[i % 5]:
                try:
                    img = Image.open(io.BytesIO(data))
                    # img.thumbnail((200, 200))
                    st.image(img, caption=name, use_container_width=True)
                except Exception as e:
                    st.error(f"{name} 로드 실패: {e}")

    # ==========================================
    # 5. 분석 및 결과 확인 (tab1 내부)
    # ==========================================
    if st.session_state.image_data_store:
        st.divider()
        current_files_hash = str(list(st.session_state.image_data_store.keys()))
        if "last_files_hash" not in st.session_state or st.session_state.last_files_hash != current_files_hash:
            st.session_state.ocr_list = []
            st.session_state.search_results = None # 💡 사진 목록이 바뀌면 검색 결과도 초기화
            st.session_state.last_files_hash = current_files_hash

        if not st.session_state.ocr_list:
            if st.button("🔍 도서 제목 분석 시작 (OCR)", type="primary", use_container_width=True):
                progress_bar = st.progress(0)
                st.session_state.ocr_list = extract_books_from_images(model, st.session_state.image_data_store, progress_bar.progress)
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
                    
                    try:
                        xml_content = fetch_nal_data(NAL_API_KEY, search_query, displaylines=100)
                        count, found_books = parse_and_sort_nal_response(xml_content, search_query)
                        
                        unique_books = []
                        seen_titles = set()
                        for b in found_books:
                            if b["title"] not in seen_titles:
                                unique_books.append(b)
                                seen_titles.add(b["title"])
                        
                        # 모바일 가독성을 위해 상위 1개만 자름
                        unique_books = unique_books[:1]
                        
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
                    except Exception as e: 
                        print(f"[{search_query}] 검색 중 에러 발생: {e}") 
                        final_results.append({
                            "원문(한자)": search_query, 
                            "소장수": "에러", 
                            "국회도서관 확인명": "-",
                            "저자": "-",
                            "발행처": "-"
                        })
                    
                    progress_bar.progress((i + 1) / len(unique_targets))

                # 💡 검색 완료 후 결과를 세션에 저장
                st.session_state.search_results = final_results 

            # 💡 버튼 클릭 블록 바깥으로 빼서 탭 이동 시에도 항상 그려주기
            if st.session_state.search_results is not None:
                st.subheader("✅ 검색 결과 요약")
                
                res_df = pd.DataFrame(st.session_state.search_results)
                
                def highlight_found(row):
                    if str(row['소장수']) not in ['0', '에러']:
                        return ['background-color: #FFF9C4'] * len(row)
                    return [''] * len(row)
                
                styled_res_df = res_df.style.apply(highlight_found, axis=1)
                st.dataframe(styled_res_df, use_container_width=True)
                
                csv = res_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 결과를 CSV로 저장", data=csv, file_name="nal_search_result.csv", mime="text/csv")


with tab2:
    st.subheader("🔍 국회도서관 API 검색 테스트")
    st.write("유사도 정렬이 적용된 API 원본 응답을 확인합니다. (전처리 롤백 적용됨)")
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