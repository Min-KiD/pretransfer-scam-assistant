"""The only place that talks to a model provider. The submission swaps this file to Bedrock; nothing else imports
the Gemini SDK.

    generate(prompt, image=None, schema=None, system=None, model=None) -> Result
Result.output is the parsed dict when a JSON schema is given, else None; Result.text is the raw text. Token counts,
seconds and USD (list prices in PRICES) come with every result, and every call is added to USAGE so callers can
enforce a budget.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from dataclasses import dataclass, field

from e1.score import PRICES  # USD per 1M tokens (input, output incl. thinking), read 2026-11-20
from e1.vlm import load_key

from .scenarios import ROOT

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite")
MIME = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp"}


@dataclass
class Result:
    output: dict | None
    text: str
    tokens_in: int
    tokens_out: int  # includes thinking tokens
    seconds: float
    usd: float
    model: str


@dataclass
class Usage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, r: Result):
        with self.lock:
            self.calls += 1
            self.tokens_in += r.tokens_in
            self.tokens_out += r.tokens_out
            self.usd += r.usd


USAGE = Usage()


class LLMError(RuntimeError):
    pass


_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=load_key(ROOT))
    return _client


def mime_of(image: bytes) -> str:
    return next((m for sig, m in MIME.items() if image.startswith(sig)), "image/jpeg")


def generate(prompt: str, image: bytes | None = None, schema: dict | None = None, system: str | None = None,
             model: str | None = None, retries: int = 5) -> Result:
    from google.genai import types
    model = model or DEFAULT_MODEL
    # Default temperature/thinking on purpose (same as E1): Gemini 3+ docs advise against lowering temperature.
    cfg = types.GenerateContentConfig(system_instruction=system,
                                      **({"response_mime_type": "application/json", "response_json_schema": schema}
                                         if schema else {}))
    contents = ([types.Part.from_bytes(data=image, mime_type=mime_of(image))] if image else []) + [prompt]
    client = _get_client()  # a missing key fails here, not inside the retry loop
    last = ""
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=cfg)
            dt = time.perf_counter() - t0
            u = resp.usage_metadata
            tin = u.prompt_token_count or 0
            tout = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
            text = resp.text or ""
            pin, pout = PRICES.get(model, (0.0, 0.0))
            r = Result(None, text, tin, tout, round(dt, 3), (tin * pin + tout * pout) / 1e6, model)
            USAGE.add(r)  # billed even if the JSON below turns out malformed
            if schema:
                r.output = json.loads(text)
            return r
        except Exception as e:  # rate limits, 5xx, the odd malformed JSON
            last = f"{type(e).__name__}: {str(e)[:200]}"
            if attempt < retries:
                time.sleep(min(30, 2 ** attempt * 2) + random.random())
    raise LLMError(last)
