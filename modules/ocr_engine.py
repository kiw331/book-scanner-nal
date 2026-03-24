# 파일명: modules/ocr_engine.py
# 지시사항: Gemini AI를 사용하여 이미지에서 도서명과 한글 독음을 추출하고 DataFrame 형태의 딕셔너리로 반환합니다. 
# (수정) 각 추출된 데이터에 원본 이미지 파일명(source_image)을 기록하여 나중에 다운로드 시 인덱스를 매핑할 수 있게 합니다.

import json
import pandas as pd
import streamlit as st

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
            
            # 💡 [수정] 추출된 책 정보에 출처 이미지 파일명을 추가
            for book in ocr_data.get('books', []):
                book['source_image'] = name
                all_books.append(book)
                
        except Exception as e:
            st.error(f"❌ [{name}] OCR 처리 중 에러 발생: {e}")
            continue
        
        if progress_callback:
            progress_callback((i + 1) / len(file_names))
    
    df_tmp = pd.DataFrame(all_books)
    if not df_tmp.empty:
        df_tmp['상태'] = df_tmp.duplicated(subset=['original'], keep='first').map({True: '⚠️ 중복', False: '정상'})
        return df_tmp.to_dict('records')
    return []