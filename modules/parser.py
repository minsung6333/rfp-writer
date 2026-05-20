# -*- coding: utf-8 -*-
import json
import base64
import fitz  # PyMuPDF
import pdfplumber
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

REQ_PARSE_SYSTEM = """당신은 RFP 문서 분석 전문가입니다.
주어진 텍스트에서 제안사가 수행해야 할 요구사항/과업을 추출하여 아래 형식의 JSON으로 반환하세요.

{"requirements": [
  {
    "id": "SFR-001",
    "category": "기능 요구사항",
    "name": "요구사항 명칭",
    "definition": "한 줄 정의 (없으면 빈 문자열)",
    "detail": "세부내용 전체 텍스트"
  }
]}

규칙:
- 요구사항 ID(SFR-, ECR- 등)가 있으면 그대로 사용, 없으면 TASK-001 형식으로 부여
- detail은 원문 텍스트를 그대로 추출 (요약하지 않음)
- 입찰안내, 참가자격, 평가기준, 계약조건, 별지서식은 제외
- 요구사항이 없는 텍스트면 빈 배열 반환
- 반드시 위 JSON 형식만 반환"""

TOC_FROM_REQS_SYSTEM = """당신은 RFP 제안서 전문가입니다.
주어진 요구사항 목록을 분석하여 제안사가 작성해야 할 제안서 목차를 설계해주세요.

{"slides": [
  {
    "chapter": "Ⅱ",
    "section": "1",
    "title": "사업이해도"
  }
]}

규칙:
- 요구사항들을 논리적으로 묶어 제안서 장(章)-절(節) 구조로 설계
- 일반적인 구조 참고: Ⅰ.일반현황 → Ⅱ.전략/이해도 → Ⅲ.기술/기능 → Ⅳ.성능/품질 → Ⅴ.프로젝트관리 → Ⅵ.지원
- 요구사항 분류(SFR=기능, DAR=데이터, SER=보안, PER=성능, PMR=프로젝트관리, PSR=지원 등)를 참고
- 비슷한 요구사항끼리 묶어 하나의 절로 구성 (너무 세분화하지 않음, 총 15~25개 절이 적당)
- 반드시 위 JSON 형식만 반환"""

TOC_PARSE_SYSTEM = """당신은 RFP 문서 분석 전문가입니다.
주어진 텍스트에서 제안사가 작성해야 할 제안서 목차를 추출하여 아래 형식의 JSON으로 반환하세요.

[유형 A] 일반 제안서 목차 (장-절 구조):
{"slides": [
  {"chapter": "Ⅱ", "section": "3", "title": "제품기술(LLM, RAG)"}
]}

[유형 B] 서비스 운영형 평가항목표 (대분류-세부기준 구조):
입력 예: 서비스 지속성 | 재무상태 제시 2점 / 전략 수립 5점 / 조직 구성 8점
         서비스 지원 | 이용 편의성 5점 / 장애대응방안 10점
출력 예: {"slides": [
  {"chapter": "", "section": "", "title": "서비스 지속성"},
  {"chapter": "", "section": "", "title": "서비스 지원"}
]}
→ 대분류 1개 = slide 1개, 세부 기준 행은 절대 개별 slide로 만들지 않음

공통 규칙:
- RFP 문서 자체 목차(사업일반, 입찰 안내 등)는 포함하지 않음
- 제안사가 직접 작성해야 할 항목만 포함
- 점수/배점 정보(~점, 배점, 점수)는 title에 절대 포함하지 않음
- 반드시 위 JSON 형식만 반환"""

# 표준 ID 체계 (고신뢰 - 이게 있으면 이 페이지만 사용)
REQ_KEYWORDS_STRICT = [
    "요구사항 고유번호", "요구사항 ID", "요구사항ID",
    "SFR-", "DAR-", "SER-", "ECR-", "SIR-", "QUR-",
    "TER-", "PMR-", "PSR-", "PER-", "COR-", "NFR-",
]

# 산문형 RFP용 폴백 키워드 (저신뢰 - strict 매칭 없을 때만 사용)
REQ_KEYWORDS_BROAD = [
    "과업 내용", "과업내용", "수행 내용", "수행내용",
    "제안 요청 사항", "제안요청사항", "요청 사항", "요청사항",
    "기술 요구사항", "기능 요구사항", "비기능 요구사항",
    "사업 내용", "사업내용", "과업 범위", "과업범위",
    "세부 과업", "세부과업", "추진 내용", "추진내용",
    "제안요청 세부사항", "제안요청세부사항", "Ⅱ. 제안요청", "Ⅱ 제안요청",
    "운영전략", "수행방안", "운영방안", "추진방안",
    "상담인력", "인력운영", "서비스 수준",
]

# 디버그용 통합 목록
REQ_KEYWORDS = REQ_KEYWORDS_STRICT + REQ_KEYWORDS_BROAD

# 고신뢰: 제안사가 작성해야 할 목차가 있는 페이지
TOC_KEYWORDS_STRICT = [
    "정성 제안서 목차", "제안서 세부 작성 지침", "제안서 작성목차",
    "작성목차", "작성순서",
    "제안서 목차 및 작성 방법", "목차 및 작성 방법",
    "제안서 목차 및 작성내용", "목차 및 작성내용",
    "목차 설정", "제안서 목차(예시)", "작성 방법(예시)",
    "정성적 평가 제안서",
]
# 저신뢰: strict 없을 때 폴백
TOC_KEYWORDS_BROAD = [
    "제안서 목차", "제안서 세부 작성", "작성 지침", "작성지침",
    "제안서 작성 요령", "작성 요령", "제안서 구성",
]

# 평가항목 기반 목차 (서비스 운영형 RFP — 전통적 목차가 없을 때)
TOC_KEYWORDS_EVAL = [
    "제안서 평가 항목", "평가 항목 및 배점", "평가항목및배점",
    "기술평가 항목", "기술평가항목", "세부평가항목",
]
TOC_KEYWORDS = TOC_KEYWORDS_STRICT + TOC_KEYWORDS_BROAD

TOC_SCOUT_SYSTEM = """당신은 RFP 문서 분석 전문가입니다.
아래 페이지들 중 제안사가 작성해야 할 제안서의 "목차 개요"가 담긴 페이지를 찾아주세요.

[찾는 것]
- Ⅰ. 일반현황 / Ⅱ. 기술전략 / Ⅲ. 구현방안 처럼 장(章)-절(節) 계층 목록만 있는 페이지
- 내용이 거의 없고 목차 항목들만 나열된 짧은 페이지
- "제안서 목차", "작성 목차", "작성 방법(예시)" 등의 제목이 붙어 있는 경우 多

[제외]
- 점선(·····)이 많은 문서 자체 TOC 페이지
- 요구사항/과업 내용이 길게 서술된 페이지
- 별지서식, 평가표, 입찰안내 페이지

{"found": true, "pages": [204, 205]}  또는  {"found": false, "pages": []}

반드시 위 JSON 형식만 반환"""


def _is_nav_toc_page(text: str) -> bool:
    """RFP 문서 자체 네비게이션 목차 페이지 판별 (점선 도트가 많은 페이지)."""
    return text.count("·") > 30 or text.count("…") > 10


def _has_proposal_toc_structure(text: str) -> bool:
    """로마숫자 장(章) + 번호 절(節) 구조 감지 — 제안서 목차 페이지 특징."""
    import re
    if _is_nav_toc_page(text):
        return False
    roman = re.findall(r'[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ][\.\s　]', text)
    numbered = re.findall(r'\n[ \t]+\d+[\.\)]\s+\S', text)
    return len(roman) >= 2 and len(numbered) >= 3


def _scout_toc_pages_with_llm(pages: list[dict]) -> str:
    """키워드 매칭 실패 시 LLM이 직접 제안서 목차 페이지를 탐색."""
    n = len(pages)
    # 문서 후반부(60% 이후)에서 탐색 — 제안서 작성 안내는 보통 문서 끝에 위치
    # 텍스트가 짧은 페이지 우선(< 1200자): 목차 페이지는 내용이 적음
    # 점선 많은 네비게이션 TOC 제외
    candidates = [
        p for p in pages[max(0, int(n * 0.6)):]
        if p["text"].strip()
        and not _is_nav_toc_page(p["text"])
        and len(p["text"]) < 1200
    ]

    # 후보가 없으면 범위를 50%로 넓힘
    if not candidates:
        candidates = [
            p for p in pages[max(0, n // 2):]
            if p["text"].strip() and not _is_nav_toc_page(p["text"])
        ]

    if not candidates:
        return ""

    page_map = {p["page"]: p["text"] for p in pages}
    found_page_nums = []

    # 배치당 25페이지씩 LLM에 전달 (짧은 페이지들이라 토큰 여유 있음)
    batch_size = 25
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        summaries = "\n\n---\n\n".join(
            f"[페이지 {p['page']} / {len(p['text'])}자]\n{p['text'].strip()}" for p in batch
        )
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": TOC_SCOUT_SYSTEM},
                    {"role": "user", "content": summaries},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                timeout=30,
            )
            data = json.loads(resp.choices[0].message.content)
            if data.get("found"):
                found_page_nums.extend(data.get("pages", []))
        except Exception as e:
            print(f"TOC 스카우트 오류: {e}")

    if not found_page_nums:
        return ""

    texts = [page_map[pg] for pg in found_page_nums if pg in page_map]
    return "\n\n".join(texts)


def extract_text_by_page(pdf_path: str) -> list[dict]:
    """PyMuPDF로 전체 페이지 빠르게 추출. 공백 깨짐 감지 시 해당 페이지만 pdfplumber로 재추출."""
    # 1단계: PyMuPDF로 전체 빠르게 추출
    fitz_pages = []
    with fitz.open(pdf_path) as pdf:
        for i, page in enumerate(pdf):
            text = page.get_text() or ""
            fitz_pages.append({"page": i + 1, "text": text})

    # 2단계: 공백 깨짐 감지 (한글 연속 비율이 높으면 깨진 것)
    def _is_space_broken(text: str) -> bool:
        import re
        korean_runs = re.findall(r'[가-힣]{6,}', text)
        korean_chars = sum(len(r) for r in korean_runs)
        total_korean = len(re.findall(r'[가-힣]', text))
        return total_korean > 80 and korean_chars / max(total_korean, 1) > 0.4

    # 문서 전반부 제외하고 중간~후반 구간에서 샘플 (앞쪽 목차 페이지는 공백 멀쩡함)
    n = len(fitz_pages)
    sample_range = fitz_pages[max(1, n // 5): min(n, n // 5 + 10)]
    sample_texts = [p["text"] for p in sample_range if p["text"].strip() and len(p["text"]) > 200]
    need_plumber = any(_is_space_broken(t) for t in sample_texts)

    if not need_plumber:
        return fitz_pages

    # 3단계: pdfplumber로 전체 재추출 (공백 복원)
    try:
        plumber_map = {}
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                plumber_map[i + 1] = text
        return [{"page": p["page"], "text": plumber_map.get(p["page"], p["text"])} for p in fitz_pages]
    except Exception:
        return fitz_pages


def _is_task_page(text: str) -> bool:
    """◦ 불릿 밀집 페이지 = 산문형 과업 페이지로 판단."""
    bullets = text.count("◦") + text.count("•") + text.count("○")
    # 임계값 높여서 실제 과업 페이지만 선택
    return bullets >= 6 and len(text) > 300


def find_requirement_pages(pages: list[dict]) -> tuple[str, bool]:
    """요구사항 관련 페이지 텍스트 반환. fallback 여부도 함께 반환."""
    # 1단계: 표준 ID 체계 페이지 (고신뢰)
    strict_pages = [p for p in pages if any(k in p["text"] for k in REQ_KEYWORDS_STRICT)]
    if strict_pages:
        text = "\n\n---PAGE---\n\n".join(p["text"] for p in strict_pages)
        return text, False

    # 2단계: 산문형 키워드 + 불릿 밀집 페이지
    broad_matched = set()
    for p in pages:
        if any(k in p["text"] for k in REQ_KEYWORDS_BROAD):
            broad_matched.add(p["page"])
        if _is_task_page(p["text"]):
            broad_matched.add(p["page"])

    filtered = []
    for p in pages:
        if p["page"] not in broad_matched:
            continue
        if p["text"].count("서식") > 3 and "과업" not in p["text"] and "운영" not in p["text"]:
            continue
        filtered.append(p["text"])

    if filtered:
        return "\n\n---PAGE---\n\n".join(filtered), False

    # 3단계: 전체 문서 폴백
    all_text = "\n\n---PAGE---\n\n".join(p["text"] for p in pages if p["text"].strip())
    return all_text, True


def find_toc_pages(pages: list[dict]) -> str:
    # 1단계: strict 키워드 && 네비게이션 TOC 아닌 페이지 (가장 신뢰)
    strict_content = [p["text"] for p in pages
                      if any(k in p["text"] for k in TOC_KEYWORDS_STRICT)
                      and not _is_nav_toc_page(p["text"])]
    if strict_content:
        return "\n\n".join(strict_content)

    # 2단계: strict 키워드 (네비게이션 포함 — 없는 것보다 나음)
    strict_all = [p["text"] for p in pages
                  if any(k in p["text"] for k in TOC_KEYWORDS_STRICT)]
    if strict_all:
        return "\n\n".join(strict_all)

    # 3단계: broad 키워드 + 네비게이션 아님 + 실제 목차 구조 (로마자/번호 항목 3개+)
    import re as _re
    def _has_listed_structure(text: str) -> bool:
        items = _re.findall(r'\n\s*(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅰⅱⅲⅳⅴ]|[1-9]\d*[\.\)])\s+\S', text)
        return len(items) >= 3

    broad = [p["text"] for p in pages
             if not _is_nav_toc_page(p["text"])
             and any(k in p["text"] for k in TOC_KEYWORDS_BROAD)
             and _has_listed_structure(p["text"])]
    if broad:
        return "\n\n".join(broad)

    # 4단계: 구조 패턴 탐지 — 로마숫자 장 + 번호 절 구조인 짧은 페이지
    n = len(pages)
    structural = [
        p["text"] for p in pages[max(0, int(n * 0.5)):]
        if _has_proposal_toc_structure(p["text"]) and len(p["text"]) < 1500
    ]
    if structural:
        return "\n\n".join(structural)

    # 5단계: 평가항목표 — 서비스 운영형 RFP (전통적 목차 없는 경우)
    # 배점표 실물 페이지만 선택 (참조 문구만 있는 페이지 제외: "배점"이 3번 이상 등장해야 함)
    eval_pages = [p["text"] for p in pages
                  if any(k in p["text"] for k in TOC_KEYWORDS_EVAL)
                  and p["text"].count("배점") >= 3]
    if eval_pages:
        return "\n\n".join(eval_pages)

    # 6단계: broad 폴백 (구조 체크 없이 — 마지막 키워드 기반 수단)
    broad_all = [p["text"] for p in pages
                 if any(k in p["text"] for k in TOC_KEYWORDS_BROAD)
                 and not _is_nav_toc_page(p["text"])]
    if broad_all:
        return "\n\n".join(broad_all)

    # 7단계: LLM 스카우트 — 모든 방법 실패 시 LLM이 직접 탐색
    print("TOC 키워드/패턴 매칭 실패 → LLM 스카우트 탐색 시작")
    return _scout_toc_pages_with_llm(pages)


def parse_chunk(chunk: str) -> list[dict]:
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": REQ_PARSE_SYSTEM},
                {"role": "user", "content": chunk}
            ],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=120,
        )
        data = json.loads(resp.choices[0].message.content)
        return data.get("requirements", [])
    except Exception as e:
        print(f"청크 파싱 오류: {e}")
        return []


def split_req_chunks(text: str, chunk_size: int = 8000) -> list[str]:
    pages = text.split("\n\n---PAGE---\n\n")
    chunks, current, prev = [], "", ""
    for page in pages:
        if len(current) + len(page) > chunk_size and current:
            chunks.append(current)
            current = prev + "\n\n" + page
        else:
            current += "\n\n" + page
        prev = page
    if current:
        chunks.append(current)
    return chunks


def parse_requirements_with_llm(text: str) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor
    chunks = split_req_chunks(text)
    all_requirements = []
    seen_ids = set()
    with ThreadPoolExecutor(max_workers=4) as executor:
        for reqs in executor.map(parse_chunk, chunks):
            for req in reqs:
                rid = req.get("id", "")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    all_requirements.append(req)
    return all_requirements


def parse_toc_with_llm(text: str) -> list[dict]:
    if not text.strip():
        return []
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": TOC_PARSE_SYSTEM},
                {"role": "user", "content": text}
            ],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=120,
        )
        data = json.loads(resp.choices[0].message.content)
        return data.get("slides", [])
    except Exception as e:
        print(f"목차 파싱 오류: {e}")
        return []


def generate_toc_from_requirements(requirements: list[dict]) -> list[dict]:
    if not requirements:
        return []
    req_summary = "\n".join(
        f"[{r.get('id', '')}] {r.get('category', '')} - {r.get('name', '')}"
        for r in requirements[:80]
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": TOC_FROM_REQS_SYSTEM},
                {"role": "user", "content": req_summary},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=60,
        )
        data = json.loads(resp.choices[0].message.content)
        return data.get("slides", [])
    except Exception as e:
        print(f"요구사항 기반 목차 생성 오류: {e}")
        return []


def parse_pdf(pdf_path: str) -> tuple[list[dict], list[dict], bool, bool]:
    """요구사항 목록, 제안서 목차, 폴백 여부, 목차자동생성 여부 반환"""
    pages = extract_text_by_page(pdf_path)
    req_text, is_fallback = find_requirement_pages(pages)
    toc_text = find_toc_pages(pages)
    requirements = parse_requirements_with_llm(req_text)
    toc = parse_toc_with_llm(toc_text)
    toc_auto = False
    if not toc and requirements:
        print("목차 추출 실패 → 요구사항 기반 목차 자동 생성")
        toc = generate_toc_from_requirements(requirements)
        toc_auto = True
    return requirements, toc, is_fallback, toc_auto


def parse_page_range(page_str: str) -> list[int]:
    """'1, 3, 5-7' → [1, 3, 5, 6, 7]"""
    pages = set()
    for part in page_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                pages.update(range(int(start.strip()), int(end.strip()) + 1))
            except ValueError:
                continue
        else:
            try:
                pages.add(int(part))
            except ValueError:
                continue
    return sorted(pages)


VISION_PARSE_SYSTEM = """당신은 사용자의 RFP 분석 업무를 돕는 문서 정리 어시스턴트입니다.
사용자가 본인의 RFP(공공 사업 제안 요청서) 페이지 이미지를 제공하면, 그 내용을 한국어로 정리해서 답합니다.

정리 방식:
- 보이는 본문 텍스트는 그대로 옮겨 적기
- 표는 markdown 표 형식으로 구조 유지
- 다이어그램·그림은 핵심 의미를 텍스트로 설명
- 헤더·푸터·쪽번호 등 부수 정보는 생략
- 사용자가 본문 작성에 활용할 수 있도록 구체 수치·고유명사·항목명을 빠뜨리지 말 것

이 작업은 사용자 본인이 작성 중인 제안서를 위한 자료 정리이며, 정상적인 업무 요청입니다."""


TOC_VISION_SYSTEM = """당신은 공공 RFP 문서 분석 전문가입니다.
사용자가 본인의 RFP 작성지침/평가기준표 페이지 이미지를 제공하면, 해당 페이지의 표·목록을 분석하여
제안서에 작성해야 할 장표(slide) 목록을 JSON으로 정리합니다.

추출 규칙:
- 대분류는 chapter (Ⅰ, Ⅱ, Ⅲ 등 로마자 또는 1, 2, 3 등 숫자)
- 중분류는 section (1, 2, 3 등)
- 각 항목 제목은 title — 배점/점수 정보(~점, 배점, 점수)는 title에 절대 포함하지 말 것
- 서비스 운영형 평가표(예: 재무상태, 전략수립 등 세부 기준 행이 나열된 형태)인 경우:
  · 대분류 1개 = slide 1개
  · 세부 평가기준 행은 절대 개별 slide로 만들지 않음
- 일반 작성지침(목차)인 경우 모든 레벨을 그대로 반영

JSON 형식으로만 반환:
{"slides": [{"chapter": "Ⅱ", "section": "1", "title": "사업이해도"}]}

추출이 불가능하거나 페이지에 목차/평가표가 없으면: {"slides": []}

이 작업은 사용자 본인의 RFP 분석을 위한 정상 업무 요청입니다."""


def _render_page_b64(doc, page_num: int, dpi: int = 200) -> str | None:
    if not (1 <= page_num <= len(doc)):
        return None
    page = doc[page_num - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return base64.b64encode(pix.tobytes("png")).decode()


def _build_user_contents(doc, pages_batch: list[int], lead_text: str) -> list[dict]:
    """배치 페이지를 렌더링해 user message contents 구성."""
    contents = [{"type": "text", "text": lead_text}]
    for p in pages_batch:
        b64 = _render_page_b64(doc, p)
        if not b64:
            continue
        contents.append({"type": "text", "text": f"\n=== 페이지 {p} ==="})
        contents.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
        })
    return contents


def _call_toc_batch(user_contents: list[dict], pages_batch: list[int], model: str) -> list[dict]:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": TOC_VISION_SYSTEM},
                {"role": "user", "content": user_contents},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            reasoning_effort="none",
            timeout=180,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        slides = data.get("slides", [])
        return [
            {
                "chapter": str(s.get("chapter", "")).strip(),
                "section": str(s.get("section", "")).strip(),
                "title": str(s.get("title", "")).strip(),
            }
            for s in slides
            if isinstance(s, dict) and s.get("title")
        ]
    except Exception as e:
        print(f"[VLLM TOC 배치 실패] pages={pages_batch}: {e}")
        return []


def extract_toc_with_vision(pdf_path: str, pages: list[int], model: str = "gpt-5.4",
                             batch_size: int = 3, max_workers: int = 4) -> list[dict]:
    """지정 페이지에서 VLLM으로 목차 추출 (배치 + 병렬)."""
    if not pages:
        return []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    doc = fitz.open(pdf_path)
    max_p = len(doc)
    valid_pages = [p for p in pages if 1 <= p <= max_p]
    batches = [valid_pages[i:i + batch_size] for i in range(0, len(valid_pages), batch_size)]
    print(f"[VLLM TOC] 총 {len(valid_pages)}페이지, {len(batches)}배치, {max_workers}워커 병렬")

    # 이미지 렌더링은 메인 스레드에서 순차 (PyMuPDF는 thread-safe 아님)
    payloads = []
    for idx, batch in enumerate(batches):
        contents = _build_user_contents(doc, batch, "다음 페이지에서 위 지침에 따라 장표 목록을 JSON으로 추출해주세요.")
        payloads.append((idx, batch, contents))
    doc.close()

    # API 호출은 병렬
    results: list[list[dict]] = [[]] * len(batches)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {
            ex.submit(_call_toc_batch, contents, batch, model): idx
            for idx, batch, contents in payloads
        }
        for fut in as_completed(future_map):
            idx = future_map[fut]
            slides = fut.result()
            results[idx] = slides
            print(f"[VLLM TOC] 배치 {idx + 1}/{len(batches)} 완료 → {len(slides)}개")

    # 순서대로 합치고 중복 제거
    all_slides = []
    seen = set()
    for batch_result in results:
        for s in batch_result:
            key = f"{s['chapter']}|{s['section']}|{s['title']}"
            if key not in seen:
                seen.add(key)
                all_slides.append(s)
    print(f"[VLLM TOC] 최종 {len(all_slides)}개 슬라이드")
    return all_slides


def _call_parse_batch(user_contents: list[dict], pages_batch: list[int], model: str) -> str:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": VISION_PARSE_SYSTEM},
                {"role": "user", "content": user_contents},
            ],
            temperature=0,
            reasoning_effort="none",
            timeout=240,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[VLLM 배치 실패 pages={pages_batch}: {e}]"


def parse_pages_with_vision(pdf_path: str, pages: list[int], model: str = "gpt-5.4",
                             batch_size: int = 3, max_workers: int = 4) -> str:
    """지정한 페이지들을 이미지로 렌더링해 vision LLM으로 파싱 (배치 + 병렬)."""
    if not pages:
        return ""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    doc = fitz.open(pdf_path)
    max_p = len(doc)
    valid_pages = [p for p in pages if 1 <= p <= max_p]
    batches = [valid_pages[i:i + batch_size] for i in range(0, len(valid_pages), batch_size)]
    print(f"[VLLM PARSE] 총 {len(valid_pages)}페이지, {len(batches)}배치, {max_workers}워커 병렬")

    # 이미지 렌더링은 순차 (PyMuPDF thread-safe 아님)
    payloads = []
    for idx, batch in enumerate(batches):
        contents = _build_user_contents(doc, batch, "다음 페이지들을 위 지침에 따라 정리해주세요.")
        payloads.append((idx, batch, contents))
    doc.close()

    # API 호출은 병렬
    results: list[str] = [""] * len(batches)
    batch_ranges: list[list[int]] = [[]] * len(batches)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {
            ex.submit(_call_parse_batch, contents, batch, model): (idx, batch)
            for idx, batch, contents in payloads
        }
        for fut in as_completed(future_map):
            idx, batch = future_map[fut]
            text = fut.result()
            results[idx] = text
            batch_ranges[idx] = batch
            print(f"[VLLM PARSE] 배치 {idx + 1}/{len(batches)} 완료 → {len(text)}자")

    parts = []
    for idx, text in enumerate(results):
        if text.strip():
            parts.append(f"### 페이지 {batch_ranges[idx]}\n{text}")
    return "\n\n".join(parts)
