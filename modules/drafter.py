# -*- coding: utf-8 -*-
import json
from .llm import chat_stream, chat

DRAFT_SYSTEM = """당신은 IT 제안서 작성 전문가입니다.
주어진 장표 정보와 요구사항을 바탕으로 제안서 내용을 작성하세요.

작성 원칙:
- 요구사항의 모든 세부항목을 반영
- 전략 방향과 일관성 유지
- 구체적이고 실질적인 내용
- 제안서 문체로 작성 (당사는 ~합니다 형식)
- 소제목과 bullet point를 활용해 가독성 있게"""

DRAFT_WITH_ANSWERS_SYSTEM = """당신은 IT 제안서 작성 전문가입니다.
사용자가 답변한 방향을 반드시 반영하여 제안서 장표 내용을 작성하세요.

작성 원칙:
- 사용자 답변이 핵심 방향 — 반드시 반영
- 요구사항 세부항목 모두 커버
- 전략 방향과 일관성 유지
- 제안서 문체 (당사는 ~합니다)
- 소제목과 bullet point 활용"""

REVISE_SYSTEM = """당신은 IT 제안서 작성 전문가입니다.
기존 초안을 사용자 요청에 맞게 수정하세요.
요구사항 커버리지는 유지하세요."""

REVIEW_SYSTEM = """당신은 제안서 검토 전문가입니다.
요구사항 목록과 초안을 비교하여 반영 여부를 체크하세요.

{"items": [
  {"req_id": "SFR-001", "req_name": "명칭", "covered": true, "note": "어디서 반영됐는지"}
], "overall": "전체 평가 한 줄"}
JSON만 반환하세요."""


def _build_req_context(requirements: list[dict], linked_ids: list[str]) -> str:
    linked = [r for r in requirements if r["id"] in linked_ids]
    if not linked:
        return "없음"
    parts = []
    for r in linked:
        parts.append(f"[{r['id']}] {r['name']}\n정의: {r.get('definition','')}\n세부내용: {r.get('detail','')[:600]}")
    return "\n\n".join(parts)


def generate_draft_stream(slide: dict, requirements: list[dict], strategy: str):
    req_context = _build_req_context(requirements, slide.get("linked_reqs", []))
    messages = [
        {"role": "system", "content": DRAFT_SYSTEM},
        {"role": "user", "content": f"[전략 방향]\n{strategy}\n\n[장표] {slide['title']}\n\n[연결 요구사항]\n{req_context}"}
    ]
    yield from chat_stream(messages, model="gpt-5.4")


def generate_draft_from_answers_stream(slide: dict, requirements: list[dict], strategy: str, qa_pairs: list[dict]):
    req_context = _build_req_context(requirements, slide.get("linked_reqs", []))
    qa_text = "\n".join([f"Q: {qa['q']}\nA: {qa['a']}" for qa in qa_pairs])
    messages = [
        {"role": "system", "content": DRAFT_WITH_ANSWERS_SYSTEM},
        {"role": "user", "content": f"[전략 방향]\n{strategy}\n\n[장표] {slide['title']}\n\n[방향 결정 Q&A]\n{qa_text}\n\n[연결 요구사항]\n{req_context}"}
    ]
    yield from chat_stream(messages, model="gpt-5.4")


def revise_draft_stream(slide: dict, requirements: list[dict], strategy: str, revision_request: str):
    req_context = _build_req_context(requirements, slide.get("linked_reqs", []))
    messages = [
        {"role": "system", "content": REVISE_SYSTEM},
        {"role": "user", "content": f"[장표] {slide['title']}\n\n[전략]\n{strategy}\n\n[요구사항]\n{req_context}\n\n[현재 초안]\n{slide['draft']}\n\n[수정 요청]\n{revision_request}"}
    ]
    yield from chat_stream(messages, model="gpt-5.4")


OUTLINE_SYSTEM = """당신은 IT 제안서 전문가입니다.
장표 정보와 요구사항을 바탕으로 해당 장표의 소제목 목록을 생성하세요.

요구사항:
- 4~6개의 소제목
- 요구사항을 모두 커버
- 각 소제목별 **scope(작성 범위)**를 명시: 다른 소제목과 절대 겹치지 않도록 무엇을 다루고 무엇을 안 다루는지 명확히
- [참고 문서]가 있으면 그 안의 사례·실적·기술 스택을 드러낼 수 있는 소제목 우선

JSON 형식으로만 반환:
{"sections": [
  {"title": "소제목", "scope": "이 소제목에서 다룰 구체 범위 — 다른 소제목과 겹치지 않게 명확히 한 줄로"}
]}"""

SECTION_SYSTEM = """당신은 IT 제안서 작성 전문가입니다.
주어진 소제목과 작성 범위(scope)에 해당하는 제안서 본문을 작성하세요.

작성 원칙:
- **scope 범위 안의 내용만** 작성. 다른 소제목 영역은 침범 금지
- 전략 방향과 일관성 유지
- 제안서 문체 (당사는 ~합니다)
- bullet point와 구체적 수치/방법론 활용
- 400~700자 분량

[참고 문서]가 제공되면 반드시 적극 활용:
- 회사 실적/사례/숫자/기술 스택 등 구체 정보는 참고 문서에서 인용
- 참고 문서에 명시된 사실은 추측 없이 그대로 반영
- 참고 문서 내용을 활용한 부분은 자연스럽게 본문에 녹여 작성 (출처 표시 X)
- 참고 문서에 없는 내용은 일반론으로 작성하되, 추측성 수치/이름은 사용 금지"""


def generate_outline(slide: dict, requirements: list[dict], strategy: str,
                     ref_text: str = "", overview: str = "") -> list[dict]:
    """소제목 + scope 리스트 반환: [{"title": "...", "scope": "..."}]"""
    req_context = _build_req_context(requirements, slide.get("linked_reqs", []))
    ref_block = f"\n\n[참고 문서]\n{ref_text[:60000]}" if ref_text else ""
    overview_block = f"[사업 개요]\n{overview}\n\n" if overview else ""
    result = chat(
        [
            {"role": "system", "content": OUTLINE_SYSTEM},
            {"role": "user", "content": f"{overview_block}[전략 방향]\n{strategy}\n\n[장표] {slide['title']}\n\n[요구사항]\n{req_context}{ref_block}"},
        ],
        model="gpt-4o-mini",
    )
    try:
        if "```" in result:
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        sections = json.loads(result.strip()).get("sections", [])
        # 문자열 리스트로 온 경우 dict로 정규화
        return [
            {"title": s, "scope": ""} if isinstance(s, str)
            else {"title": s.get("title", ""), "scope": s.get("scope", "")}
            for s in sections if (isinstance(s, str) and s) or (isinstance(s, dict) and s.get("title"))
        ]
    except Exception:
        return []


def _build_section_messages(slide: dict, section_title: str, section_scope: str,
                             requirements: list[dict], strategy: str,
                             ref_text: str = "", overview: str = ""):
    req_context = _build_req_context(requirements, slide.get("linked_reqs", []))
    ref_block = f"\n\n[참고 문서]\n{ref_text[:60000]}" if ref_text else ""
    scope_block = f"\n\n[작성 범위(scope)]\n{section_scope}" if section_scope else ""
    overview_block = f"[사업 개요]\n{overview}\n\n" if overview else ""
    return [
        {"role": "system", "content": SECTION_SYSTEM},
        {"role": "user", "content": (
            f"{overview_block}"
            f"[전략 방향]\n{strategy}\n\n"
            f"[장표] {slide['title']}\n\n"
            f"[작성할 소제목] {section_title}"
            f"{scope_block}\n\n"
            f"[요구사항]\n{req_context}"
            f"{ref_block}"
        )},
    ]


def generate_section_stream(slide: dict, section_title: str, requirements: list[dict],
                             strategy: str, section_scope: str = "",
                             ref_text: str = "", overview: str = ""):
    """단일 소제목 본문 스트리밍 생성. (개별 작성/재작성용)"""
    messages = _build_section_messages(slide, section_title, section_scope, requirements, strategy, ref_text, overview)
    yield from chat_stream(messages, model="gpt-5.4", max_tokens=2048)


def generate_section(slide: dict, section_title: str, section_scope: str, requirements: list[dict],
                      strategy: str, ref_text: str = "", overview: str = "") -> str:
    """단일 소제목 본문 일괄 생성 (병렬 호출용, 스트리밍 X)."""
    from .llm import client
    messages = _build_section_messages(slide, section_title, section_scope, requirements, strategy, ref_text, overview)
    resp = client.chat.completions.create(
        model="gpt-5.4",
        messages=messages,
        temperature=0.7,
        max_completion_tokens=2048,
        timeout=180,
    )
    return resp.choices[0].message.content or ""


def review_draft(slide: dict, requirements: list[dict]) -> dict:
    req_context = _build_req_context(requirements, slide.get("linked_reqs", []))
    result = chat(
        [
            {"role": "system", "content": REVIEW_SYSTEM},
            {"role": "user", "content": f"[요구사항]\n{req_context}\n\n[초안]\n{slide['draft']}"}
        ],
        model="gpt-4o-mini"
    )
    try:
        if "```" in result:
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        return json.loads(result.strip())
    except Exception:
        return {"items": [], "overall": "검토 실패"}
