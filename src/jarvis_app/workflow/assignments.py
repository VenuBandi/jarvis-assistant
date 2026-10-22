"""Read-only FlightOps handoff/allocation metadata -> observed workflow records.

Recorded running is NOT live execution. Done is NOT an accepted review. Artifact bodies,
prompts, stderr, task notes and acceptance prose never enter the monitor. No task runs here.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import threading
import uuid

ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_BYTES = 1_048_576
ALLOCATION = "docs/office/roles/provider_allocation_2026-10-21.json"
REVIEWS = {"accept": "accepted", "accepted": "accepted", "accept_with_notes": "accepted_with_notes",
           "accepted_with_notes": "accepted_with_notes", "reject": "rejected", "rejected": "rejected",
           "pending": "pending", "unverified": "unverified"}


def normalize_review(value):
    if isinstance(value, dict):
        value = value.get("verdict") or value.get("state")
    return REVIEWS.get(value, "unverified") if isinstance(value, str) else "unverified"


class AssignmentBridge:
    def __init__(self, bus, root, interval=2):
        self.bus = bus
        self.root = Path(root).resolve() if root else None
        self.interval = interval
        self._records = {}
        self._stop = threading.Event()
        self._thread = None

    def _open(self, relative):
        """Descriptor traversal: reject links, directories/leaves outside the selected root."""
        if not self.root or not isinstance(relative, str) or len(relative) > 240:
            raise ValueError("unsafe path")
        path = PurePosixPath(relative)
        if path.is_absolute() or not path.parts or ".." in path.parts or "\\" in relative or any(ord(c) < 32 for c in relative):
            raise ValueError("unsafe path")
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for index, part in enumerate(path.parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if index < len(path.parts) - 1:
                    flags |= os.O_DIRECTORY
                following = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = following
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("not a single regular file")
            result = fd
            fd = None
            return result, info
        finally:
            if fd is not None:
                os.close(fd)

    def _read(self, relative):
        try:
            fd, info = self._open(relative)
            with os.fdopen(fd, "rb") as handle:
                if info.st_size > MAX_BYTES:
                    return None, None
                blob = handle.read(MAX_BYTES + 1)
            if len(blob) > MAX_BYTES:
                return None, None
            obj = json.loads(blob)
            return (obj, info.st_mtime) if isinstance(obj, dict) else (None, None)
        except (OSError, ValueError, TypeError):
            return None, None

    def _reference(self, path):
        if not isinstance(path, str):
            return None
        pp = PurePosixPath(path)
        if pp.is_absolute() or ".." in pp.parts or "\\" in path or len(path) > 240 or any(ord(c) < 32 for c in path):
            return None
        allowed = path.startswith(("reports/", "docs/office/", "artifacts/handoff/"))
        if not allowed or pp.suffix not in {".md", ".json", ".csv"}:
            return None
        if any(part.lower() in {"keys", "secrets", "logs", "config", "data"} for part in pp.parts):
            return None
        if pp.name in {"prompt.md", "task.json", "key.json"}:
            return None
        try:
            fd, _ = self._open(path)
            os.close(fd)
            return path, True
        except (OSError, ValueError, TypeError):
            return path, False

    @staticmethod
    def _time(record, modified):
        for key in ("last_activity", "finished_at", "updated_at", "started_at"):
            value = record.get(key)
            if isinstance(value, str):
                try:
                    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if stamp.tzinfo is not None:
                        return value, stamp.timestamp(), "record_timestamp"
                except ValueError:
                    pass
        if modified is not None:
            return datetime.fromtimestamp(modified, timezone.utc).isoformat(), modified, "file_mtime_no_task_timestamp"
        return None, None, "timestamp_unavailable"

    def _task(self, key, task, source_path, modified, available=True):
        run = uuid.uuid5(uuid.NAMESPACE_URL, "flightops-assignment:" + key).hex
        root_node = run
        recorded = task.get("state") if isinstance(task.get("state"), str) else "unknown"
        when, stamp, reason = self._time(task, modified)
        active = recorded in {"running", "queued", "waiting", "in_progress"}
        stale = bool(active and (reason != "record_timestamp" or stamp is None or
                                datetime.now(timezone.utc).timestamp() - stamp > 120))
        # This is record state, never a live started/running execution event.
        status = "completed" if recorded in {"done", "completed", "completed_reviewed"} else \
                 "error" if recorded == "failed" else "waiting" if recorded in {"waiting", "queued"} else "unknown"
        if not available:
            status = "unknown"
        review = normalize_review(task.get("review_state") or task.get("review"))
        if not available:
            review = "unverified"
            reason = "record_unavailable"
        base = {"source": "flightops", "visibility": "assignment_record", "task_id": task.get("id", key),
                "agent": task.get("agent") or task.get("who"), "checker": task.get("checker"),
                "recorded_state": recorded, "review_state": review, "recorded_at": when,
                "source_path": source_path, "stale": stale, "available": available, "reason": reason}
        def node(kind, suffix, label, status="unknown", **extra):
            return {"kind": kind, "run_id": run, "node_id": root_node if not suffix else run + ":" + suffix,
                    "parent_id": root_node if suffix else None, "status": status,
                    **base, "label": label, **extra}
        title = task.get("title")
        if not isinstance(title, str) or not title.strip():
            title = task.get("id") if isinstance(task.get("id"), str) else key
        rows = [node("assignment.recorded", "", title, status)]
        provider = task.get("brain") or task.get("provider") or task.get("who")
        if isinstance(provider, str) or isinstance(task.get("model"), str):
            rows.append(node("assignment.provider", "provider", "Recorded provider allocation",
                             provider=provider, model=task.get("model"), operation="allocation"))
        outputs = task.get("outputs") or task.get("evidence") or []
        if not isinstance(outputs, list):
            outputs = []
        references = []
        for output in outputs[:30]:
            raw = output.get("path") if isinstance(output, dict) else output
            ref = self._reference(raw)
            if ref and ref[0] not in [p for p, _ in references]:
                references.append(ref)
        for path, exists in references:
            suffix = "output:" + hashlib.sha256(path.encode()).hexdigest()[:16]
            rows.append(node("assignment.output", suffix, "Output reference", output_path=path,
                             available=exists, operation="artifact_reference"))
        rows.append(node("assignment.review", "review", "Recorded review state",
                         status="completed" if review in {"accepted", "accepted_with_notes"} else
                                "error" if review == "rejected" else "waiting" if review == "pending" else "unknown",
                         operation="review"))
        return run, rows

    def _collect(self):
        records = {}
        plan_path = "artifacts/handoff/plan.json"
        plan, plan_mtime = self._read(plan_path)
        tasks = plan.get("tasks", []) if plan else []
        if isinstance(tasks, list):
            for task in tasks[:200]:
                if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not ID.fullmatch(task["id"]):
                    continue
                sid = task["id"]
                path = f"artifacts/handoff/{sid}/status.json"
                status, mtime = self._read(path)
                merged = {**task, **(status or {}), "id": sid}
                output = f"artifacts/handoff/{sid}/output.md"
                if not (merged.get("outputs") or merged.get("evidence")) and self._reference(output) == (output, True):
                    merged["outputs"] = [output]
                run, rows = self._task("handoff:" + sid, merged, path, mtime or plan_mtime, status is not None)
                records[run] = rows
        resume_path = "artifacts/handoff/FO-RESUME/tasks.json"
        resume, modified = self._read(resume_path)
        tasks = resume.get("tasks", []) if resume else []
        if isinstance(tasks, list):
            for task in tasks[:100]:
                if isinstance(task, dict) and isinstance(task.get("id"), str) and ID.fullmatch(task["id"]):
                    run, rows = self._task("resume:" + task["id"], task, resume_path, modified)
                    records[run] = rows
        allocation, modified = self._read(ALLOCATION)
        roles = allocation.get("roles", []) if allocation else []
        if isinstance(roles, list):
            for role in roles[:100]:
                if not isinstance(role, dict) or not isinstance(role.get("agent"), str) or not ID.fullmatch(role["agent"]):
                    continue
                task = {"id": role["agent"], "title": "Brain allocation · " + role["agent"],
                        "agent": role["agent"], "provider": role.get("provider"), "model": role.get("model"),
                        "checker": role.get("checker"), "state": "recorded_allocation", "review_state": "unverified",
                        "evidence": [role["evidence"]] if isinstance(role.get("evidence"), str) else []}
                run, rows = self._task("allocation:" + role["agent"], task, ALLOCATION, modified)
                records[run] = rows
        return records

    def scan(self):
        if not self.root:
            return 0
        current = self._collect()
        count = 0
        for run, nodes in current.items():
            previous = self._records.get(run, [])
            if nodes == previous:
                continue
            for node in nodes:
                self.bus.emit(**node)
                count += 1
            retained = {n["node_id"] for n in nodes}
            for old in previous:
                if old["node_id"] not in retained:
                    self._unavailable(old)
                    count += 1
        for run, old_nodes in self._records.items():
            if run not in current:
                for old in old_nodes:
                    self._unavailable(old)
                    count += 1
        self._records = current
        return count

    def _unavailable(self, old):
        data = {**old, "kind": "assignment.unavailable", "status": "unknown", "available": False,
                "reason": "record_unavailable", "review_state": "unverified", "recorded_state": "unavailable"}
        self.bus.emit(**data)

    def start(self):
        if not self.root or self._thread:
            return
        self.scan()
        self._thread = threading.Thread(target=self._loop, name="flightops-assignment-monitor", daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.wait(self.interval):
            self.scan()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
