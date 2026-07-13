"""Brain — talks to Google Gemini: tool-calling, streaming, vision, key/model
fallback, approval gate, and session summarization.

API reference: https://ai.google.dev/api/generate-content
"""
from __future__ import annotations

import base64
import io
import json
import threading
import time
from typing import Any, Callable, Iterator

import requests

from config import CONFIG, FALLBACK_MODELS, VISION_MODELS, GEMINI_BASE
from .memory import Memory


# Errors that mean "try the next key" (rate-limit / quota exhausted).
RETRYABLE_KEY_STATUS = {429, 500, 502, 503, 504}
# Permanent errors that mean "give up on this key but try the next model".
FATAL_KEY_STATUS = {400, 401, 403}


def _empty_reply_text(finish_reason: str | None) -> str:
    """Explain an empty Gemini reply instead of a vague '(no reply)' fallback."""
    reason = finish_reason or "unknown"
    if reason.startswith("BLOCKED:"):
        return f"⚠ Gemini blocked that prompt (reason: {reason.split(':', 1)[1]}). Try rephrasing."
    if reason == "MAX_TOKENS":
        return "⚠ Gemini ran out of its response budget before writing an answer. Try a shorter/simpler question, or try again."
    if reason in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT"):
        return f"⚠ Gemini declined to answer (reason: {reason}). Try rephrasing."
    return "⚠ Gemini returned an empty response. Try again."


class Brain:
    """Wraps a Gemini chat model + a registry of callable tools.

    Key + model fallback:
    1. Try primary key + primary model.
    2. If a rate-limit/quota error → swap to the backup key, reset to primary model.
    3. If an auth error → swap to backup key.
    4. If a model error (e.g. model not found, content blocked) → try next model
       in the fallback chain on the same key.
    """

    def __init__(
        self,
        memory: Memory,
        tools_schema: list[dict[str, Any]],
        dispatch: Callable[[str, dict[str, Any]], str],
        on_tool: Callable[[str, dict[str, Any]], None] | None = None,
        registry: Any = None,
    ) -> None:
        self.memory = memory
        self.tools_schema = tools_schema
        self.dispatch = dispatch
        self.on_tool = on_tool
        self.registry = registry
        self.session = requests.Session()
        # Thread safety for key rotation (used from web + Telegram threads)
        self._key_lock = threading.Lock()
        # Track which key index we're on (0 = primary, 1 = backup). Updated
        # dynamically if a key gets rate-limited.
        self._key_index = 0
        # Suppress a noisy log when we already warned about a key.
        self._key_warned: set[str] = set()

    # ── key / model selection ────────────────────────────────
    def _current_key(self) -> str:
        keys = CONFIG.all_keys()
        if not keys:
            return ""
        with self._key_lock:
            if self._key_index >= len(keys):
                self._key_index = 0
            return keys[self._key_index]

    def _mark_key_dead(self, status: int) -> None:
        """When a key hits a fatal or quota error, switch to the next one."""
        keys = CONFIG.all_keys()
        if len(keys) <= 1:
            return  # nothing to fall back to
        with self._key_lock:
            old = self._current_key()
            self._key_index = (self._key_index + 1) % len(keys)
        new = self._current_key()
        if old and old not in self._key_warned:
            self._key_warned.add(old)
            reason = "quota / rate limit" if status in RETRYABLE_KEY_STATUS else f"auth error {status}"
            print(
                f"[brain] primary Gemini key hit {reason}; "
                f"switched to backup key (key #{self._key_index + 1}/{len(keys)})."
            )

    def _models_to_try(self, primary: str | None = None) -> list[str]:
        first = primary or CONFIG.model
        chain = [first] + [m for m in FALLBACK_MODELS if m != first]
        return chain

    def _key_order(self, keys: list[str]) -> list[int]:
        """Indices of every key to try this request, starting at the last
        known-good key and wrapping around. Because it wraps, a key that was
        rate-limited earlier but has since recovered still gets retried — we
        never permanently abandon a key, which is what keeps 'limit reached'
        from showing while any key still has quota."""
        n = len(keys)
        if n == 0:
            return []
        with self._key_lock:
            start = self._key_index % n
            return [(start + off) % n for off in range(n)]

    @staticmethod
    def _is_quota_error(status: int, body: str = "") -> bool:
        """True when a non-200 is a rate/quota limit (429 / RESOURCE_EXHAUSTED)
        rather than an auth/model/network failure."""
        return status == 429 or "RESOURCE_EXHAUSTED" in (body or "")

    def _exhausted_text(self, saw_non_quota: bool, last_err: str,
                        n_keys: int) -> str:
        """Message shown when every key+model attempt failed. If the ONLY
        failures were rate limits, say so plainly ('limit reached'); otherwise
        surface the real error."""
        if not saw_non_quota:
            return (
                f"⏳ All {n_keys} Gemini key(s) are rate-limited right now — "
                "limit reached. Add more keys in Settings → Extra Gemini keys, "
                "or wait about a minute and try again."
            )
        return f"Gemini request failed. Last error — {last_err}"

    # ── schema translation (registry tool defs → Gemini function_declarations) ─
    def _to_gemini_tools(self) -> list[dict[str, Any]] | None:
        """Convert the registry tool schema into Gemini's format.

        Registry format (stored in self.tools_schema):
          {"type": "function", "function": {"name": ..., "description": ...,
                                            "parameters": {...JSON schema...}}}
        Gemini format:
          {"function_declarations": [
              {"name": ..., "description": ..., "parameters": {...JSON schema...}}
          ]}
        """
        decls = []
        for entry in self.tools_schema:
            fn = entry.get("function") if "function" in entry else entry
            if not fn:
                continue
            decls.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        if not decls:
            return None
        return [{"function_declarations": decls}]

    def _to_gemini_contents(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
        """Convert OpenAI-style messages into Gemini contents.

        Returns (contents, system_text). Gemini keeps the system prompt as a
        separate top-level field, not as a message.

        OpenAI roles: system, user, assistant, tool
        Gemini roles:  user, model (and 'function' parts in tool turns)
        """
        system_text: str | None = None
        contents: list[dict[str, Any]] = []

        for m in messages:
            role = m.get("role")
            if role == "system":
                # Stash it; we'll send as a top-level systemInstruction.
                text = m.get("content") or ""
                system_text = (system_text + "\n\n" + text) if system_text else text
                continue

            if role == "user":
                # `content` is usually a string, but vision passes the OpenAI
                # multimodal shape (a list of {type,text|image_url} parts). Flatten
                # any text parts to a string so Gemini gets a valid `{"text": ...}`
                # (a raw list here produces `{"text": [...]}`, which the API 400s).
                raw = m.get("content", "")
                if isinstance(raw, list):
                    text = " ".join(
                        p.get("text", "") for p in raw
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                else:
                    text = raw or ""
                contents.append({
                    "role": "user",
                    "parts": [{"text": text}],
                })

            elif role == "assistant":
                parts: list[dict[str, Any]] = []
                text = m.get("content")
                if text:
                    parts.append({"text": text})
                # NOTE: we intentionally do NOT replay the `functionCall` parts
                # back to Gemini. Gemini's API requires the `thought_signature`
                # that came with the original functionCall in order to accept
                # it on a subsequent turn; we don't preserve that signature, and
                # the API rejects the request with 400 "Function call is missing
                # a thought_signature". The `tool` (functionResponse) parts on
                # the next user turn are still enough for the model to see the
                # tool results and continue reasoning.
                if not parts:
                    # Skip empty assistant turns — Gemini rejects them.
                    continue
                contents.append({"role": "model", "parts": parts})

            elif role == "tool":
                # Tool results in Gemini come back as 'functionResponse' parts
                # on a 'user' turn (Gemini only accepts user/model alternation).
                content = m.get("content") or ""
                # Wrap the previous turn if needed so the function response is
                # attached to a 'user' message.
                if not contents or contents[-1].get("role") != "user":
                    contents.append({"role": "user", "parts": []})
                contents[-1]["parts"].append({
                    "functionResponse": {
                        "name": m.get("name", ""),
                        "response": {"result": _safe_truncate(content, 4000)},
                    }
                })

        return contents, (system_text or None)

    # ── HTTP helpers ────────────────────────────────────────
    def _post(self, payload: dict[str, Any], models: list[str] | None = None) -> dict[str, Any]:
        """Non-streaming POST with key + model fallback.

        Layered resilience:
          1. For each model in the chain…
          2.   For each configured Gemini key…
          3.     Try the request. On 200, return.
          4.     On 429/5xx (quota/rate) → mark key dead, try next key.
          5.     On 401/403 (auth) → mark key dead, try next key.
          6.     On 400 (bad request — e.g. content blocked, bad model) →
          7.        try next model on same key.
        """
        contents, system_text = self._to_gemini_contents(payload.get("messages", []))
        if not contents:
            # Gemini requires at least one content turn; if the caller passed
            # only a system prompt (e.g. summarize_session), wrap in a dummy
            # user message — but that would change semantics, so instead raise
            # a clearer error.
            raise RuntimeError("Gemini call has no user/model messages to send.")

        base_payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": payload.get("temperature", 0.6),
                # Thinking-capable models (gemini-3-flash-preview, 2.5-flash)
                # spend part of this budget on invisible reasoning tokens
                # before writing the visible answer. A 1024 cap let complex
                # prompts get truncated (finishReason=MAX_TOKENS) with zero
                # visible text — that's the "(no reply from model)" bug.
                "maxOutputTokens": max(payload.get("max_tokens") or 4096, 4096),
            },
        }
        if system_text:
            base_payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        if payload.get("tools"):
            gt = self._to_gemini_tools()
            if gt:
                base_payload["tools"] = gt

        last_err = ""
        saw_non_quota = False
        keys = CONFIG.all_keys()
        if not keys:
            raise RuntimeError("No Gemini API key configured (set JARVIS_GEMINI_KEY in .env).")
        order = self._key_order(keys)

        for model in (models or self._models_to_try(payload.get("model"))):
            for ki in order:
                key = keys[ki]
                url = f"{GEMINI_BASE}/{model}:generateContent"
                try:
                    resp = self.session.post(
                        url, params={"key": key},
                        json=base_payload, timeout=(5, 90),
                    )
                except requests.RequestException as exc:
                    last_err = f"{model}: network error {exc}"
                    saw_non_quota = True
                    continue
                if resp.status_code == 200:
                    self._key_index = ki  # remember the key that worked
                    return _gemini_to_openai_shape(resp.json(), model)
                body = resp.text[:140]
                if self._is_quota_error(resp.status_code, body):
                    # Pure rate limit — try the next key, keep it out of the
                    # user-facing message unless everything is exhausted.
                    last_err = f"{model} key#{ki+1}: {resp.status_code} {body}"
                    self._mark_key_dead(resp.status_code)
                    continue
                if resp.status_code in RETRYABLE_KEY_STATUS or resp.status_code in FATAL_KEY_STATUS:
                    last_err = f"{model} key#{ki+1}: {resp.status_code} {body}"
                    saw_non_quota = True
                    self._mark_key_dead(resp.status_code)
                    continue
                # 400 — usually a model-specific error (bad model name, content
                # blocked, etc.). Try the next model on the same key.
                last_err = f"{model} key#{ki+1}: {resp.status_code} {body}"
                saw_non_quota = True
                break  # break key loop; outer for-loop moves to next model

        raise RuntimeError(self._exhausted_text(saw_non_quota, last_err, len(keys)))

    def _post_stream(
        self, payload: dict[str, Any], models: list[str] | None = None,
    ) -> Iterator[dict]:
        """Streaming POST with key + model fallback. Yields raw SSE-style events:
          {'type': 'token', 'text': '...'}
          {'type': 'tool_call', 'name': '...', 'args': {...}, 'id': '...'}
          {'type': 'done', 'text': '...', 'tool_calls': [...]}
          {'type': 'error', 'text': '...'}
        """
        contents, system_text = self._to_gemini_contents(payload.get("messages", []))
        if not contents:
            yield {"type": "error", "text": "No user/model messages to send."}
            return

        base_payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": payload.get("temperature", 0.6),
                # Thinking-capable models (gemini-3-flash-preview, 2.5-flash)
                # spend part of this budget on invisible reasoning tokens
                # before writing the visible answer. A 1024 cap let complex
                # prompts get truncated (finishReason=MAX_TOKENS) with zero
                # visible text — that's the "(no reply from model)" bug.
                "maxOutputTokens": max(payload.get("max_tokens") or 4096, 4096),
            },
        }
        if system_text:
            base_payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        if payload.get("tools"):
            gt = self._to_gemini_tools()
            if gt:
                base_payload["tools"] = gt

        last_err = ""
        saw_non_quota = False
        keys = CONFIG.all_keys()
        if not keys:
            yield {"type": "error",
                   "text": "No Gemini API key configured (set JARVIS_GEMINI_KEY in .env)."}
            return
        order = self._key_order(keys)
        for model in (models or self._models_to_try(payload.get("model"))):
            for ki in order:
                key = keys[ki]
                url = f"{GEMINI_BASE}/{model}:streamGenerateContent"
                try:
                    resp = self.session.post(
                        url,
                        params={"key": key, "alt": "sse"},
                        json=base_payload, stream=True, timeout=(5, 120),
                    )
                except requests.RequestException as exc:
                    last_err = f"{model}: network {exc}"
                    saw_non_quota = True
                    continue
                if resp.status_code != 200:
                    body = ""
                    try:
                        body = resp.text[:200]
                    except Exception:  # noqa: BLE001
                        pass
                    if self._is_quota_error(resp.status_code, body):
                        last_err = f"{model} key#{ki+1}: {resp.status_code} {body}"
                        self._mark_key_dead(resp.status_code)
                        continue
                    if resp.status_code in RETRYABLE_KEY_STATUS or resp.status_code in FATAL_KEY_STATUS:
                        last_err = f"{model} key#{ki+1}: {resp.status_code} {body}"
                        saw_non_quota = True
                        self._mark_key_dead(resp.status_code)
                        continue
                    # 400 — try next model
                    last_err = f"{model} key#{ki+1}: {resp.status_code} {body}"
                    saw_non_quota = True
                    break

                # We got a 200 — remember which key worked and parse the SSE stream.
                self._key_index = ki
                yield from self._parse_stream(resp, model)
                return
            # try next model

        yield {"type": "error",
               "text": self._exhausted_text(saw_non_quota, last_err, len(keys))}

    def _parse_stream(self, resp, model: str) -> Iterator[dict]:
        """Parse Gemini's SSE stream and yield normalized events."""
        content_parts: list[str] = []
        tool_calls: list[dict] = []
        finish_reason = None
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            # Gemini SSE: lines starting with "data: " contain JSON.
            if raw.startswith("data: "):
                data_str = raw[6:]
            else:
                data_str = raw
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                # Malformed / truncated SSE line (e.g. connection cut
                # mid-line) — skip it and keep streaming.
                continue
            candidates = chunk.get("candidates") or []
            if not candidates:
                # Prompt itself may have been blocked (safety filter) before
                # any candidate was even generated.
                block = (chunk.get("promptFeedback") or {}).get("blockReason")
                if block:
                    finish_reason = f"BLOCKED:{block}"
                continue
            cand = candidates[0]
            fr = cand.get("finishReason")
            if fr:
                finish_reason = fr
            for part in (cand.get("content", {}) or {}).get("parts", []) or []:
                if "text" in part and part["text"]:
                    content_parts.append(part["text"])
                    yield {"type": "token", "text": part["text"]}
                if "functionCall" in part:
                    fc = part["functionCall"]
                    name = fc.get("name", "")
                    args = fc.get("args") or {}
                    call_id = f"call_{len(tool_calls)}_{int(time.time()*1000)}"
                    tool_calls.append({
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    })
                    yield {"type": "tool", "name": name, "args": args}

        final_text = "".join(content_parts).strip()
        yield {
            "type": "done",
            "text": final_text,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "model": model,
        }

    # ── tool execution helper ────────────────────────────────
    def _run_tools(self, tool_calls: list[dict], tool_cb) -> Iterator[dict]:
        """Run a batch of tool calls. Yields events:
          {'type': 'tool_done', 'name': str, 'result': str, 'id': str}
        For tools that require approval, yields 'approval_required' first and
        waits for the user before dispatching.
        """
        # Record the assistant message with all tool_calls so the conversation
        # stays well-formed even if the user denies.
        assistant_msg = {"role": "assistant", "content": None, "tool_calls": tool_calls}
        self.memory.add_raw(assistant_msg)
        for call in tool_calls:
            name = call["function"]["name"]
            call_id = call.get("id") or f"call_{id(call)}"
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            # Approval gate — skipped entirely in full-trust/owner mode
            # (CONFIG.owner_trust), so JARVIS just runs the tool.
            if (self.registry and self.registry.requires_approval(name)
                    and not CONFIG.owner_trust):
                self.memory.store_pending(call_id, name, args, call)
                yield {
                    "type": "approval_required",
                    "id": call_id,
                    "name": name,
                    "args": args,
                }
                return  # caller will resume via resolve_approval

            if tool_cb:
                tool_cb(name, args)
            try:
                result = self.dispatch(name, args)
            except Exception as exc:  # noqa: BLE001
                result = f"ERROR while running {name}: {exc}"
            self.memory.add_raw({
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": str(result),
            })
            yield {"type": "tool_done", "name": name, "result": str(result), "id": call_id}

    # ── non-streaming (CLI) ──────────────────────────
    def ask(self, user_text: str, max_tool_rounds: int = 6, on_tool=None) -> str:
        tool_cb = on_tool or self.on_tool
        if not any(m.get("role") == "user" and m.get("content") == user_text
                   for m in self.memory.messages[-2:]):
            self.memory.add("user", user_text)
        for _ in range(max_tool_rounds):
            events = list(self._post_stream(
                {
                    "model": CONFIG.model,
                    "messages": self.memory.as_list(),
                    "tools": self.tools_schema,
                    "temperature": 0.6,
                }
            ))
            err = next((e for e in events if e.get("type") == "error"), None)
            if err:
                raise RuntimeError(err.get("text", "Gemini error"))
            done = next((e for e in events if e.get("type") == "done"), None)
            if not done:
                continue
            tool_calls = done.get("tool_calls") or []
            if not tool_calls:
                content = done.get("text", "").strip()
                self.memory.add("assistant", content)
                return content
            # Consume the tool generator fully; in CLI we just execute.
            for _ in self._run_tools(tool_calls, tool_cb):
                pass
        fallback = "I hit the automation step limit. Let's try that again more simply."
        self.memory.add("assistant", fallback)
        return fallback

    def complete(self, prompt: str, max_tokens: int = 800) -> str:
        """One-shot completion (no tool-calls, no memory). Used by the
        agent planner / reflection to emit structured JSON cheaply.

        Tries the configured model first, then falls back to a known-stable
        model (gemini-2.0-flash) because some lightweight models (e.g.
        -flash-lite) intermittently return empty candidates for JSON prompts.
        """
        fallback_models = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
        models = list(dict.fromkeys([CONFIG.model, *fallback_models]))
        last_err: Exception | None = None
        for model in models:
            try:
                data = self._post(
                    {
                        "model": model,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2,
                        "max_tokens": max_tokens,
                        "top_p": 0.95,
                    }
                )
                text = _extract_text(data)
                if text and text.strip():
                    return text
                # empty candidate — try next model
                last_err = RuntimeError(f"{model}: empty response")
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
        raise RuntimeError(
            f"complete() failed across all models: {last_err}"
        )
    def stream_ask(self, user_text: str, max_tool_rounds: int = 6) -> Iterator[dict]:
        """Yield events: tool|approval_required|token|done|error."""
        self.memory.add("user", user_text)

        for _ in range(max_tool_rounds):
            payload = {
                "model": CONFIG.model,
                "messages": self.memory.as_list(),
                "tools": self.tools_schema,
                "temperature": 0.6,
            }
            done_event: dict | None = None
            for ev in self._post_stream(payload):
                etype = ev.get("type")
                if etype == "done":
                    done_event = ev
                elif etype == "error":
                    yield ev
                    return
                else:
                    yield ev  # token / tool (announced before execution)

            if done_event is None:
                return

            tool_calls = done_event.get("tool_calls") or []
            if not tool_calls:
                final = (done_event.get("text") or "").strip()
                if final:
                    self.memory.add("assistant", final)
                    yield {"type": "done", "text": final}
                else:
                    yield {"type": "error", "text": _empty_reply_text(done_event.get("finish_reason"))}
                return

            # Run tools (may yield approval_required and pause).
            events = list(self._run_tools(tool_calls, None))
            approval_pending = any(e.get("type") == "approval_required" for e in events)
            yield from events
            if approval_pending:
                return
            # Otherwise loop again with tool results in the conversation.

        yield {"type": "done", "text": "I hit the automation step limit."}

    # ── vision ───────────────────────────────────────
    def vision(self, text: str, image_data_url: str) -> str:
        """One-shot image understanding. Gemini is natively multimodal."""
        prompt = text.strip() or "Describe this image in detail."
        # Pull out the base64 payload from a data URL.
        if image_data_url.startswith("data:"):
            try:
                header, b64 = image_data_url.split(",", 1)
                mime = header.split(";")[0].split(":", 1)[1] or "image/png"
            except ValueError:
                mime, b64 = "image/png", image_data_url
        else:
            mime, b64 = "image/png", image_data_url

        # Build a one-off payload — don't add to the long-term memory.
        payload = {
            "model": VISION_MODELS[0],
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    # We use the raw OpenAI-shape here just to leverage
                    # _to_gemini_contents. The "image_url" key is not
                    # understood by Gemini — we extract the image below.
                ]}
            ],
            "temperature": 0.5,
        }
        contents, system_text = self._to_gemini_contents(payload["messages"])
        # Inject the image as a proper inline_data part.
        if contents and contents[0].get("parts"):
            contents[0]["parts"].insert(0, {
                "inline_data": {"mime_type": mime, "data": b64}
            })
        base_payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": payload.get("temperature", 0.5),
                "maxOutputTokens": 1024,
            },
        }

        last_err = ""
        saw_non_quota = False
        keys = CONFIG.all_keys()
        order = self._key_order(keys)
        for model in VISION_MODELS:
            for ki in order:
                key = keys[ki]
                url = f"{GEMINI_BASE}/{model}:generateContent"
                try:
                    resp = self.session.post(
                        url, params={"key": key},
                        json=base_payload, timeout=(5, 90),
                    )
                except requests.RequestException as exc:
                    last_err = f"{model}: {exc}"
                    saw_non_quota = True
                    continue
                if resp.status_code == 200:
                    self._key_index = ki
                    data = resp.json()
                    reply = _extract_text(data)
                    self.memory.add("user", f"[sent an image] {prompt}")
                    self.memory.add("assistant", reply)
                    return reply
                body = resp.text[:140]
                if self._is_quota_error(resp.status_code, body):
                    last_err = f"{model} key#{ki+1}: {resp.status_code} {body}"
                    self._mark_key_dead(resp.status_code)
                    continue
                if resp.status_code in RETRYABLE_KEY_STATUS or resp.status_code in FATAL_KEY_STATUS:
                    last_err = f"{model} key#{ki+1}: {resp.status_code} {body}"
                    saw_non_quota = True
                    self._mark_key_dead(resp.status_code)
                    continue
                last_err = f"{model} key#{ki+1}: {resp.status_code} {body}"
                saw_non_quota = True
                break
        raise RuntimeError(self._exhausted_text(saw_non_quota, last_err, len(keys)))

    # ── see_screen binding ───────────────────────────
    def see_screen(self, question: str = "") -> str:
        """Take a screenshot, send it to the vision model, return description."""
        try:
            import pyautogui
        except ImportError:
            return "pyautogui is not installed. Run: pip install pyautogui"
        try:
            img = pyautogui.screenshot()
        except Exception as exc:  # noqa: BLE001
            return f"Couldn't capture screen: {exc}"
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"
        prompt = (question.strip() or
                  "Describe what's currently on the screen in detail.")
        try:
            reply = self.vision(prompt, data_url)
        except Exception as exc:  # noqa: BLE001
            return f"Vision failed: {exc}"
        return reply

    def bind_see_screen(self) -> None:
        """Wire Brain.see_screen into the registry."""
        if self.registry is None:
            return
        self.registry.replace_func("see_screen", self.see_screen)

    # ── approval resolution ──────────────────────────
    def resolve_approval(self, call_id: str, approved: bool) -> dict | None:
        """Called from /api/approve. Resumes a pending tool call."""
        pending = self.memory.take_pending(call_id)
        if not pending:
            return None
        name = pending["name"]
        args = pending["args"]
        if not approved:
            self.memory.add_raw({
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": "User denied this action. Inform them and suggest an alternative if appropriate.",
            })
            return {"type": "denied", "name": name, "args": args}
        try:
            result = self.dispatch(name, args)
        except Exception as exc:  # noqa: BLE001
            result = f"ERROR while running {name}: {exc}"
        self.memory.add_raw({
            "role": "tool",
            "tool_call_id": call_id,
            "name": name,
            "content": str(result),
        })
        return {"type": "approved", "name": name, "result": str(result), "args": args}

    def continue_after_approval(self, max_tool_rounds: int = 4) -> Iterator[dict]:
        """Resume the streaming loop after an approval was granted/denied."""
        for _ in range(max_tool_rounds):
            payload = {
                "model": CONFIG.model,
                "messages": self.memory.as_list(),
                "tools": self.tools_schema,
                "temperature": 0.6,
            }
            done_event: dict | None = None
            for ev in self._post_stream(payload):
                etype = ev.get("type")
                if etype == "done":
                    done_event = ev
                elif etype == "error":
                    yield ev
                    return
                else:
                    yield ev

            if done_event is None:
                return

            tool_calls = done_event.get("tool_calls") or []
            if not tool_calls:
                final = (done_event.get("text") or "").strip()
                if final:
                    self.memory.add("assistant", final)
                    yield {"type": "done", "text": final}
                else:
                    yield {"type": "error", "text": _empty_reply_text(done_event.get("finish_reason"))}
                return

            events = list(self._run_tools(tool_calls, None))
            approval_pending = any(e.get("type") == "approval_required" for e in events)
            yield from events
            if approval_pending:
                return

        yield {"type": "done", "text": "I hit the automation step limit."}

    # ── session summarization ────────────────────────
    def summarize_session(self, messages: list[dict], max_words: int = 80) -> str:
        """Ask the model to produce a short summary of a past conversation."""
        convo = []
        for m in messages:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if not content or role not in ("user", "assistant"):
                continue
            convo.append(f"{role.upper()}: {content[:400]}")
        if not convo:
            return ""
        text = "\n".join(convo[-30:])
        prompt = (
            "Summarize the following conversation in one or two short sentences "
            f"(under {max_words} words). Focus on topics, decisions, and any facts "
            "worth remembering. Reply with the summary only — no preamble.\n\n"
            f"{text}"
        )
        # Bypass the conversation memory — single-turn call.
        payload = {
            "model": CONFIG.model,
            "messages": [
                {"role": "system", "content": "You are a concise summarizer."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }
        events = list(self._post_stream(payload))
        err = next((e for e in events if e.get("type") == "error"), None)
        if err:
            raise RuntimeError(err.get("text", "Gemini error"))
        done = next((e for e in events if e.get("type") == "done"), None)
        return (done.get("text", "") if done else "").strip()


# ── small helpers (module-level) ────────────────────────────
def _safe_json_loads(s: str | dict) -> dict:
    if isinstance(s, dict):
        return s
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}


def _safe_truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "…"


def _extract_text(data: dict[str, Any]) -> str:
    """Pull the first text part from a Gemini response."""
    try:
        cand = (data.get("candidates") or [{}])[0]
        for part in (cand.get("content", {}) or {}).get("parts", []) or []:
            if "text" in part and part["text"]:
                return part["text"]
    except (IndexError, KeyError, TypeError):
        pass
    return ""


def _gemini_to_openai_shape(data: dict[str, Any], model: str) -> dict[str, Any]:
    """Convert a non-streaming Gemini response into the OpenAI shape
    that the rest of JARVIS already understands (and that callers expect
    from _post). Mostly used for internal consistency / debugging.
    """
    text = _extract_text(data)
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": text,
            },
            "finish_reason": "stop",
        }],
        "model": model,
    }
