# RFP 제안서 작성기

공공 RFP 문서를 분석하여 제안서 초안을 작성하는 도구입니다. PDF 업로드 한 번으로 요구사항·목차 자동 추출 → 전략가 ↔ 비평가 토론 → 장표별 초안 작성까지 한 번에 진행할 수 있습니다.

## 주요 기능

- **RFP 자동 파싱** — PDF에서 요구사항·목차 추출 (텍스트 기반)
- **VLLM 기반 보조 추출** — 표·도표·이미지가 많은 페이지는 vision LLM(gpt-5.4)으로 OCR
- **전략가 ↔ 비평가 다중 라운드 토론** — 챕터별로 평가위원 관점 비평 + 개선
- **소제목 단위 병렬 초안 작성** — outline + scope 기반 병렬 호출로 빠른 초안 생성
- **참고 문서 반영** — 회사소개서·이전 제안서·기술백서 등 업로드 시 본문에 자동 반영
- **마크다운 다운로드** — 챕터별 전체 컨텍스트(전략·논의·참고문서·초안) 패키지로 export
- **목차 직접 편집** — UI에서 슬라이드 추가/삭제, 요구사항 매핑 수정 가능
- **엑셀 다운로드** — 요구사항·목차 두 시트로 정리 export

## 시작하기

### 1. API 키 설정 (필수)

`.env.example` 파일을 복사해서 `.env`로 이름 변경 후, 본인의 OpenAI API 키 입력:

```
OPENAI_API_KEY=sk-...
```

API 키 발급: https://platform.openai.com/api-keys

### 2. 실행

**Windows (비개발자용)**

`제안서작성기실행.bat` 더블클릭.
- 첫 실행 시 Python 3.12 + 필요 패키지 자동 다운로드 (5~10분, ~500MB, 인터넷 필요)
- 이후 실행은 즉시
- 자동으로 브라우저(http://localhost:8501) 열림

**개발자용 (Python 환경 이미 있음)**

```bash
pip install -r requirements.txt
streamlit run app.py
```

### 3. 사용 흐름

1. 사이드바에서 RFP PDF 업로드 → 요구사항·목차 자동 추출
2. **목차 구성 탭**: 자동 추출 결과 확인·수정, 필요시 VLLM으로 재추출
3. **전략 수립 탭**: 챕터 선택 → 사전 의견·참고문서 입력 → 전략 토론 → 장표별 초안 작성
4. 챕터 완료 시 마크다운 다운로드 → Claude/GPT 등에 넘겨 PPT 변환 또는 직접 편집

자세한 사용법은 `사용법.txt` 참고.

## 사용 모델

- **gpt-5.4** (전략 토론·장표 작성·VLLM 파싱)
- **gpt-4o-mini** (요구사항/목차 LLM 파싱 — 비용 절감)

## 의존성

- Python 3.12+
- streamlit, openai, pymupdf, pdfplumber, openpyxl, python-dotenv

자세한 버전은 `requirements.txt` 참고.

## 폴더 구조

```
.
├── app.py                       메인 Streamlit 앱
├── modules/
│   ├── parser.py                PDF 파싱 + VLLM
│   ├── strategist.py            전략가/비평가/정리 LLM
│   ├── drafter.py               장표 초안 생성
│   ├── slide_manager.py         슬라이드-요구사항 매핑
│   ├── excel_manager.py         엑셀 export
│   └── llm.py                   OpenAI 클라이언트
├── 제안서작성기실행.bat          더블클릭 실행 (Windows)
├── 배포준비.bat                 개발자용 — Python+패키지 사전 설치
├── 사용법.txt                   비개발자 안내
├── requirements.txt
├── .env.example                 API 키 템플릿
└── README.md
```

## 주의사항

- **API 비용**: OpenAI 종량제. RFP 1건 처리에 대략 $1~5 (참고문서 양에 따라 다름)
- **VLLM 비용 주의**: 28페이지 vision 호출 시 ~$1 발생 가능
- **민감 정보**: PDF 내용·전략 등이 OpenAI로 전송됨. 보안 등급 높은 RFP는 사용 전 검토 필요
- **`.env` 파일은 절대 공유 금지** (API 키 노출 시 무단 사용 위험)

## 라이선스

(미정)
