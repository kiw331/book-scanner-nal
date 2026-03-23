# API 키로 접근 가능한 Gemini 모델 리스트

import google.generativeai as genai

# 본인의 API 키를 입력하세요
API_KEY = ""

genai.configure(api_key=API_KEY)

print("--- 사용 가능한 모델 목록 ---")
try:
    for m in genai.list_models():
        # 콘텐츠 생성(generateContent)이 가능한 모델만 필터링
        if 'generateContent' in m.supported_generation_methods:
            print(f"모델명: {m.name}")
except Exception as e:
    print(f"에러 발생: {e}")