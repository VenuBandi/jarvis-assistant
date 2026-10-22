"""Bounded metadata-only journal. Instrumentation never stores message/tool/memory bodies.

The journal is per-process, not a persistent audit ledger. SSE readers pull by sequence;
slow readers cannot build unbounded queues. A new instance or retention gap requires reset.
"""
from collections import deque
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import math
import re
import threading
import time
import uuid

from ..security.secrets import redact

_SCOPE = ContextVar("jarvis_workflow_scope", default=None)
FIELDS = {"label", "source", "provider", "model", "requested_model", "served_model", "tool", "operation",
          "ms", "count", "error_code", "reason", "attempt", "from_provider", "to_provider", "from_model",
          "to_model", "status_code", "fallback_observed", "visibility", "available", "trace_id", "recorded_at",
          "task_id", "agent", "checker", "recorded_state", "review_state", "output_path", "source_path", "stale"}
STATUSES = {"running", "completed", "error", "waiting", "denied", "stopped", "rejected", "invalid", "unknown"}
NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")


def safe_text(value):
    text = redact(str(value))
    # Redact before applying bounds; never leak a prefix of a truncated credential.
    if len(text) > 240:
        return "[metadata omitted]"
    return "".join(ch for ch in text if ord(ch) >= 32)


def metadata(values):
    result = {}
    for key, value in values.items():
        if key not in FIELDS or value is None:
            continue
        if isinstance(value, bool):
            result[key] = value
        elif isinstance(value, (float, int)):
            if math.isfinite(value):
                result[key] = max(-1e12, min(value, 1e12))
        elif isinstance(value, str):
            result[key] = safe_text(value)
    return result


class EventBus:
    def __init__(self, capacity=1000):
        if not 1 <= capacity <= 10000:
            raise ValueError("invalid workflow capacity")
        self.capacity = capacity
        self.instance_id = uuid.uuid4().hex
        self._events = deque(maxlen=capacity)
        self._cursor = 0
        self._lock = threading.Lock()

    def emit(self, kind, node_id=None, parent_id=None, status=None, run_id=None, **data):
        scope = _SCOPE.get()
        if scope and scope.bus is self:
            run_id = run_id or scope.run_id
            node_id = node_id or scope.node_id
            parent_id = parent_id if parent_id is not None else scope.parent_id
        run_id = run_id or uuid.uuid4().hex
        node_id = node_id or run_id
        event = {"at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                 "run_id": safe_text(run_id), "node_id": safe_text(node_id),
                 "parent_id": safe_text(parent_id) if parent_id else None,
                 "kind": kind if isinstance(kind, str) and NAME.fullmatch(kind) else "workflow.event",
                 "status": status if status in STATUSES else "unknown", "data": metadata(data)}
        with self._lock:
            self._cursor += 1
            event["id"] = self._cursor
            self._events.append(event)
            return deepcopy(event)

    def snapshot(self):
        with self._lock:
            return {"instance_id": self.instance_id, "cursor": self._cursor,
                    "first_id": self._events[0]["id"] if self._events else self._cursor + 1,
                    "events": deepcopy(list(self._events))}

    def read(self, after=0, instance_id=None, limit=128):
        with self._lock:
            first = self._events[0]["id"] if self._events else self._cursor + 1
            reset = bool((instance_id and instance_id != self.instance_id)
                         or after > self._cursor or after < first - 1)
            return {"reset": reset, "instance_id": self.instance_id, "cursor": self._cursor,
                    "first_id": first,
                    "events": deepcopy([e for e in self._events if e["id"] > after][:max(1, min(limit, 256))])}

    def run(self, action="chat", source="jarvis", **data):
        return Span(self, "run", label=action, source=source, root=True, **data)

    def span(self, kind, **data):
        return Span(self, kind, **data)


class Span:
    def __init__(self, bus, kind, root=False, **data):
        self.bus, self.kind, self.data = bus, kind, data
        parent = _SCOPE.get()
        self.run_id = uuid.uuid4().hex if root or not parent or parent.bus is not bus else parent.run_id
        self.node_id = self.run_id if root else uuid.uuid4().hex
        self.parent_id = parent.node_id if not root and parent and parent.bus is bus else None
        self.status = "completed"

    def __enter__(self):
        self.started = time.monotonic()
        self.token = _SCOPE.set(self)
        self.bus.emit(self.kind + ".started", status="running", **self.data)
        return self

    def finish(self, status="completed", **data):
        self.status = status if status in STATUSES else "unknown"
        self.data.update(data)

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                self.status = "error"
                self.data["error_code"] = exc_type.__name__
            self.data.setdefault("ms", round((time.monotonic() - self.started) * 1000, 2))
            self.bus.emit(self.kind + "." + self.status, status=self.status, **self.data)
        finally:
            _SCOPE.reset(self.token)
        return False
