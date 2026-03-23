import streamlit as st
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import json
from PIL import Image
import io

# ==========================================
# 1. 초기 설정 및 보안 (Secrets)
# ==========================================
# Secrets에서 키 불러오기
try:
    GEMINI_API_KEY = st.secrets["GEMINI_KEY"]
    NAL_API_KEY = st.secrets["NAL_KEY"]
except Exception:
    st.error("API 키 설정이 필요합니다. Streamlit Cloud의 Secrets 설정을 확인하세요.")
    st.stop()

# Gemini 설정 및 최신 모델 로드
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-3-flash-preview')

# 레이아웃 설정
st.set_page_config(page_title="서적 OCR 정리", layout="wide", page_icon="📚")
st.title("📚 서적 OCR 및 국회도서관 검색")

# 카메라 UI 크기 개선을 위한 CSS 주입
st.markdown("""
    <style>
    [data-testid="stCameraInput"] { width: 100% !important; max-width: 100% !important; }
    [data-testid="stCameraInput"] video { width: 100% !important; height: auto !important; border-radius: 10px; }
    /* 썸네일 이미지 스타일 */
    .thumb-container { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
    .thumb-item { border: 2px solid #ddd; border-radius: 5px; overflow: hidden; position: relative; }
    .thumb-item img { display: block; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 세션 상태 관리 (초기화)
# ==========================================
# 촬영/업로드된 이미지 데이터를 담을 딕셔너리 {파일명: 바이너리데이터}
if "image_data_store" not in st.session_state:
    st.session_state.image_data_store = {}

# 카메라 작동 상태
if "camera_enabled" not in st.session_state:
    st.session_state.camera_enabled = False

# OCR 결과 리스트
if "ocr_list" not in st.session_state:
    st.session_state.ocr_list = []

# ==========================================
# 3. 이미지 입력 섹션 (탭 구성)
# ==========================================
tab1, tab2 = st.tabs(["📸 카메라 촬영", "📁 사진 다중 업로드"])

# --- 탭 1: 카메라 촬영 ---
with tab1:
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
        # CSS 영향으로 크게 표시됨
        cam_file = st.camera_input("책장을 정면에서 촬영해주세요")
        if cam_file:
            st.session_state.image_data_store["camera_shot.jpg"] = cam_file.getvalue()
            st.success("사진이 촬영되어 분석 대기열에 추가되었습니다.")

# --- 탭 2: 사진 다중 업로드 ---
with tab2:
    st.subheader("갤러리 업로드")
    uploaded_files = st.file_uploader("사진들을 선택하세요 (여러 장 가능)", 
                                      type=['jpg', 'jpeg', 'png'], 
                                      accept_multiple_files=True)
    if uploaded_files:
        for f in uploaded_files:
            st.session_state.image_data_store[f.name] = f.getvalue()
        st.success(f"{len(uploaded_files)}장의 사진이 대기열에 추가되었습니다.")

# ==========================================
# 4. 🔥 이미지 미리보기 (Image Preview) 섹션
# ==========================================
if st.session_state.image_data_store:
    st.divider()
    st.subheader(f"🖼️ 분석 대기 중인 사진 ({len(st.session_state.image_data_store)}장)")
    
    # 초기화 버튼
    if st.button("🗑️ 대기열 전체 삭제", type="secondary"):
        st.session_state.image_data_store = {}
        st.session_state.ocr_list = []
        st.rerun()

    # 썸네일 표시 로직
    cols = st.columns(5) # 한 줄에 5개씩 표시
    for i, (name, data) in enumerate(st.session_state.image_data_store.items()):
        with cols[i % 5]:
            try:
                # 바이너리 데이터를 PIL 이미지로 변환
                img = Image.open(io.BytesIO(data))
                # 썸네일 크기로 조정 (비율 유지)
                img.thumbnail((200, 200))
                # Streamlit 이미지 컴포넌트로 출력
                st.image(img, caption=name, use_container_width=True)
            except Exception as e:
                st.error(f"{name} 로드 실패: {e}")

# ==========================================
# 5. 분석 및 결과 확인 (이전 로직 동일)
# ==========================================
if st.session_state.image_data_store:
    st.divider()
    # 새로운 파일 구성 확인을 위한 해시 생성
    current_files_hash = str(list(st.session_state.image_data_store.keys()))
    if "last_files_hash" not in st.session_state or st.session_state.last_files_hash != current_files_hash:
        st.session_state.ocr_list = []
        st.session_state.last_files_hash = current_files_hash

    # --- OCR 분석 시작 버튼 ---
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
            
            # 중복 체크 로직
            df_tmp = pd.DataFrame(all_books)
            if not df_tmp.empty:
                df_tmp['상태'] = df_tmp.duplicated(subset=['original'], keep='first').map({True: '⚠️ 중복', False: '정상'})
                st.session_state.ocr_list = df_tmp.to_dict('records')
            st.rerun()

    # --- 결과 편집 및 검색 ---
    if st.session_state.ocr_list:
        st.subheader("📝 추출된 도서 리스트 (편집 가능)")
        df = pd.DataFrame(st.session_state.ocr_list)
        
        # 중복 항목 하이라이트 함수
        def highlight_dup(row):
            return ['background-color: #FFCDD2' if row['상태'] == '⚠️ 중복' else '' for _ in row]

        # 데이터 에디터 출력
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

        # 🔍 국회도서관 API 검색 (최적화 버전)
        if st.button("📚 국회도서관 소장 여부 확인 (중복 제외 검색)", use_container_width=True):
            final_results = []
            # 검색 시에는 중복을 제외한 유니크한 항목만 추출
            unique_targets = edited_df.drop_duplicates(subset=['original'])
            
            progress_bar = st.progress(0)
            for i, (idx, row) in enumerate(unique_targets.iterrows()):
                params = {
                    'ServiceKey': NAL_API_KEY,
                    'search': f"자료명, {row['original']}",
                    'displaylines': 5
                }
                
                try:
                    res = requests.get("http://apis.data.go.kr/9720000/searchservice/basic", params=params)
                    root = ET.fromstring(res.content)
                    count = root.findtext('total') or "0"
                    
                    # 모든 검색 결과 수집 (recode 오타 반영)
                    titles = []
                    for record in root.findall('.//recode'):
                        for item in record.findall('item'):
                            if item.findtext('name') == "자료명": # '자료명' 항목 추출
                                titles.append(item.findtext('value'))
                                break
                    
                    display_titles = "\n".join(titles) if titles else "정보 없음"
                    final_results.append({
                        "내 책(독음)": row['display'],
                        "원문(한자)": row['original'],
                        "소장수": count,
                        "국회도서관 확인명": display_titles
                    })
                except Exception:
                    final_results.append({"내 책(독음)": row['display'], "원문(한자)": row['original'], "소장수": "에러", "국회도서관 확인명": "-"})
                
                progress_bar.progress((i + 1) / len(unique_targets))

            st.subheader("✅ 검색 결과 요약")
            st.dataframe(pd.DataFrame(final_results), use_container_width=True)
            
            # CSV 다운로드
            csv = pd.DataFrame(final_results).to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 결과를 CSV로 저장", data=csv, file_name="nal_search_result.csv", mime="text/csv")