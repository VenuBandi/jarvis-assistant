"""Provider adapters: Anthropic Messages API (REST via httpx, no SDK installed), OpenAI-compatible
/v1/chat/completions (OmniRoute or any compatible endpoint), Ollama /api/chat, and a deterministic mock.
No proxies, no redirects; errors are redacted before they leave."""
import json
import uuid

import httpx

from ..security.secrets import redact
from .base import ChatResult, Provider, ProviderError, ToolCall

TIMEOUT = httpx.Timeout(120.0, connect=5.0)


def _client():
    return httpx.Client(timeout=TIMEOUT, follow_redirects=False, trust_env=False)


def _post(url, headers, body):
    try:
        with _client() as c:
            r = c.post(url, headers=headers, json=body)
    except httpx.HTTPError as e:
        raise ProviderError(redact(f"{type(e).__name__}: {e}")) from None
    if r.status_code >= 400:
        raise ProviderError(redact(f"HTTP {r.status_code}: {r.text[:300]}"))
    try:
        return r.json()
    except ValueError:
        raise ProviderError("reply was not JSON") from None


class AnthropicProvider(Provider):
    def __init__(self, base_url, key_fn):
        self.base, self.key_fn = base_url.rstrip("/"), key_fn

    def chat(self, model, system, messages, tools):
        key = self.key_fn()
        if not key:
            raise ProviderError("no Anthropic API key configured (Keychain 'jarvis/anthropic_api_key' or ANTHROPIC_API_KEY)")
        out = []
        for m in messages:
            if m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["call_id"], "content": m["content"]}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                blocks = ([{"type": "text", "text": m["content"]}] if m.get("content") else []) + [
                    {"type": "tool_use", "id": t.id, "name": t.name, "input": t.args} for t in m["tool_calls"]]
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": m["role"], "content": m["content"]})
        body = {"model": model, "max_tokens": 2048, "system": system, "messages": out}
        if tools:
            body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                             for t in tools]
        j = _post(f"{self.base}/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01",
                                                "content-type": "application/json"}, body)
        res = ChatResult(model=j.get("model", model), model_reported=bool(j.get("model")), stop=j.get("stop_reason", ""))
        for b in j.get("content", []):
            if b.get("type") == "text":
                res.text += b.get("text", "")
            elif b.get("type") == "tool_use":
                res.tool_calls.append(ToolCall(b["id"], b["name"], b.get("input") or {}))
        return res


class OpenAICompatProvider(Provider):
    def __init__(self, base_url, key_fn):
        self.base, self.key_fn = base_url.rstrip("/"), key_fn

    def chat(self, model, system, messages, tools):
        key = self.key_fn()
        out = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["call_id"], "content": m["content"]})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": [
                    {"id": t.id, "type": "function", "function": {"name": t.name, "arguments": json.dumps(t.args)}}
                    for t in m["tool_calls"]]})
            else:
                out.append({"role": m["role"], "content": m["content"]})
        body = {"model": model, "messages": out, "max_tokens": 2048, "stream": False}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        headers = {"content-type": "application/json"}
        if key:
            headers["authorization"] = "Bearer " + key
        j = _post(f"{self.base}/chat/completions", headers, body)
        try:
            ch = j["choices"][0]
            msg = ch["message"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("unexpected reply shape") from None
        res = ChatResult(text=msg.get("content") or "", model=j.get("model", model), model_reported=bool(j.get("model")), stop=ch.get("finish_reason", ""))
        for t in msg.get("tool_calls") or []:
            try:
                args = json.loads(t["function"].get("arguments") or "{}")
            except ValueError:
                args = {"__unparsed__": t["function"].get("arguments")}
            res.tool_calls.append(ToolCall(t.get("id") or uuid.uuid4().hex[:8], t["function"]["name"], args))
        return res


class OllamaProvider(Provider):
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")

    def chat(self, model, system, messages, tools):
        out = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "tool":
                out.append({"role": "tool", "content": m["content"], "tool_name": m.get("name", "")})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                out.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": [
                    {"function": {"name": t.name, "arguments": t.args}} for t in m["tool_calls"]]})
            else:
                out.append({"role": m["role"], "content": m["content"]})
        body = {"model": model, "messages": out, "stream": False, "think": False,
                "options": {"num_ctx": 16384, "temperature": 0.2}}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        j = _post(f"{self.base}/api/chat", {"content-type": "application/json"}, body)
        msg = j.get("message") or {}
        res = ChatResult(text=msg.get("content") or "", model=j.get("model", model), model_reported=bool(j.get("model")), stop=j.get("done_reason", ""))
        for t in msg.get("tool_calls") or []:
            f = t.get("function") or {}
            args = f.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {"__unparsed__": args}
            res.tool_calls.append(ToolCall(uuid.uuid4().hex[:8], f.get("name", ""), args))
        return res


class MockProvider(Provider):
    """Deterministic test brain: 'tool:<name> {json}' in the last user message → that tool call; after a tool
    result → 'Result: <content>'; otherwise echoes. Never used unless selected."""

    def chat(self, model, system, messages, tools):
        last = messages[-1]
        if last["role"] == "tool":
            return ChatResult(text=f"Result: {last['content']}", model=model, stop="end")
        text = last.get("content", "")
        if text.startswith("tool:") and tools:
            name, _, rest = text[5:].partition(" ")
            return ChatResult(tool_calls=[ToolCall("call-" + uuid.uuid4().hex[:6], name, json.loads(rest or "{}"))],
                              model=model, stop="tool_use")
        return ChatResult(text=f"Echo: {text}", model=model, stop="end")
