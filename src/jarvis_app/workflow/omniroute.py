"""Read-only local OmniRoute completion-log bridge.

Never forwards requestBody/responseBody/error/account/connection/key fields. Fallbacks are
observed only across failed attempts with the same explicit comboExecutionKey. A mere
requested/served model difference is not proof of fallback. No provider settings change.
"""
from collections import OrderedDict
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid


class OmniRouteBridge:
    def __init__(self, bus, directory, interval=1):
        self.bus = bus
        self.directory = Path(directory).expanduser() if directory else None
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._seen = OrderedDict()
        self._combos = OrderedDict()
        self._files = OrderedDict()
        self._baseline = None

    def ingest(self, summary):
        if not isinstance(summary, dict) or not isinstance(summary.get("id"), str):
            return False
        sid = summary["id"]
        if not sid or len(sid) > 200 or sid in self._seen:
            return False
        status = summary.get("status")
        if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
            return False
        self._seen[sid] = True
        while len(self._seen) > 2000:
            self._seen.popitem(last=False)
        combo = summary.get("comboExecutionKey")
        if not isinstance(combo, str) or not combo or len(combo) > 200:
            combo = None
        run_id = uuid.uuid5(uuid.NAMESPACE_URL, "omniroute:" + (combo or sid)).hex
        node_id = uuid.uuid5(uuid.NAMESPACE_URL, "omniroute-call:" + sid).hex
        provider = summary.get("provider")
        model = summary.get("model")
        requested = summary.get("requestedModel")
        previous = self._combos.get(combo) if combo else None
        data = {"source": "omniroute", "visibility": "completion_log", "provider": provider,
                "model": model, "requested_model": requested, "served_model": model if status < 400 else None,
                "ms": summary.get("duration"), "status_code": status,
                "label": "OmniRoute completed request", "operation": "provider_request",
                "recorded_at": summary.get("timestamp")}
        parent_id = previous["node_id"] if previous else None
        if previous and previous["failed"]:
            # Retried combo attempts are facts; provider fallback requires observed route change.
            changed = bool((previous["provider"] and provider and previous["provider"] != provider)
                           or (previous["model"] and model and previous["model"] != model))
            if changed:
                fallback_id = uuid.uuid5(uuid.NAMESPACE_URL, "omniroute-fallback:" + sid).hex
                self.bus.emit("provider.fallback", run_id=run_id, node_id=fallback_id,
                              parent_id=parent_id, status="completed", source="omniroute",
                              label="Observed combo fallback", from_provider=previous["provider"],
                              to_provider=provider, from_model=previous["model"], to_model=model,
                              fallback_observed=True, visibility="completion_log", reason="failed_combo_attempt")
                parent_id = fallback_id
        self.bus.emit("omniroute.request." + ("error" if status >= 400 else "completed"),
                      run_id=run_id, node_id=node_id, parent_id=parent_id,
                      status="error" if status >= 400 else "completed",
                      error_code=f"HTTP_{status}" if status >= 400 else None, **data)
        if combo:
            self._combos[combo] = {"node_id": node_id, "failed": status >= 400,
                                   "provider": provider, "model": model}
            self._combos.move_to_end(combo)
            while len(self._combos) > 200:
                self._combos.popitem(last=False)
        return True

    def scan(self, initial=False):
        if not self.directory or not self.directory.is_dir():
            return 0
        # Only today's completion directory, bounded recent candidates. Logs are final
        # summaries; this bridge does not imply that in-flight attempts are observable.
        folder = self.directory / datetime.now(timezone.utc).date().isoformat()
        candidates = sorted(folder.glob("*.json"), reverse=True)[:200]
        if initial:
            candidates = candidates[:24]
            self._baseline = min((p.name for p in candidates), default=None)
        count = 0
        for path in reversed(candidates):
            try:
                if self._baseline and path.name < self._baseline:
                    continue
                info = path.stat()
                version = (info.st_mtime_ns, info.st_size)
                if self._files.get(str(path)) == version:
                    continue
                if path.is_symlink() or not path.is_file() or info.st_size > 1_048_576:
                    continue
                record = json.loads(path.read_bytes())
                summary = record.get("summary") if isinstance(record, dict) else None
                if isinstance(summary, dict) and summary.get("id") not in self._seen:
                    count += self.ingest(summary)
                self._files[str(path)] = version
                self._files.move_to_end(str(path))
                while len(self._files) > 1000:
                    self._files.popitem(last=False)
            except (OSError, ValueError, TypeError):
                # A partially written/rotated log may be retried; never log body/error.
                continue
        return count

    def start(self):
        if self._thread:
            return
        available = bool(self.directory and self.directory.is_dir())
        self.bus.emit("bridge.status", run_id="omniroute-bridge", node_id="omniroute-bridge",
                      status="completed" if available else "unknown", source="omniroute",
                      label="OmniRoute completion-log bridge", available=available,
                      visibility="completion_log", reason="local_logs_available" if available else "local_logs_unavailable")
        if not available:
            return
        self.scan(initial=True)
        self._thread = threading.Thread(target=self._loop, name="jarvis-omniroute-monitor", daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.wait(self.interval):
            self.scan()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
