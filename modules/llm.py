# -*- coding: utf-8 -*-
import os
from openai import OpenAI

def _get_api_key():
    """API 키 우선순위: 환경변수 → st.secrets → .env"""
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    return None

client = OpenAI(api_key=_get_api_key())


def chat_stream(messages: list[dict], model: str = "gpt-4o", max_tokens: int = 4096):
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        temperature=0.7,
        max_completion_tokens=max_tokens,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def chat(messages: list[dict], model: str = "gpt-4o-mini") -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
    )
    return resp.choices[0].message.content
