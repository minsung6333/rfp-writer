# -*- coding: utf-8 -*-
import json
import os
from .llm import client

CLASSIFY_SYSTEM = """당신은 IT 제안서 작성 전문가입니다.
장표 제목과 연결된 요구사항을 보고 아래 기준으로 분류하세요.

전략(strategic): 기술 선택지가 있거나, 회사 차별화가 필요하거나, 창의적 접근이 필요한 장표
표준(standard): 요구사항이 명확하고 업계 표준 대응 방식이 있는 장표

{"type": "strategic" 또는 "standard", "reason": "한 줄 이유"}
JSON만 반환하세요."""

QUESTION_SYSTEM = """당신은 IT 제안서 작성 전문가입니다.
이 장표를 잘 쓰기 위해 작성자에게 꼭 확인해야 할 핵심 질문 2~3개를 만드세요.
열린 질문이 아닌, 구체적인 기술/방향 선택에 관한 질문으로 만드세요.

{"questions": ["질문1", "질문2", "질문3"]}
JSON만 반환하세요."""

BULK_LINK_SYSTEM = """당신은 IT 제안서 작성 전문가입니다.
장표 목록과 요구사항 목록을 보고, 각 장표에 해당하는 요구사항 ID를 매핑하세요.

반환 형식:
{"mapping": {"장표제목1": ["REQ-001", "REQ-002"], "장표제목2": ["REQ-003"]}}

규칙:
- 관련 없으면 빈 배열
- 장표 제목을 key로 그대로 사용
- JSON만 반환"""


def classify_slide(title: str, req_details: str) -> dict:
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM},
                {"role": "user", "content": f"장표: {title}\n\n연결 요구사항:\n{req_details}"}
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"type": "standard", "reason": "분류 실패"}


def generate_questions(title: str, req_details: str, strategy: str) -> list[str]:
    try:
        resp = client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {"role": "system", "content": QUESTION_SYSTEM},
                {"role": "user", "content": f"[전략 방향]\n{strategy}\n\n[장표] {title}\n\n[요구사항]\n{req_details}"}
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return data.get("questions", [])
    except Exception:
        return []


def bulk_link_reqs(titles: list[str], requirements: list[dict]) -> dict[str, list[str]]:
    """모든 장표-요구사항 매핑을 한 번의 API 호출로 처리."""
    if not requirements:
        return {t: [] for t in titles}
    req_summary = "\n".join([f"{r['id']}: {r['name']}" for r in requirements])
    slides_text = "\n".join([f"- {t}" for t in titles])
    try:
        resp = client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {"role": "system", "content": BULK_LINK_SYSTEM},
                {"role": "user", "content": f"[장표 목록]\n{slides_text}\n\n[요구사항 목록]\n{req_summary}"}
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return data.get("mapping", {})
    except Exception:
        return {t: [] for t in titles}


def build_slides_from_toc(toc: list[dict], requirements: list[dict]) -> list[dict]:
    titles = [item.get("title", "") for item in toc]
    mapping = bulk_link_reqs(titles, requirements)

    slides = []
    for i, item in enumerate(toc):
        title = item.get("title", "")
        linked_ids = mapping.get(title, [])
        slides.append({
            "id": f"slide_{i+1:03d}",
            "chapter": item.get("chapter", ""),
            "section": item.get("section", ""),
            "title": title,
            "type": None,
            "linked_reqs": linked_ids,
            "questions": [],
            "draft": "",
            "status": "미작성",
            "chat_history": [],
        })
    return slides


def get_uncovered_reqs(requirements: list[dict], slides: list[dict]) -> list[str]:
    covered = set()
    for slide in slides:
        for rid in slide.get("linked_reqs", []):
            covered.add(rid)
    return [r["id"] for r in requirements if r["id"] not in covered]
