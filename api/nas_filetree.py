import re
import csv
from tqdm import tqdm

def create_file_db(input_txt, output_csv):
    target_exts = {
        'zip', '7z', 'gz', 'tar',
        'xls', 'xlsx', 'xlsm', 'xltx',
        'hwp', 'hwpx', 'pdf',
        'doc', 'docx', 'docs', 'rtf',
        'ppt', 'pptx', 'ppsx', 'pps'
    }

    print("파일을 읽어오는 중...")
    
    # 윈도우 환경에서 발생할 수 있는 여러 인코딩을 순차적으로 시도 (PowerShell의 utf-16 포함)
    encodings = ['utf-8', 'cp949', 'utf-16', 'euc-kr']
    lines = None
    
    for enc in encodings:
        try:
            with open(input_txt, 'r', encoding=enc) as f:
                lines = f.readlines()
            print(f"[{enc}] 인코딩으로 파일을 성공적으로 읽었습니다.")
            break
        except UnicodeError:
            continue
            
    # 모든 인코딩 시도가 실패한 경우, 깨지는 문자를 무시하고 강제로 읽어옵니다.
    if lines is None:
        print("경고: 알 수 없는 인코딩입니다. 일부 문자를 무시하고 강제로 읽기를 시도합니다.")
        with open(input_txt, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

    results = []
    dir_stack = []

    for line in tqdm(lines, desc="파일 트리 분석 중"):
        line = line.rstrip('\n')
        if not line:
            continue

        match = re.match(r'^([\s│├─└]*)(.*)', line)
        if not match:
            continue

        prefix, name = match.groups()
        if not name:
            continue

        if name.startswith('Z:'):
            dir_stack = [(0, '2015이후백업')]
            continue
        elif name.startswith('Y:'):
            dir_stack = [(0, 'AI_MCP')]
            continue

        is_dir = ('├' in prefix) or ('└' in prefix)
        depth = len(prefix)

        if is_dir:
            while dir_stack and dir_stack[-1][0] >= depth:
                dir_stack.pop()
            dir_stack.append((depth, name))
        else:
            ext = name.split('.')[-1].lower() if '.' in name else ''
            
            if ext in target_exts:
                parent_path = "\\".join([d[1] for d in dir_stack])
                full_path = f"{parent_path}\\{name}"
                
                results.append({
                    '파일명': name,
                    '확장자': ext,
                    '상위경로': parent_path,
                    '전체경로': full_path
                })

    with open(output_csv, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['파일명', '확장자', '상위경로', '전체경로'])
        writer.writeheader()
        for row in tqdm(results, desc="CSV 파일 저장 중"):
            writer.writerow(row)
            
    print(f"\n성공적으로 완료되었습니다! 총 {len(results)}개의 유효한 파일이 '{output_csv}'에 저장되었습니다.")

if __name__ == "__main__":
    create_file_db('NAS_LIST.txt', 'NAS_File_DB.csv')