"""
파일명: modules/ocr_engine.py
지시사항: Gemini AI를 사용하여 이미지에서 도서명과 한글 독음을 추출하고 DataFrame 형태의 딕셔너리로 반환합니다.
"""
import json
import pandas as pd
import streamlit as st  # 💡 [추가] Streamlit 모듈 불러오기

def extract_books_from_images(model, image_data_store, progress_callback=None):
    all_books = []
    file_names = list(image_data_store.keys())
    
    for i, name in enumerate(file_names):
        data = image_data_store[name]
        prompt = "이 사진 속 책 제목들을 추출해줘. 세로쓰기를 고려해줘. 결과는 반드시 {'books': [{'original': '원문한자', 'display': '한글독음'}]} 형식의 JSON으로만 답해줘."
        try:
            response = model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': data}])
            raw_text = response.text.replace('```json', '').replace('```', '').strip()
            ocr_data = json.loads(raw_text)
            all_books.extend(ocr_data.get('books', []))
        except Exception as e:
            # 💡 [수정] print 대신 웹 화면에 에러 메세지를 바로 띄웁니다!
            st.error(f"❌ [{name}] OCR 처리 중 에러 발생: {e}")
            continue
        
        # 진행률 바 업데이트를 위한 콜백
        if progress_callback:
            progress_callback((i + 1) / len(file_names))
    
    df_tmp = pd.DataFrame(all_books)
    if not df_tmp.empty:
        df_tmp['상태'] = df_tmp.duplicated(subset=['original'], keep='first').map({True: '⚠️ 중복', False: '정상'})
        return df_tmp.to_dict('records')
    return []