"""Central tool registry. Each tool declares name, description, input model (pydantic → JSON schema), output
description, permissions, read_only, confirm, timeout and retries. execute() validates arguments, enforces the
timeout, retries only read-only tools, and returns a ToolOutcome. Audit logging is done by the orchestrator."""
import concurrent.futures
from contextvars import copy_context
import time
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, ValidationError

from ..security.secrets import redact

_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="jarvis-tool")


@dataclass
class Tool:
    name: str
    description: str
    input_model: type
    output: str
    run: Callable
    permissions: list = field(default_factory=list)
    read_only: bool = True
    confirm: bool = False
    timeout_s: float = 20.0
    retries: int = 0

    def schema(self):
        s = self.input_model.model_json_schema()
        s.pop("title", None)
        return {"name": self.name, "description": self.description, "parameters": s}


@dataclass
class ToolOutcome:
    ok: bool
    content: str
    ms: int = 0
    error: str = ""


class ToolRegistry:
    def __init__(self):
        self.tools = {}
        self.disabled_permissions = set()

    def register(self, tool: Tool):
        if tool.name in self.tools:
            raise ValueError(f"duplicate tool {tool.name}")
        if not tool.read_only and not tool.confirm:
            raise ValueError(f"tool {tool.name} writes data, so it must require confirmation")
        self.tools[tool.name] = tool

    def available(self):
        return [t for t in self.tools.values() if not (set(t.permissions) & self.disabled_permissions)]

    def schemas(self):
        return [t.schema() for t in self.available()]

    def get(self, name):
        return self.tools.get(name)

    def permission_ok(self, tool):
        blocked = set(tool.permissions) & self.disabled_permissions
        return not blocked, sorted(blocked)

    def validate(self, tool, args):
        try:
            return tool.input_model.model_validate(args or {}), None
        except ValidationError as e:
            return None, "; ".join(f"{'.'.join(map(str, x['loc'])) or 'input'}: {x['msg']}" for x in e.errors())[:400]

    def execute(self, tool, parsed: BaseModel, ctx) -> ToolOutcome:
        attempts = 1 + (tool.retries if tool.read_only else 0)
        last = ""
        for i in range(attempts):
            t0 = time.time()
            fut = _POOL.submit(copy_context().run, tool.run, parsed, ctx)
            try:
                out = fut.result(timeout=tool.timeout_s)
                return ToolOutcome(True, redact(out if isinstance(out, str) else repr(out))[:8000],
                                   int((time.time() - t0) * 1000))
            except concurrent.futures.TimeoutError:
                last = f"timed out after {tool.timeout_s:.0f}s"
            except Exception as e:  # noqa: BLE001 - tool failure is reported, not raised
                last = redact(f"{type(e).__name__}: {e}")[:400]
            if i + 1 < attempts:
                time.sleep(0.5 * (i + 1))
        return ToolOutcome(False, "", 0, last)
