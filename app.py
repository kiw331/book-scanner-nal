import streamlit as st
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import json

# 1. 보안 설정: Secrets에서 키 불러오기
try:
    GEMINI_API_KEY = st.secrets["GEMINI_KEY"]
    NAL_API_KEY = st.secrets["NAL_KEY"]
except:
    st.error("API 키 설정이 필요합니다. Streamlit Cloud의 Secrets 설정을 확인하세요.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
# 최신 모델 명칭 사용
model = genai.GenerativeModel('models/gemini-3-flash-preview')

st.set_page_config(page_title="한의학 서적 정리", layout="wide")
st.title("📚 한의학 서적 다중 정리 및 국회도서관 검색")

# --- 입력 방식 선택 ---
tab1, tab2 = st.tabs(["📸 카메라 촬영", "📁 사진 다중 업로드"])

with tab1:
    cam_file = st.camera_input("책장을 찍어주세요")

with tab2:
    # accept_multiple_files=True 옵션 추가
    uploaded_files = st.file_uploader("갤러리에서 사진들을 선택하세요 (여러 장 가능)", 
                                      type=['jpg', 'jpeg', 'png'], 
                                      accept_multiple_files=True)

# 처리할 파일 리스트 만들기
files_to_process = []
if cam_file:
    files_to_process.append(cam_file)
if uploaded_files:
    files_to_process.extend(uploaded_files)

# 새로운 파일 구성이 들어오면 세션 초기화 로직
current_files_hash = str([f.name for f in files_to_process])
if files_to_process:
    if "last_files_hash" not in st.session_state or st.session_state.last_files_hash != current_files_hash:
        st.session_state.ocr_list = []
        st.session_state.last_files_hash = current_files_hash

    # 2. OCR 수행 (모든 사진 순차 처리)
    if not st.session_state.get('ocr_list'):
        all_detected_books = []
        with st.spinner(f'Gemini가 {len(files_to_process)}장의 사진을 분석 중입니다...'):
            for file in files_to_process:
                img_data = file.getvalue()
                prompt = "이 사진 속 책 제목들을 추출해줘. 세로쓰기를 고려해줘. 결과는 반드시 {'books': [{'original': '원문한자', 'display': '한글독음'}]} 형식의 JSON으로만 답해줘."
                try:
                    response = model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': img_data}])
                    raw_text = response.text.replace('```json', '').replace('```', '').strip()
                    # JSON 파싱 후 리스트에 추가
                    data = json.loads(raw_text)
                    all_detected_books.extend(data.get('books', []))
                except Exception as e:
                    st.warning(f"{file.name} 분석 중 오류 발생: {e}")
            
            # 중복 제거 (원문 기준)
            unique_books = {b['original']: b for b in all_detected_books}.values()
            st.session_state.ocr_list = list(unique_books)

    # 3. 데이터 편집 및 검색
    if st.session_state.ocr_list:
        st.subheader(f"📝 추출된 도서 리스트 (총 {len(st.session_state.ocr_list)}권)")
        df = pd.DataFrame(st.session_state.ocr_list)
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

        if st.button("국회도서관 소장 여부 일괄 확인"):
            final_results = []
            progress_bar = st.progress(0)
            
            for i, row in edited_df.iterrows():
                params = {
                    'ServiceKey': NAL_API_KEY,
                    'search': f"자료명, {row['original']}", 
                    'displaylines': 5
                }
                
                try:
                    res = requests.get("http://apis.data.go.kr/9720000/searchservice/basic", params=params)
                    root = ET.fromstring(res.content)
                    count = root.findtext('total') or "0"
                    
                    found_titles = []
                    records = root.findall('.//recode') # 오타 반영
                    for record in records:
                        for item in record.findall('item'):
                            if item.findtext('name') == "자료명":
                                found_titles.append(item.findtext('value'))
                                break
                    
                    display_titles = "\n".join(found_titles) if found_titles else "정보 없음"
                    
                    final_results.append({
                        "내 책": row['display'],
                        "원문": row['original'],
                        "소장수": count,
                        "국회도서관 확인명": display_titles
                    })
                except:
                    final_results.append({"내 책": row['display'], "원문": row['original'], "소장수": "에러", "국회도서관 확인명": "-"})
                
                progress_bar.progress((i + 1) / len(edited_df))

            st.subheader("✅ 검색 결과 요약")
            st.dataframe(pd.DataFrame(final_results), use_container_width=True)
            
            csv_data = pd.DataFrame(final_results).to_csv(index=False).encode('utf-8-sig')
            st.download_button("결과를 CSV로 저장하기", data=csv_data, file_name="book_search_result.csv", mime="text/csv")