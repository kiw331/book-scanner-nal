"""
파일명: app.py
지시사항: Streamlit Cloud 배포용 코드입니다. 
API 키는 소스코드에 적지 않고 Streamlit Secrets 기능을 활용합니다.
"""

import streamlit as st
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
import pandas as pd

# 1. 보안 설정: Streamlit Secrets에서 키 불러오기
# (배포 후 Streamlit Cloud 설정창에서 입력할 예정입니다)
try:
    GEMINI_API_KEY = st.secrets["GEMINI_KEY"]
    NAL_API_KEY = st.secrets["NAL_KEY"]
except:
    st.error("API 키 설정이 필요합니다. Streamlit Cloud의 Secrets 설정을 확인하세요.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="한의학 서적 정리", layout="wide")
st.title("📚 한의학 서적 정리 도우미")

# 2. 카메라 입력 (모바일 크롬에서 작동)
img_file = st.camera_input("책장을 정면에서 촬영해주세요")

if img_file:
    # OCR 수행 (한 번만 실행되도록 세션 상태 활용)
    if 'ocr_list' not in st.session_state:
        with st.spinner('Gemini가 한자를 읽고 있습니다...'):
            img_data = img_file.getvalue()
            # Gemini Vision 프로프프 설정
            prompt = "이 사진 속 책 제목들을 추출해줘. 세로쓰기를 고려해줘. 결과는 반드시 {'books': [{'original': '원문한자', 'display': '한글독음'}]} 형식의 JSON으로만 답해줘."
            response = model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': img_data}])
            
            # JSON 텍스트만 추출하여 파싱 (정규표현식 대신 간단한 처리)
            try:
                raw_text = response.text.replace('```json', '').replace('```', '').strip()
                st.session_state.ocr_list = eval(raw_text)['books']
            except:
                st.error("OCR 결과 해석에 실패했습니다. 다시 찍어보세요.")
                st.stop()

    # 3. 데이터 편집 (사용자 수정 단계)
    st.subheader("📝 OCR 결과 확인 및 수정")
    df = pd.DataFrame(st.session_state.ocr_list)
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

    # 4. 국회도서관 검색
    if st.button("국회도서관 소장 여부 일괄 확인"):
        final_results = []
        progress_bar = st.progress(0)
        
        for i, row in edited_df.iterrows():
            # 실제 API 호출 (가이드의 'recode' 오타 반영)
            params = {
                'ServiceKey': NAL_API_KEY,
                'search': f"자료명, {row['original']}",
                'displaylines': 3
            }
            
            try:
                res = requests.get("http://apis.data.go.kr/9720000/searchservice/basic", params=params)
                root = ET.fromstring(res.content)
                count = root.findtext('total') or "0"
                
                # 'recode' 태그 내 '자료명' 추출
                first_book = "없음"
                records = root.findall('.//recode')
                if records:
                    for item in records[0].findall('item'):
                        if item.findtext('name') == "자료명":
                            first_book = item.findtext('value')
                            break
                
                final_results.append({
                    "내 책": row['display'],
                    "소장수": count,
                    "도서관 확인명": first_book
                })
            except:
                final_results.append({"내 책": row['display'], "소장수": "오류", "도서관 확인명": "-"})
            
            progress_bar.progress((i + 1) / len(edited_df))

        # 5. 최종 결과 표
        st.subheader("✅ 최종 확인 리스트")
        st.dataframe(pd.DataFrame(final_results), use_container_width=True)
        st.success("작업이 완료되었습니다!")