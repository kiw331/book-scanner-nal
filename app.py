import streamlit as st
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
import pandas as pd

# 1. 보안 설정: Secrets에서 키 불러오기
try:
    GEMINI_API_KEY = st.secrets["GEMINI_KEY"]
    NAL_API_KEY = st.secrets["NAL_KEY"]
except:
    st.error("API 키 설정이 필요합니다. Streamlit Cloud의 Secrets 설정을 확인하세요.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="한의학 서적 정리", layout="wide")
st.title("📚 한의학 서적 정리 및 국회도서관 검색")

# --- 입력 방식 선택 (탭 또는 나란히 배치) ---
tab1, tab2 = st.tabs(["📸 카메라 촬영", "📁 사진 업로드"])

with tab1:
    cam_file = st.camera_input("책장을 찍어주세요")

with tab2:
    uploaded_file = st.file_uploader("갤러리에서 사진을 선택하세요", type=['jpg', 'jpeg', 'png'])

# 두 입력 중 하나라도 있으면 해당 파일을 선택
target_file = cam_file if cam_file is not None else uploaded_file

# 새로운 사진이 들어오면 이전 OCR 결과 초기화
if target_file:
    # 파일명이 바뀌거나 새로운 데이터가 들어오면 세션 초기화
    if "last_uploaded_file" not in st.session_state or st.session_state.last_uploaded_file != target_file.name:
        if 'ocr_list' in st.session_state:
            del st.session_state.ocr_list
        st.session_state.last_uploaded_file = target_file.name

    # 2. OCR 수행
    if 'ocr_list' not in st.session_state:
        with st.spinner('Gemini가 책 제목을 분석 중입니다...'):
            img_data = target_file.getvalue()
            prompt = "이 사진 속 책 제목들을 추출해줘. 세로쓰기를 고려해줘. 결과는 반드시 {'books': [{'original': '원문한자', 'display': '한글독음'}]} 형식의 JSON으로만 답해줘."
            response = model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': img_data}])
            
            try:
                raw_text = response.text.replace('```json', '').replace('```', '').strip()
                st.session_state.ocr_list = eval(raw_text)['books']
            except:
                st.error("OCR 해석 실패. 사진을 더 밝은 곳에서 다시 찍어보세요.")
                st.stop()

    # 3. 데이터 편집 및 검색 (이전 로직 동일)
    st.subheader("📝 추출된 도서 리스트 (수정 가능)")
    df = pd.DataFrame(st.session_state.ocr_list)
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

    if st.button("국회도서관 소장 여부 일괄 확인"):
        final_results = []
        progress_bar = st.progress(0)
        
        for i, row in edited_df.iterrows():
            # 국회도서관 API 호출 [cite: 1, 3, 11]
            params = {
                'ServiceKey': NAL_API_KEY,
                'search': f"자료명, {row['original']}", # 원문으로 검색 [cite: 159, 193]
                'displaylines': 3
            }
            
            try:
                res = requests.get("http://apis.data.go.kr/9720000/searchservice/basic", params=params)
                root = ET.fromstring(res.content)
                count = root.findtext('total') or "0"
                
                # 'recode' 태그와 '자료명' 항목 처리
                first_book = "정보 없음"
                records = root.findall('.//recode')
                if records:
                    for item in records[0].findall('item'):
                        if item.findtext('name') == "자료명":
                            first_book = item.findtext('value')
                            break
                
                final_results.append({
                    "내 책": row['display'],
                    "소장수": count,
                    "국회도서관 확인명": first_book
                })
            except:
                final_results.append({"내 책": row['display'], "소장수": "에러", "국회도서관 확인명": "-"})
            
            progress_bar.progress((i + 1) / len(edited_df))

        st.subheader("✅ 검색 결과 요약")
        st.dataframe(pd.DataFrame(final_results), use_container_width=True)
        
        # 엑셀/CSV 다운로드 기능 추가
        csv_data = pd.DataFrame(final_results).to_csv(index=False).encode('utf-8-sig')
        st.download_button("결과를 CSV로 저장하기", data=csv_data, file_name="book_search_result.csv", mime="text/csv")