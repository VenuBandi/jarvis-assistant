"""Provider-neutral chat types. Every adapter turns the neutral message list into its own wire format and
returns a ChatResult. Neutral messages:
  {"role": "user"|"assistant", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [ToolCall...]}
  {"role": "tool", "call_id": str, "name": str, "content": str}
"""
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ChatResult:
    text: str = ""
    tool_calls: list = field(default_factory=list)
    model: str = ""
    stop: str = ""
    model_reported: bool = True


class ProviderError(Exception):
    """Raised with a short, secret-free message the UI can show."""


class Provider:
    def chat(self, model: str, system: str, messages: list, tools: list | None) -> ChatResult:
        raise NotImplementedError

    def chat_stream(self, model: str, system: str, messages: list, tools: list | None, on_text) -> ChatResult:
        """Like chat, calling on_text(piece) as the answer text is written. Providers without streaming give the
        whole text in one piece at the end."""
        r = self.chat(model, system, messages, tools)
        if r.text and not r.tool_calls:
            on_text(r.text)
        return r

    def ping(self, model: str) -> str:
        """Tiny live call proving the model answers. Returns the served model id."""
        r = self.chat(model, "Reply with the single word PONG.", [{"role": "user", "content": "ping"}], None)
        if not (r.text or "").strip() and not r.tool_calls:
            raise ProviderError("empty reply to ping")
        self.last_ping_model_reported = r.model_reported and bool(r.model)
        return r.model or model
