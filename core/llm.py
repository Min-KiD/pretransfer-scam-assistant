"""The only place that talks to a model provider. The submission swaps this file to Bedrock; nothing else imports
a provider SDK.

    generate(prompt, image=None, schema=None, system=None, model=None) -> Result
Result.output is the parsed dict when a JSON schema is given, else None; Result.text is the raw text. Token counts,
seconds and USD (list prices in PRICES) come with every result, and every call is added to USAGE so callers can
enforce a budget. Result.retries counts failed attempts before the one returned (errors and malformed JSON).

Model names (default from $LLM_MODEL):
- "gemini-..." goes to the Google SDK; a suffix "@low" / "@medium" ... sets the thinking level (e.g. "gemini-3.8-flash@low").
- "anthropic:<model>" goes to Anthropic's native Messages API, the schema as `output_config.format` (constrained
  decoding; their OpenAI-compatible layer ignores response_format). Thinking stays at the model's default.
- "<provider>:<model>" otherwise goes to an OpenAI-style /chat/completions endpoint (PROVIDERS): "local:<name>" is a
  vLLM server on the GPU box at $LOCAL_LLM_URL; "openai:" needs a key in the environment or .env. Providers in
  JSON_SCHEMA get the schema as constrained decoding; the rest get it as text in the prompt, and a reply that does not
  parse is asked again (counted in retries). $LOCAL_LLM_SCHEMA=0 turns constrained decoding off for the local server.
"""
from __future__ import annotations

import base64
import json
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field

from e1.score import PRICES  # USD per 1M tokens (input, output incl. thinking), read 2026-11-20
from e1.vlm import load_key

from .scenarios import ROOT

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite")
MIME = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp"}
# provider -> (base URL or the env var holding it, env vars that may hold the key; empty = no key)
PROVIDERS = {
    "local": ("LOCAL_LLM_URL", ()),
    "openai": ("https://api.openai.com/v1", ("OPENAI_API_KEY",)),
    # base URL of the native Messages API (POST /messages), see _generate_anthropic
    "anthropic": ("https://api.anthropic.com/v1", ("CLAUDE_API_KEY", "ANTHROPIC_API_KEY")),
}
JSON_SCHEMA = {"local", "openai", "anthropic"}
ANTHROPIC_VERSION = "2026-10-21"  # the version header in Anthropic's structured-outputs docs, read 2026-11-23
# USD per 1M tokens (input, output), official price pages: the mid-tier model of each vendor (read 2026-11-22);
# claude-haiku-5-5 for prompts up to 100,000 tokens (read 2026-11-23; longer prompts cost more, ours are far shorter)
PRICES = {**PRICES, "gpt-6.2-sol": (2.00, 10.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50)}
NO_CREDIT = ("insufficient_quota", "credit balance", "billing")  # out of money: fail at once, never retry
SCHEMA_IN_PROMPT = "\n\nTrả về đúng một đối tượng JSON hợp lệ theo JSON Schema dưới đây, không thêm chữ nào khác:\n"


@dataclass
class Result:
    output: dict | None
    text: str
    tokens_in: int
    tokens_out: int  # includes thinking tokens
    seconds: float
    usd: float
    model: str
    retries: int = 0  # failed attempts before this one (API errors, malformed JSON)
    tokens_thought: int = 0  # the thinking part of tokens_out, where the provider reports it (Gemini)


@dataclass
class Usage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    usd_by_model: dict = field(default_factory=dict)  # model name as called -> USD
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, r: Result):
        with self.lock:
            self.calls += 1
            self.tokens_in += r.tokens_in
            self.tokens_out += r.tokens_out
            self.usd += r.usd
            self.usd_by_model[r.model] = self.usd_by_model.get(r.model, 0.0) + r.usd


USAGE = Usage()


class LLMError(RuntimeError):
    pass


_client = None
_http = None


def env_value(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip("\"'") or None
    return None


def has_key(model: str) -> bool:
    """False for a provider whose key is missing (the run is skipped and reported as "chưa có key")."""
    prov = model.split(":", 1)[0] if ":" in model else "gemini"
    if prov == "gemini":
        return bool(env_value("GEMINI_API_KEY"))
    return not PROVIDERS[prov][1] or any(env_value(v) for v in PROVIDERS[prov][1])


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=load_key(ROOT))
    return _client


def mime_of(image: bytes) -> str:
    return next((m for sig, m in MIME.items() if image.startswith(sig)), "image/jpeg")


def parse_json(text: str, schema: dict) -> dict:
    """The JSON object in a free-text reply (code fences and chatter around it are dropped). Raises ValueError."""
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < i:
        raise ValueError("no JSON object")
    obj = json.loads(t[i:j + 1])
    missing = [k for k in schema.get("required", []) if k not in obj]
    if missing:
        raise ValueError(f"missing keys {missing}")
    return obj


def generate(prompt: str, image: bytes | None = None, schema: dict | None = None, system: str | None = None,
             model: str | None = None, retries: int = 5, max_tokens: int | None = None) -> Result:
    model = model or DEFAULT_MODEL
    if model.startswith("anthropic:"):
        return _generate_anthropic(prompt, image, schema, system, model, retries, max_tokens)
    if ":" in model:
        return _generate_openai(prompt, image, schema, system, model, retries, max_tokens)
    from google.genai import types
    name, _, level = model.partition("@")
    # Default temperature/thinking on purpose (same as E1): Gemini 3+ docs advise against lowering temperature.
    # A thinking level is only set when the model name asks for one.
    cfg = types.GenerateContentConfig(system_instruction=system,
                                      **({"thinking_config": types.ThinkingConfig(thinking_level=level)} if level else {}),
                                      **({"response_mime_type": "application/json", "response_json_schema": schema}
                                         if schema else {}))
    contents = ([types.Part.from_bytes(data=image, mime_type=mime_of(image))] if image else []) + [prompt]
    client = _get_client()  # a missing key fails here, not inside the retry loop
    last = ""
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(model=name, contents=contents, config=cfg)
            dt = time.perf_counter() - t0
            u = resp.usage_metadata
            tin = u.prompt_token_count or 0
            thought = u.thoughts_token_count or 0
            tout = (u.candidates_token_count or 0) + thought
            text = resp.text or ""
            pin, pout = PRICES.get(name, (0.0, 0.0))
            r = Result(None, text, tin, tout, round(dt, 3), (tin * pin + tout * pout) / 1e6, model, attempt, thought)
            USAGE.add(r)  # billed even if the JSON below turns out malformed
            if schema:
                r.output = json.loads(text)
            return r
        except Exception as e:  # rate limits, 5xx, the odd malformed JSON
            last = f"{type(e).__name__}: {str(e)[:200]}"
            if attempt < retries:
                time.sleep(min(30, 2 ** attempt * 2) + random.random())
    raise LLMError(last)


def _generate_openai(prompt, image, schema, system, model, retries, max_tokens) -> Result:
    import httpx
    global _http
    prov, name = model.split(":", 1)
    base, key_vars = PROVIDERS[prov]
    base = (env_value(base) or "http://127.0.0.1:8000/v1") if prov == "local" else base
    key = next((env_value(v) for v in key_vars if env_value(v)), None) if key_vars else "none"
    if not key:
        raise LLMError(f"{' / '.join(key_vars)} missing from environment and .env")
    native = schema is not None and prov in JSON_SCHEMA and not (prov == "local" and
                                                                 os.environ.get("LOCAL_LLM_SCHEMA") == "0")
    text_prompt = prompt + (SCHEMA_IN_PROMPT + json.dumps(schema, ensure_ascii=False) if schema and not native else "")
    content = ([{"type": "image_url", "image_url": {"url": f"data:{mime_of(image)};base64,"
                                                           f"{base64.b64encode(image).decode()}"}}] if image else [])
    content.append({"type": "text", "text": text_prompt})
    body = {"model": name, "messages": ([{"role": "system", "content": system}] if system else [])
                                       + [{"role": "user", "content": content}]}
    if native:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}
    if max_tokens:
        body["max_completion_tokens" if prov == "openai" else "max_tokens"] = max_tokens
    if prov == "local":
        # Greedy decoding, thinking off (Qwen3.5 and Gemma 4 chat templates read enable_thinking). A retry after a
        # malformed reply samples (temperature 0.7): greedy would only repeat the same reply.
        body["chat_template_kwargs"] = {"enable_thinking": False}
    if _http is None:
        _http = httpx.Client(timeout=600)
    last = ""
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        if prov == "local":
            body["temperature"] = 0 if attempt == 0 else 0.7
        try:
            resp = _http.post(base.rstrip("/") + "/chat/completions", json=body,
                              headers={"Authorization": f"Bearer {key}", "x-api-key": key})
            if 400 <= resp.status_code < 500 and any(s in resp.text.lower() for s in NO_CREDIT):
                raise LLMError(f"no credit: HTTP {resp.status_code} {resp.text[:200]}")
            resp.raise_for_status()
            d = resp.json()
            dt = time.perf_counter() - t0
            u = d.get("usage") or {}
            tin, tout = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
            text = d["choices"][0]["message"].get("content") or ""
            pin, pout = PRICES.get(name, (0.0, 0.0))
            r = Result(None, text, tin, tout, round(dt, 3), (tin * pin + tout * pout) / 1e6, model, attempt)
            USAGE.add(r)
            if schema:
                r.output = json.loads(text) if native else parse_json(text, schema)
            return r
        except LLMError:
            raise
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
            if attempt < retries:
                time.sleep(min(30, 2 ** attempt) + random.random())
    raise LLMError(last)


def anthropic_schema(schema: dict) -> dict:
    """Our JSON schemas in the subset Anthropic's constrained decoding accepts: every object closed with
    additionalProperties false; numeric/string-length constraints and minItems above 1 dropped (400 otherwise)."""
    if isinstance(schema, list):
        return [anthropic_schema(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: anthropic_schema(v) for k, v in schema.items()
           if k not in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength",
                        "maxLength", "maxItems")}
    if out.get("minItems", 0) > 1:
        out["minItems"] = 1
    t = out.get("type")
    if t == "object" or (isinstance(t, list) and "object" in t) or "properties" in out:
        out["additionalProperties"] = False
    return out


def _generate_anthropic(prompt, image, schema, system, model, retries, max_tokens) -> Result:
    import httpx
    global _http
    name = model.split(":", 1)[1]
    base, key_vars = PROVIDERS["anthropic"]
    key = next((env_value(v) for v in key_vars if env_value(v)), None)
    if not key:
        raise LLMError(f"{' / '.join(key_vars)} missing from environment and .env")
    content = ([{"type": "image", "source": {"type": "base64", "media_type": mime_of(image),
                                             "data": base64.b64encode(image).decode()}}] if image else [])
    content.append({"type": "text", "text": prompt})
    # No temperature (the model page says to omit it); adaptive thinking at the model's default effort.
    body = {"model": name, "max_tokens": max_tokens or 8192, "messages": [{"role": "user", "content": content}]}
    if system:
        body["system"] = system
    if schema is not None:
        body["output_config"] = {"format": {"type": "json_schema", "schema": anthropic_schema(schema)}}
    if _http is None:
        _http = httpx.Client(timeout=600)
    last = ""
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        try:
            resp = _http.post(base.rstrip("/") + "/messages", json=body,
                              headers={"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION})
            # A wrong key, a key without a workspace, no credit or a rejected schema will not fix itself: fail at once.
            if 400 <= resp.status_code < 500 and resp.status_code not in (408, 409, 429):
                raise LLMError(f"HTTP {resp.status_code} {resp.text[:300]}")
            resp.raise_for_status()
            d = resp.json()
            dt = time.perf_counter() - t0
            u = d.get("usage") or {}
            tin = (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                   + u.get("cache_read_input_tokens", 0))
            tout = u.get("output_tokens", 0)  # includes thinking
            text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
            pin, pout = PRICES.get(name, (0.0, 0.0))
            r = Result(None, text, tin, tout, round(dt, 3), (tin * pin + tout * pout) / 1e6, model, attempt)
            USAGE.add(r)  # billed even if the reply below is unusable
            if d.get("stop_reason") in ("refusal", "max_tokens"):
                raise ValueError(f"stop_reason {d['stop_reason']}")
            if schema:
                r.output = json.loads(text)
            return r
        except LLMError:
            raise
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
            if attempt < retries:
                time.sleep(min(30, 2 ** attempt) + random.random())
    raise LLMError(last)
