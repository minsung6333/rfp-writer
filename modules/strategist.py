# -*- coding: utf-8 -*-
import json, os
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

NEED_INFO_TAG = "[NEED_INFO]"
NEED_DOC_TAG = "[NEED_DOC]"

STRATEGIST_SYSTEM = """당신은 IT 공공 제안서 전략 전문가입니다.
RFP 요구사항과 평가기준을 분석하여 경쟁력 있는 제안서 작성 전략을 수립합니다.

**중요: 답변은 최대 1000자 이내로 간결하게.**
- 핵심 방향과 스토리라인 2~4줄
- 차별화 포인트 3~5개 (bullet, 구체적으로)
- 불필요한 서론/요약/마무리 멘트 금지

추가 정보나 문서가 필요한 경우 가장 중요한 것 1가지만:
[NEED_INFO] 답변으로 해결되는 질문 (예: 보유 인증, 수행 실적 유무 등)
[NEED_DOC] 문서가 필요한 경우 — 어떤 문서인지와 왜 필요한지 한 줄로

필요한 것이 없으면 태그 없이 전략만 작성하세요."""

CRITIC_SYSTEM = """당신은 RFP 평가위원이자 경쟁사 관점의 전략 비평가입니다.

**중요: 답변은 최대 1000자 이내로 간결하게.**
- 핵심 약점 2~4개 + 각각의 개선 방향 (bullet, 구체적으로)
- 단순 비판 금지, 반드시 개선 방향 포함
- 서론/마무리 멘트 금지

추가 정보나 문서가 필요한 경우 1가지만:
[NEED_INFO] 질문 내용
[NEED_DOC] 필요한 문서 설명

없으면 태그 없이 비평만 작성하세요."""

SUMMARIZER_SYSTEM = """전략가와 비평가의 논의를 종합하여 최종 제안 전략을 정리하세요.

아래 형식으로 작성하세요:

## 핵심 전략 방향
(2~3줄 요약)

## 차별화 포인트
- 포인트 1
- 포인트 2
- ...

## 장표별 작성 가이드
(각 절별 핵심 내용 방향)

## 유의사항
(놓치지 말아야 할 점, 경쟁사 대비 취약점 보완 방법)"""

PAGE_FINDER_SYSTEM = """PDF 페이지 목록에서 주어진 검색 쿼리와 관련된 페이지 번호를 찾으세요.
JSON 형식으로만 반환: {"pages": [1, 3, 5]}
관련 페이지가 없으면: {"pages": []}"""

NEEDED_DOCS_SYSTEM = """당신은 RFP 제안서 작성 전문가입니다.
최종 전략과 챕터 정보를 검토하여, 장표를 구체적이고 설득력 있게 작성하기 위해 추가로 필요한 참고 문서를 판단하세요.

판단 기준:
- 회사의 과거 수행 실적/유사 사례 (구체적으로 어떤 분야?)
- 보유 기술/솔루션 자료 (어떤 기술 스택? 어떤 제품?)
- 인증/자격 증빙 (ISO, 클라우드 인증 등)
- 유사 제안서, 회사소개서, 기술백서
- 평가위원이 신뢰할 만한 객관적 근거 자료

[이미 첨부된 문서]가 있다면 그 외에 추가로 필요한 것만 답하세요.
정말 필요한 문서만 0~3건 추려서 답하세요. 없으면 빈 배열로 답하세요.

JSON 형식으로만 반환:
{"docs": [{"name": "문서 이름", "reason": "왜 필요한지 한 문장으로"}]}"""


def find_relevant_pages(pages: list[dict], query: str) -> list[dict]:
    """쿼리와 관련된 페이지를 LLM으로 찾아 반환. 못 찾으면 빈 리스트."""
    if not pages:
        return []
    summary = "\n".join(
        f"p{p['page']}: {p['text'][:200].replace(chr(10), ' ')}"
        for p in pages
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PAGE_FINDER_SYSTEM},
                {"role": "user", "content": f"검색 쿼리: {query}\n\n{summary}"},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=30,
        )
        data = json.loads(resp.choices[0].message.content)
        relevant = set(data.get("pages", []))
        return [p for p in pages if p["page"] in relevant]
    except Exception:
        return []


def build_chapter_context(chapter: str, slides: list[dict], requirements: list[dict]) -> str:
    req_map = {r["id"]: r for r in requirements}
    chapter_slides = [s for s in slides if s.get("chapter") == chapter]
    lines = [f"## {chapter}장 구성"]
    for slide in chapter_slides:
        lines.append(f"\n### {slide.get('section', '')}. {slide.get('title', '')}")
        for rid in slide.get("linked_reqs", []):
            r = req_map.get(rid)
            if r:
                lines.append(f"- [{rid}] {r['name']}: {r.get('detail', '')[:250]}")
    return "\n".join(lines)


def parse_agent_response(text: str) -> tuple[str, str, str]:
    """
    [NEED_INFO] 또는 [NEED_DOC] 태그 파싱.
    반환: (본문, need_info_질문, need_doc_설명)
    """
    for tag, attr in [(NEED_DOC_TAG, "doc"), (NEED_INFO_TAG, "info")]:
        if tag in text:
            idx = text.index(tag)
            clean = text[:idx].strip()
            content = text[idx + len(tag):].strip()
            if attr == "doc":
                return clean, "", content
            else:
                return clean, content, ""
    return text.strip(), "", ""


def _build_messages(context: str, history: list[dict], ref_text: str = "") -> list[dict]:
    messages = []
    if ref_text:
        messages.append({"role": "user", "content": f"[참고 문서]\n{ref_text}"})
        messages.append({"role": "assistant", "content": "참고 문서 확인했습니다."})
    messages.append({"role": "user", "content": context})
    for h in history:
        role = "user" if h["agent"] == "user" else "assistant"
        messages.append({"role": role, "content": f"[{h['label']}]\n{h['content']}"})
    return messages


def stream_strategist(context: str, history: list[dict], ref_text: str = ""):
    msgs = _build_messages(context, history, ref_text)
    if not history:
        msgs.append({"role": "user", "content": "위 챕터에 대한 제안서 작성 전략을 제시해주세요."})
    else:
        msgs.append({"role": "user", "content": "비평을 반영하여 전략을 보완해주세요."})
    resp = client.chat.completions.create(
        model="gpt-5.4",
        messages=[{"role": "system", "content": STRATEGIST_SYSTEM}] + msgs,
        temperature=0.7,
        stream=True,
        timeout=120,
    )
    for chunk in resp:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def stream_critic(context: str, history: list[dict], ref_text: str = ""):
    msgs = _build_messages(context, history, ref_text)
    msgs.append({"role": "user", "content": "위 전략의 약점을 비평하고 개선 방향을 제시해주세요."})
    resp = client.chat.completions.create(
        model="gpt-5.4",
        messages=[{"role": "system", "content": CRITIC_SYSTEM}] + msgs,
        temperature=0.7,
        stream=True,
        timeout=120,
    )
    for chunk in resp:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


REVISE_STRATEGY_SYSTEM = """당신은 RFP 제안서 전략 전문가입니다.
기존 최종 전략을 유저 의견에 맞춰 갱신하세요.

원칙:
- 유저 의견을 반드시 반영
- 기존 전략의 좋은 부분은 유지
- 구조(## 핵심 전략 방향 / ## 차별화 포인트 / ## 장표별 작성 가이드 / ## 유의사항)는 그대로
- 변경된 내용 중심으로 자연스럽게 갱신
- 추가 설명/머리말 없이 갱신된 전략 본문만 출력"""


def revise_final_strategy(context: str, final_strategy: str, user_addition: str, ref_text: str = "") -> str:
    ref_note = f"\n\n[참고 문서]\n{ref_text[:60000]}" if ref_text else ""
    resp = client.chat.completions.create(
        model="gpt-5.4",
        messages=[
            {"role": "system", "content": REVISE_STRATEGY_SYSTEM},
            {"role": "user", "content": (
                f"{context}\n\n"
                f"[기존 최종 전략]\n{final_strategy}\n\n"
                f"[유저 의견]\n{user_addition}"
                f"{ref_note}"
            )},
        ],
        timeout=120,
    )
    return resp.choices[0].message.content


def check_needed_docs(context: str, final_strategy: str, ref_text: str = "") -> list[dict]:
    """장표 작성에 필요한 추가 문서 목록 반환. 없으면 빈 리스트."""
    ref_note = f"\n\n[이미 첨부된 문서 요약]\n{ref_text[:60000]}" if ref_text else "\n\n[이미 첨부된 문서] 없음"
    try:
        resp = client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {"role": "system", "content": NEEDED_DOCS_SYSTEM},
                {"role": "user", "content": f"{context}\n\n[최종 전략]\n{final_strategy}{ref_note}"},
            ],
            response_format={"type": "json_object"},
            timeout=60,
        )
        return json.loads(resp.choices[0].message.content).get("docs", [])
    except Exception:
        return []


def run_summarizer(context: str, history: list[dict]) -> str:
    debate_text = "\n\n".join(
        f"[{h['label']}]\n{h['content']}" for h in history
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SUMMARIZER_SYSTEM},
            {"role": "user", "content": f"{context}\n\n---\n\n{debate_text}"},
        ],
        temperature=0.5,
        timeout=120,
    )
    return resp.choices[0].message.content
