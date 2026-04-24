# API 키 설정

import os
import google.generativeai as genai
import toml

CONFIG_PATH = os.path.join("config", "secrets.toml")

try:
    secrets = toml.load(CONFIG_PATH)
    API_KEY = secrets["GEMINI_KEY"]
except Exception as exc:
    print(f"config/secrets.toml에서 GEMINI_KEY를 읽는 중 오류: {exc}")
    raise SystemExit(1)

genai.configure(api_key=API_KEY)

print("--- 사용 가능한 모델 목록 ---")

try:
    for m in genai.list_models():
        # generateContent 지원 모델만 출력
        if 'generateContent' in m.supported_generation_methods:
            print(f"모델: {m.name}")
except Exception as e:
    print(f"오류 발생: {e}")