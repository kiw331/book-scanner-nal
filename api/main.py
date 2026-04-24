# 파일명: main.py
# 지시사항: 
# 1. OCR 추출 및 API 검색 결과를 바로 xlsx (엑셀) 파일로 저장하며 파일명에 '_raw'를 추가합니다.
# 2. "중복 행번호"는 2회 이상 등장하는 동일 도서에 대해서만 최초 인덱스를 기입하고, 단일 도서는 빈칸으로 둡니다.
# 3. OCR결과가 "OCR 불가"일 경우 검색을 생략하고 중복 체크에서도 제외합니다.

import os
import shutil
import pandas as pd
import google.generativeai as genai
from datetime import datetime
import tomllib  
import time

# 커스텀 모듈 임포트
from modules.ocr_engine_ide import extract_books_from_images
from modules.nal_search import fetch_nal_data, parse_and_sort_nal_response

# ==========================================
# 1. API 키 로드 및 기본 설정
# ==========================================
SECRETS_PATH = os.path.join("config", "secrets.toml")

try:
    with open(SECRETS_PATH, "rb") as f:
        secrets = tomllib.load(f)
        
    GEMINI_API_KEY = secrets.get("GEMINI_KEY")
    NAL_API_KEY = secrets.get("NAL_KEY")
    
    if not GEMINI_API_KEY or not NAL_API_KEY:
        raise ValueError("secrets.toml 파일에 GEMINI_KEY 또는 NAL_KEY가 없습니다.")
        
except FileNotFoundError:
    print(f"❌ 설정 파일을 찾을 수 없습니다. 경로를 확인해주세요: {SECRETS_PATH}")
    exit(1)
except Exception as e:
    print(f"❌ API 키를 불러오는 중 오류가 발생했습니다: {e}")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-3-flash-preview')

# 입출력 폴더 경로 설정
# INPUT_DIR = os.path.join("data", "0324_crop")
INPUT_DIR = os.path.join("data", "extra")

OUTPUT_DIR = "output"

# 출력 폴더가 없으면 자동 생성
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    print(f"📁 [{OUTPUT_DIR}] 폴더를 생성했습니다.")

def main():
    # ==========================================
    # 2. 입력 폴더에서 이미지 파일 읽어오기
    # ==========================================
    if not os.path.exists(INPUT_DIR):
        print(f"❌ 입력 폴더를 찾을 수 없습니다: {INPUT_DIR}")
        return

    # 이미지 확장자 필터링
    image_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    if not image_files:
        print(f"⚠️ [{INPUT_DIR}] 폴더 안에 이미지 파일이 없습니다.")
        return

    print(f"\n📸 총 {len(image_files)}장의 사진을 메모리에 불러오는 중...")
    
    image_data_store = {}
    for file_name in image_files:
        file_path = os.path.join(INPUT_DIR, file_name)
        with open(file_path, "rb") as f:
            image_data_store[file_name] = f.read()

    # ==========================================
    # 3. OCR 분석 실행
    # ==========================================
    print("\n[1단계] 이미지에서 텍스트 추출을 시작합니다.")
    
    def print_progress(progress_ratio):
        print(f"   진행률: {progress_ratio * 100:.1f}%")

    ocr_list = extract_books_from_images(model, image_data_store, progress_callback=print_progress)
    
    if not ocr_list:
        print("❌ 추출된 도서 데이터가 없습니다. 프로그램을 종료합니다.")
        return

    # ==========================================
    # 4. 데이터 전처리 및 중복 기준점 계산
    # ==========================================
    work_df = pd.DataFrame(ocr_list)
    work_df['행번호'] = work_df.index
    
    # 💡 [핵심 추가] 전체 목록에서 2번 이상 등장하는 책의 제목만 추려냅니다.
    counts = work_df['original'].value_counts()
    duplicate_titles = set(counts[counts >= 2].index)
    
    # 각 원문(도서명)이 처음 등장하는 0-based 인덱스를 기록
    first_occurrences = work_df.drop_duplicates(subset=['original'], keep='first')
    first_idx_map = dict(zip(first_occurrences['original'], first_occurrences['행번호']))

    # ==========================================
    # 5. 국회도서관 API 검색
    # ==========================================
    unique_queries = first_occurrences['original'].tolist()
    nal_results_map = {}
    
    print(f"\n[2단계] 총 {len(unique_queries)}건의 고유 도서에 대해 국회도서관 검색을 시작합니다.")
    
    for i, query in enumerate(unique_queries):
        if query == "OCR 불가":
            continue
            
        time.sleep(0.5) # API 트래픽 제한 방어 로직 (0.5초 대기)
        
        try:
            xml_content = fetch_nal_data(NAL_API_KEY, query, displaylines=100)
            count, found_books = parse_and_sort_nal_response(xml_content, query)
            
            unique_books = []
            seen_titles = set()
            for b in found_books:
                if b["title"] not in seen_titles:
                    unique_books.append(b)
                    seen_titles.add(b["title"])
            unique_books = unique_books[:1]
            
            nal_results_map[query] = {
                "응답수": count,
                "국회도서관 확인명": "\n".join([b["title"] for b in unique_books]) if unique_books else "",
                "저자": "\n".join([b["author"] for b in unique_books]) if unique_books else "",
                "발행처": "\n".join([b["publisher"] for b in unique_books]) if unique_books else ""
            }
        except Exception as e:
            print(f"⚠️ [{query}] 검색 중 오류 발생: {e}")
            nal_results_map[query] = {"응답수": "에러", "국회도서관 확인명": "", "저자": "", "발행처": ""}
            
        if (i + 1) % 10 == 0 or (i + 1) == len(unique_queries):
            print(f"   검색 진행 상황: {i + 1} / {len(unique_queries)}")

    # ==========================================
    # 6. 최종 결과 조립 및 파일 저장 (xlsx)
    # ==========================================
    print("\n[3단계] 최종 데이터 조립 및 저장을 진행합니다.")
    final_results = []
    
    for idx, row in work_df.iterrows():
        q = row['original']
        
        # 1. idx (1부터 시작)
        df_idx = idx + 1
        
        # 2. 위치 (이미지 파일명에서 확장자 제거하여 매핑)
        img_name = row.get('source_image', '')
        location = os.path.splitext(img_name)[0]
        
        # 💡 3. "OCR 불가" 데이터 처리 및 중복 행번호 분기
        if q == "OCR 불가":
            exist_flag = "FALSE"
            nal_data = {}
            first_idx_val = "" # OCR 불가는 중복 행번호 빈칸
        else:
            nal_data = nal_results_map.get(q, {})
            count = nal_data.get("응답수", "에러")
            
            if count == "에러":
                exist_flag = "ERROR"
            elif str(count) == "0":
                exist_flag = "FALSE"
            else:
                exist_flag = "TRUE"
                
            # 💡 [핵심 수정] 2회 이상 등장한 제목만 본인의 첫 번째 인덱스 부여, 나머지는 빈칸
            if q in duplicate_titles:
                first_idx_val = first_idx_map.get(q, idx) + 1
            else:
                first_idx_val = ""
        
        # 새로운 양식으로 딕셔너리 구성
        final_results.append({
            "idx": df_idx,
            "위치": location,
            "OCR결과": q,
            "검색결과 유무": exist_flag,
            "국회도서관 확인명": nal_data.get("국회도서관 확인명", ""),
            "저자": nal_data.get("저자", ""),
            "발행처": nal_data.get("발행처", ""),
            "중복 행번호": first_idx_val,  # 수정된 값 적용
            "처리구분": "",
            "비고": ""
        })

    res_df = pd.DataFrame(final_results)
    
    # xlsx 확장자 및 _raw 파일명 적용
    current_time = datetime.now().strftime("%m%d%H%M")
    xlsx_filename = f"nal{current_time}_results_raw.xlsx"
    xlsx_path = os.path.join(OUTPUT_DIR, xlsx_filename)
    
    # Excel 파일로 바로 저장 (index 미포함)
    res_df.to_excel(xlsx_path, index=False)
    print(f"✅ 엑셀(xlsx) 결과 저장 완료: {xlsx_path}")

    # 이미지 이름 변경하여 복사 저장
    print("🖼️ 원본 이미지 복사 및 이름 매핑 중...")
    for img_name in image_files:
        base_name, ext = os.path.splitext(img_name)
        original_path = os.path.join(INPUT_DIR, img_name)
        
        img_rows = work_df[work_df['source_image'] == img_name]
        
        if not img_rows.empty:
            start_idx = img_rows.index.min() + 1
            end_idx = img_rows.index.max() + 1
            new_img_name = f"{base_name}_{start_idx}_{end_idx}{ext}"
        else:
            new_img_name = f"{base_name}_none{ext}"
            
        new_path = os.path.join(OUTPUT_DIR, new_img_name)
        shutil.copy2(original_path, new_path)
        print(f"   복사됨: {img_name} -> {new_img_name}")

    print("\n🎉 모든 작업이 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    main()