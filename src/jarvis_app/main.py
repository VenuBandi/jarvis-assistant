"""Jarvis FastAPI app (Phase 1). create_app() wires settings → SQLite → models → tools → agent → routes.
Every /api route needs the X-Jarvis-Token header and a loopback Host header (security/guard.py)."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent.orchestrator import Agent
from .config.settings import load_settings
from .database.db import DB
from .models.manager import ModelManager
from .security.guard import host_ok, load_or_create_token, token_ok
from .tools.builtin import register_builtin
from .tools.registry import ToolRegistry
from .workflow.events import EventBus
from .workflow.omniroute import OmniRouteBridge
from .workflow.stream import stream_events
from .workflow.assignments import AssignmentBridge

FRONTEND = Path(__file__).resolve().parent / "frontend"
PERMISSIONS = ["project_read", "settings", "memory_read", "memory_write", "web_search"]
PLANNED = [  # honest integration status: nothing is claimed connected before it is built and validated
    ("local_files", "Phase 3"), ("google_calendar", "Phase 4"), ("gmail", "Phase 4"),
    ("google_drive", "Phase 4"), ("telegram", "Phase 5"), ("invoices", "Phase 5"), ("telephony", "Phase 6"),
    ("screen", "Phase 7"), ("browser", "Phase 7")]


class ChatIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    conv: str = Field("default", pattern=r"^[A-Za-z0-9_-]{1,40}$")


class ConfirmIn(BaseModel):
    id: str = Field(..., pattern=r"^[0-9a-f]{12}$")
    approve: bool


class ModelIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)


class PermIn(BaseModel):
    permission: str
    enabled: bool


def _turn(r):
    return {"reply": r.reply, "model": r.model, "steps": r.steps, "pending": r.pending, "error": r.error}


def create_app(settings=None):
    s = settings or load_settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = DB(s.db_path)
    events = EventBus()
    models = ModelManager(s.providers_file, db, events=events)
    tools = ToolRegistry()
    register_builtin(tools)
    tools.disabled_permissions = set(db.get_setting("disabled_permissions", []))
    agent = Agent(s, db, models, tools, events=events)
    token = load_or_create_token(s.data_dir)
    bridge = OmniRouteBridge(events, s.workflow_omniroute_logs)
    assignments = AssignmentBridge(events, s.workflow_project_root)

    @asynccontextmanager
    async def lifespan(app):
        try:
            bridge.start()
            assignments.start()
            yield
        finally:
            assignments.stop()
            bridge.stop()

    app = FastAPI(title="Jarvis", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.agent, app.state.settings = agent, s
    app.state.workflow_events = events
    app.state.workflow_bridge = bridge
    app.state.workflow_assignments = assignments

    def guard(request: Request, x_jarvis_token: str = Header(default="")):
        if not host_ok(request.headers.get("host", ""), s.allow_remote):
            raise HTTPException(403, "bad host")
        if not token_ok(x_jarvis_token, token):
            raise HTTPException(401, "missing or wrong X-Jarvis-Token")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        if not host_ok(request.headers.get("host", ""), s.allow_remote):
            raise HTTPException(403, "bad host")
        html = (FRONTEND / "index.html").read_text()
        return html.replace("__JARVIS_TOKEN__", token)

    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/workflow", response_class=HTMLResponse)
    def workflow_page(request: Request):
        if not host_ok(request.headers.get("host", ""), s.allow_remote):
            raise HTTPException(403, "bad host")
        page = FRONTEND / "workflow.html"
        if not page.is_file():
            raise HTTPException(503, "Workflow assets are not built yet")
        return HTMLResponse(page.read_text().replace("__JARVIS_TOKEN__", token),
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    @app.get("/api/workflow/snapshot", dependencies=[Depends(guard)])
    def workflow_snapshot():
        return events.snapshot()

    @app.get("/api/workflow/events", dependencies=[Depends(guard)])
    async def workflow_events(request: Request, after: int = Query(0, ge=0),
                              instance_id: str | None = Query(None, max_length=64)):
        return StreamingResponse(stream_events(request, events, after, instance_id),
                                 media_type="text/event-stream", headers={
                                     "Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get("/api/state", dependencies=[Depends(guard)])
    def state():
        key, m = models.current()
        return {"agent_state": agent.state, "active": {"key": key, "label": m.get("label", key),
                                                       "provider": m["provider"], "model": m["model"]},
                "models": [x for x in models.status() if x["key"] != "mock" or key == "mock"],
                "tools": [{"name": t.name, "description": t.description, "read_only": t.read_only,
                           "confirm": t.confirm, "permissions": t.permissions} for t in tools.tools.values()],
                "permissions": {p: p not in tools.disabled_permissions for p in PERMISSIONS},
                "pending": db.open_pending(), "memory_enabled": s.memory_enabled,
                "memory_count": len(db.memories()),
                "integrations": [{"name": "voice", "status": "browser speech (availability depends on browser)"}] +
                                [{"name": n, "status": f"not built yet ({ph})"} for n, ph in PLANNED]}

    @app.get("/api/conversation", dependencies=[Depends(guard)])
    def conversation(conv: str = "default"):
        return [m for m in agent.db.messages(conv, 100)]

    @app.post("/api/chat", dependencies=[Depends(guard)])
    def chat(body: ChatIn):
        with events.run(action="Chat", source="jarvis") as run:
            result = agent.handle(body.conv, body.text)
            run.finish(status="waiting" if result.pending else "error" if result.error else
                       "stopped" if result.reply == "Stopped." else "completed")
            return _turn(result)

    @app.post("/api/confirm", dependencies=[Depends(guard)])
    def confirm(body: ConfirmIn):
        with events.run(action="Confirmation", source="jarvis") as run:
            r = agent.confirm(body.id, body.approve)
            run.finish(status="waiting" if r.pending else "error" if r.error else "completed")
            if r.error and not r.reply:
                raise HTTPException(409, r.error)
            return _turn(r)

    @app.post("/api/model", dependencies=[Depends(guard)])
    def switch_model(body: ModelIn):
        with events.run(action="Switch model", source="jarvis") as run:
            result = models.switch(body.name)
            run.finish(status="completed" if result.get("ok") else "error")
            return result

    @app.post("/api/model/validate", dependencies=[Depends(guard)])
    def validate_model(body: ModelIn):
        key = models.resolve(body.name) if body.name not in models.models else body.name
        if not key:
            raise HTTPException(404, "unknown model")
        with events.run(action="Validate model", source="jarvis") as run:
            ok, detail = models.validate(key)
            run.finish(status="completed" if ok else "error")
        return {"key": key, "ok": ok, "detail": detail}

    @app.post("/api/permissions", dependencies=[Depends(guard)])
    def permissions(body: PermIn):
        if body.permission not in PERMISSIONS:
            raise HTTPException(404, "unknown permission")
        (tools.disabled_permissions.discard if body.enabled else tools.disabled_permissions.add)(body.permission)
        db.set_setting("disabled_permissions", sorted(tools.disabled_permissions))
        return {"permissions": {p: p not in tools.disabled_permissions for p in PERMISSIONS}}

    @app.get("/api/audit", dependencies=[Depends(guard)])
    def audit(limit: int = 50):
        return db.audit_log(min(max(limit, 1), 500))

    @app.get("/api/memory", dependencies=[Depends(guard)])
    def memory():
        return db.memories()

    @app.delete("/api/memory/{mid}", dependencies=[Depends(guard)])
    def forget(mid: int):
        with events.run(action="Delete memory", source="jarvis"):
            with events.span("memory", label="Delete memory", operation="delete") as span:
                if not db.delete_memory(mid):
                    span.finish(status="error", error_code="memory_not_found")
                    raise HTTPException(404, "no such memory")
                span.finish(count=1)
        return {"deleted": mid}

    @app.post("/api/stop", dependencies=[Depends(guard)])
    def stop():
        agent.stop()
        events.emit("agent.stop_requested", run_id="session-control", node_id="session-control",
                    status="stopped", label="Stop requested", source="jarvis")
        return {"stopped": True}

    return app
