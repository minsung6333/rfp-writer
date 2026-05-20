# -*- coding: utf-8 -*-
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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
