# -*- coding: utf-8 -*-
"""기능 아이디어 도출 채팅 — Agentic RAG (web_search + 문서 요청)"""
import json
from .llm import client


NEED_DOC_TAG = "[NEED_DOC]"


INITIAL_SYSTEM = """당신은 IT 공공 제안서 자문 전문가입니다.
주어진 사업 정보·요구사항·주제를 분석하여 아이디어 토론의 출발점을 제시합니다.

답변 구성:
1. 주제와 요구사항을 1~2줄로 짧게 짚고
2. **3~5개의 직관적 접근 방향**을 제시 (각 방향은 한 줄 요약 + 핵심 차별점)
3. 마지막에 "어느 쪽부터 깊이 가볼까요?" 같은 open question으로 사용자 응답 유도

원칙:
- 일반론 X. 본 사업의 도메인·요구사항 특성에 맞춰 구체적으로
- 평가위원이 주목할 차별점 강조
- 500~800자 분량"""


CHAT_SYSTEM = """당신은 IT 공공 제안서 자문 전문가입니다.
사용자와 자유롭게 대화하며 사업의 핵심 기능·전략·구현 방안 아이디어를 함께 발전시킵니다.

매 응답마다 다음 중 가장 적절한 행동을 자율적으로 선택:

1. **그냥 답변** — 기존 컨텍스트로 충분할 때
2. **🔍 웹 검색** — 최신 시장/경쟁사/유사 사업/외부 사례 정보가 필요할 때
   (web_search 도구를 호출하세요)
3. **📎 사용자 문서 요청** — 회사 보유 자료(이전 제안서·실적·인증·기술백서 등)가
   필요할 때 답변 끝에 다음 마커 포함:
   [NEED_DOC] 어떤 문서가 왜 필요한지 한 줄

원칙:
- 일반 지식은 검색하지 말고 그냥 답할 것 (자원 낭비)
- 최신 시장·사례·통계·법규 변화는 반드시 검색 후 답
- 답변은 구체적 수치·방법론 중심
- 답변 길이 적정선 유지 (500~1500자)
- 사용자의 직전 질문에 직접적으로 답할 것"""


COMPACT_SYSTEM = """이전 채팅 메시지들을 압축 요약하세요. 이후 대화에서 이 요약이 컨텍스트로 사용됩니다.

다음 형식으로 마크다운 작성:

### 지금까지의 핵심 논의
- (bullet, 6~10개)

### 사용자가 표명한 방향성·선호
- (있으면)

### 검색으로 알아낸 주요 사실
- (사실 + 출처 URL/도메인 보존)

### 첨부 문서 핵심 내용
- (문서명 + 핵심 정보)

### 진행 중인 논점·미해결 질문
- (다음 답변에 필요한 맥락)

원칙:
- 사실/숫자/고유명사/URL/문서명 누락 절대 금지
- 모호한 표현은 정리·압축
- 마크다운 본문만 출력 (서론·머리말·맺음말 X)"""


def compact_history(messages: list[dict]) -> str:
    """오래된 메시지들을 요약 텍스트로."""
    if not messages:
        return ""
    text_parts = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            content = "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
        prefix = "사용자" if role == "user" else "전문가"
        text_parts.append(f"### {prefix}\n{content}")
    full = "\n\n".join(text_parts)
    try:
        resp = client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {"role": "system", "content": COMPACT_SYSTEM},
                {"role": "user", "content": full},
            ],
            timeout=180,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"(요약 실패: {e})"


def maybe_compact_for_api(messages: list[dict], threshold: int = 12, keep_recent: int = 4,
                          cached_summary: str = "", cached_until_idx: int = 0) -> tuple[list[dict], str, int]:
    """API 전송용 압축. 표시용 messages는 그대로 두고, API에 보낼 list만 압축.

    Returns:
        (api_messages, summary_for_system, new_cached_until_idx)
    """
    if len(messages) <= threshold:
        return messages, cached_summary, cached_until_idx

    # 첫 메시지(AI 초기 분석) 유지
    first = messages[0:1]
    recent = messages[-keep_recent:]
    middle_start = 1
    middle_end = len(messages) - keep_recent
    middle = messages[middle_start:middle_end]

    if not middle:
        return messages, cached_summary, cached_until_idx

    # 캐시된 요약이 있고 그 범위까지만 요약했다면, 그 이후 메시지만 새로 요약
    if cached_summary and cached_until_idx > 0 and cached_until_idx <= middle_end:
        new_middle = messages[cached_until_idx:middle_end]
        if new_middle:
            new_part_summary = compact_history(new_middle)
            combined = cached_summary + "\n\n---\n[추가 요약]\n" + new_part_summary
        else:
            combined = cached_summary
    else:
        combined = compact_history(middle)

    return first + recent, combined, middle_end


SUMMARIZE_SYSTEM = """당신은 IT 제안서 작성 전문가입니다.
사용자와 전문가의 아이디어 도출 채팅 전체를 검토하여 **구조화된 아이디어 정리본**을 작성합니다.

이 정리본은 이후 제안서 전략 수립 단계에서 컨텍스트로 사용됩니다.

다음 형식으로 마크다운 작성:

## 주제: {주제명}

### 핵심 아이디어
(번호 매긴 bullet, 각 아이디어는 1~2줄 + 핵심 차별점)

### 차별화 포인트
- 평가위원이 주목할 만한 포인트들

### 구현 방안 / 기술 스택
(채팅에서 나온 구체 방법론·기술·아키텍처)

### 외부 참고 (검색 결과)
- 인용 출처 (URL 포함)

### 회사 자료 활용 (첨부)
- 첨부된 문서명과 그 안에서 활용할 핵심 내용

### 잠재 리스크 & 대응
- 채팅에서 언급된 리스크와 대응 방안

### 평가위원 호소 포인트
- 이 아이디어를 제안서에 반영했을 때 어필 가능한 부분

원칙:
- 채팅에 없는 내용은 추가하지 말 것
- 모호한 부분은 그대로 두지 말고 정리·압축
- 마크다운 본문만 출력 (서론·머리말·맺음말 X)"""


def generate_initial_message(topic: str, linked_reqs: list[dict], overview: str = "") -> str:
    """주제 만들면 AI가 먼저 던지는 메시지 생성."""
    req_text = "\n".join([
        f"- [{r.get('id','')}] {r.get('name','')}: {r.get('detail','')[:300]}"
        for r in linked_reqs
    ]) if linked_reqs else "(연결 요구사항 없음)"

    overview_block = f"[사업 개요]\n{overview}\n\n" if overview else ""
    user_msg = (
        f"{overview_block}"
        f"[아이디어 도출 주제] {topic}\n\n"
        f"[연결 요구사항]\n{req_text}\n\n"
        f"위 정보를 분석해서 아이디어 도출의 출발점을 제시해주세요."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {"role": "system", "content": INITIAL_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            timeout=120,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"(초기 메시지 생성 실패: {e})"


def agentic_chat_stream(
    messages: list[dict],
    topic: str,
    linked_reqs: list[dict],
    overview: str = "",
    attached_docs: str = "",
    use_web_search: bool = True,
    cached_summary: str = "",
    cached_until_idx: int = 0,
):
    """Agentic 채팅 streaming. 이벤트를 yield.

    Event types:
      ('stage', label)         - 진행 단계 변경
      ('search', query)        - 웹 검색 수행 (쿼리)
      ('text_delta', text)     - 답변 텍스트 증분
      ('compact', (summary, until_idx))  - 자동 압축 수행 (캐시 갱신용)
      ('done', result_dict)    - 최종 결과
    """
    req_text = "\n".join([
        f"- [{r.get('id','')}] {r.get('name','')}: {r.get('detail','')[:200]}"
        for r in linked_reqs
    ]) if linked_reqs else "(없음)"

    # 자동 압축: 메시지 많아지면 오래된 부분 요약
    did_compact_now = False
    new_summary = cached_summary
    new_until_idx = cached_until_idx
    if len(messages) > 12:
        yield ("stage", "🗜️ 이전 대화 자동 요약 중...")
        api_messages, new_summary, new_until_idx = maybe_compact_for_api(
            messages, threshold=12, keep_recent=4,
            cached_summary=cached_summary, cached_until_idx=cached_until_idx,
        )
        if new_summary != cached_summary or new_until_idx != cached_until_idx:
            did_compact_now = True
            yield ("compact", (new_summary, new_until_idx))
    else:
        api_messages = messages

    summary_block = (
        f"[이전 대화 자동 요약 — 오래된 메시지 압축됨]\n{new_summary}\n\n"
        if new_summary else ""
    )

    context_block = (
        (f"[사업 개요]\n{overview}\n\n" if overview else "") +
        f"[주제] {topic}\n\n" +
        f"[연결 요구사항]\n{req_text}\n\n" +
        (f"[첨부된 사용자 문서]\n{attached_docs[:30000]}\n\n" if attached_docs else "") +
        summary_block
    )

    clean_messages = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in api_messages if m.get("content")
    ]
    input_messages = [
        {"role": "system", "content": CHAT_SYSTEM + "\n\n--- 컨텍스트 ---\n" + context_block},
    ] + clean_messages

    try:
        yield ("stage", "🧠 의사결정 중...")

        kwargs = {
            "model": "gpt-5.5",
            "input": input_messages,
            "stream": True,
        }
        if use_web_search:
            kwargs["tools"] = [{"type": "web_search"}]
            kwargs["tool_choice"] = "auto"

        stream = client.responses.create(**kwargs)

        text_parts = []
        search_calls = []
        citations = []
        last_stage = "🧠 의사결정 중..."

        for event in stream:
            ev_type = getattr(event, "type", "") or ""

            if "web_search_call" in ev_type:
                if "in_progress" in ev_type or "searching" in ev_type:
                    if last_stage != "🔍 웹 검색 중...":
                        last_stage = "🔍 웹 검색 중..."
                        yield ("stage", last_stage)
                elif "completed" in ev_type:
                    item = getattr(event, "item", None)
                    query = ""
                    if item is not None:
                        action = getattr(item, "action", None)
                        if action is not None:
                            query = getattr(action, "query", "") or ""
                    search_calls.append({"query": query})
                    yield ("search", query)
                    last_stage = "🧠 검색 결과 분석 중..."
                    yield ("stage", last_stage)

            elif ev_type == "response.output_text.delta":
                delta = getattr(event, "delta", "") or ""
                if delta:
                    if last_stage != "✏️ 답변 생성 중...":
                        last_stage = "✏️ 답변 생성 중..."
                        yield ("stage", last_stage)
                    text_parts.append(delta)
                    yield ("text_delta", delta)

            elif ev_type == "response.completed":
                # 최종 응답에서 citations 추출
                response_obj = getattr(event, "response", None)
                if response_obj is not None:
                    output = getattr(response_obj, "output", []) or []
                    for item in output:
                        if getattr(item, "type", None) == "message":
                            content = getattr(item, "content", []) or []
                            for c in content:
                                annotations = getattr(c, "annotations", []) or []
                                for ann in annotations:
                                    if getattr(ann, "type", None) == "url_citation":
                                        citations.append({
                                            "url": getattr(ann, "url", "") or "",
                                            "title": getattr(ann, "title", "") or "",
                                        })

        full_text = "".join(text_parts).strip()

        # [NEED_DOC] 마커 추출
        need_doc = ""
        if NEED_DOC_TAG in full_text:
            idx = full_text.index(NEED_DOC_TAG)
            need_doc = full_text[idx + len(NEED_DOC_TAG):].strip().split("\n")[0]
            full_text = full_text[:idx].strip()

        yield ("done", {
            "text": full_text,
            "search_calls": search_calls,
            "citations": citations,
            "need_doc": need_doc,
        })
    except Exception as e:
        yield ("done", {
            "text": f"(응답 생성 실패: {e})",
            "search_calls": [],
            "citations": [],
            "need_doc": "",
        })


def agentic_chat(
    messages: list[dict],
    topic: str,
    linked_reqs: list[dict],
    overview: str = "",
    attached_docs: str = "",
    use_web_search: bool = True,
) -> dict:
    """한 턴의 agentic 채팅. Responses API + web_search tool.

    Returns:
        {
            "text": 답변 본문,
            "search_calls": [{"query": "..."}, ...],
            "citations": [{"url": "...", "title": "..."}, ...],
            "need_doc": "어떤 문서 필요하면 설명, 아니면 ''",
        }
    """
    req_text = "\n".join([
        f"- [{r.get('id','')}] {r.get('name','')}: {r.get('detail','')[:200]}"
        for r in linked_reqs
    ]) if linked_reqs else "(없음)"

    context_block = (
        (f"[사업 개요]\n{overview}\n\n" if overview else "") +
        f"[주제] {topic}\n\n" +
        f"[연결 요구사항]\n{req_text}\n\n" +
        (f"[첨부된 사용자 문서]\n{attached_docs[:30000]}\n\n" if attached_docs else "")
    )

    # 메시지 history → API 표준 형식으로 정제 (커스텀 필드 제거)
    clean_messages = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in messages if m.get("content")
    ]
    input_messages = [
        {"role": "system", "content": CHAT_SYSTEM + "\n\n--- 컨텍스트 ---\n" + context_block},
    ] + clean_messages

    try:
        kwargs = {
            "model": "gpt-5.5",
            "input": input_messages,
        }
        if use_web_search:
            kwargs["tools"] = [{"type": "web_search"}]
            kwargs["tool_choice"] = "auto"

        response = client.responses.create(**kwargs)

        # 응답 파싱
        text_parts = []
        search_calls = []
        citations = []

        for item in response.output:
            item_type = getattr(item, "type", None)
            if item_type == "web_search_call":
                action = getattr(item, "action", None)
                query = ""
                if action:
                    query = getattr(action, "query", "") or ""
                search_calls.append({"query": query})
            elif item_type == "message":
                content = getattr(item, "content", [])
                for c in content:
                    c_type = getattr(c, "type", None)
                    if c_type in ("output_text", "text"):
                        text_parts.append(getattr(c, "text", "") or "")
                        annotations = getattr(c, "annotations", []) or []
                        for ann in annotations:
                            ann_type = getattr(ann, "type", None)
                            if ann_type == "url_citation":
                                citations.append({
                                    "url": getattr(ann, "url", "") or "",
                                    "title": getattr(ann, "title", "") or "",
                                })

        full_text = "".join(text_parts).strip()

        # [NEED_DOC] 마커 추출
        need_doc = ""
        if NEED_DOC_TAG in full_text:
            idx = full_text.index(NEED_DOC_TAG)
            need_doc = full_text[idx + len(NEED_DOC_TAG):].strip().split("\n")[0]
            full_text = full_text[:idx].strip()

        return {
            "text": full_text,
            "search_calls": search_calls,
            "citations": citations,
            "need_doc": need_doc,
        }
    except Exception as e:
        return {
            "text": f"(응답 생성 실패: {e})",
            "search_calls": [],
            "citations": [],
            "need_doc": "",
        }


def summarize_idea_chat(messages: list[dict], topic: str, overview: str = "") -> str:
    """채팅 전체를 구조화된 아이디어 정리로 압축."""
    if not messages:
        return ""

    # 채팅 history를 텍스트로
    history_lines = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            content = "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
        prefix = "사용자" if role == "user" else "전문가"
        history_lines.append(f"### {prefix}\n{content}")
    history_text = "\n\n".join(history_lines)

    overview_block = f"[사업 개요]\n{overview}\n\n" if overview else ""
    user_content = (
        f"{overview_block}"
        f"[주제] {topic}\n\n"
        f"[채팅 전체 내역]\n{history_text}"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {"role": "system", "content": SUMMARIZE_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            timeout=180,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"(정리 실패: {e})"
