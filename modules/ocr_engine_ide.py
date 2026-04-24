# 파일명: modules/ocr_engine_ide.py
# 지시사항: 
# 1. 좌측 도서부터 순서대로 인식
# 2. 중복 도서를 생략하지 않고 눈에 보이는 권수만큼 모두 추출
# 3. 책의 일부가 잘렸거나 글씨가 작아 추출이 어려운 경우 'OCR 불가'로 반환하도록 지시사항 추가
# 4. 불필요해진 번역 항목 제외

import json
import pandas as pd

def extract_books_from_images(model, image_data_store, progress_callback=None):
    all_books = []
    file_names = list(image_data_store.keys())
    
    for i, name in enumerate(file_names):
        data = image_data_store[name]
        
        # 💡 [프롬프트 개선] OCR 불가 처리 지시사항(3번) 추가
        prompt = """
                이 사진 속 책 제목들을 추출해줘. 세로쓰기를 고려해줘. 
                [매우 중요 사항 5가지]:
                1. 반드시 사진의 '좌측'에 꽂힌 책부터 '우측' 방향으로 순서대로 추출해줘. (왼쪽에 있는 책이 배열의 가장 앞쪽에 와야 함)
                2. 제목이 완전히 똑같은 책(복본, 동일 시리즈 등)이 여러 권 꽂혀 있더라도 절대 생략하거나 요약하지 마. 눈에 보이는 물리적인 책의 권수만큼 동일한 제목을 중복해서 모두 배열에 담아줘.
                3. 책이 꽂혀 있는 것은 인식되지만, 일부가 잘렸거나 글씨가 너무 작아 제목을 추출하기 어려운 경우, 해당 책을 배열에서 누락시키지 말고 'original' 값을 'OCR 불가'로 반환해줘.
                4. 책 제목을 임의로 번역하거나 한글로 해석(독음)하지 마. 한자, 영어, 일본어 등 사진에 보이는 텍스트 원문(글자) 그대로 정확하게 추출해줘.
                5. 결과는 반드시 {'books': [{'original': '원문'}]} 형식의 JSON으로만 답해줘.
                """
        
        try:
            response = model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': data}])
            raw_text = response.text.replace('```json', '').replace('```', '').strip()
            ocr_data = json.loads(raw_text)
            
            for book in ocr_data.get('books', []):
                book['source_image'] = name
                all_books.append(book)
                
        except Exception as e:
            print(f"❌ [{name}] OCR 처리 중 에러 발생: {e}")
            continue
        
        if progress_callback:
            progress_callback((i + 1) / len(file_names))
    
    df_tmp = pd.DataFrame(all_books)
    if not df_tmp.empty:
        df_tmp['상태'] = df_tmp.duplicated(subset=['original'], keep='first').map({True: '⚠️ 중복', False: '정상'})
        return df_tmp.to_dict('records')
    return []