"""Settings from environment variables (development) with safe defaults. Secrets are NOT read here: see
security/secrets.py. Loopback-only by default; a non-loopback host needs JARVIS_ALLOW_REMOTE=1."""
import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8770
    data_dir: Path = PROJECT_ROOT / "data" / "jarvis_app"
    providers_file: Path = APP_DIR / "config" / "providers.yaml"
    log_level: str = "INFO"
    allow_remote: bool = False
    max_agent_steps: int = 6
    memory_enabled: bool = True
    allowed_dirs: list = field(default_factory=list)
    workflow_omniroute_logs: Path | None = field(default_factory=lambda: Path.home() / ".omniroute" / "call_logs")
    workflow_project_root: Path | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jarvis.sqlite"


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def load_settings(env=None) -> Settings:
    env = os.environ if env is None else env
    s = Settings()
    s.host = env.get("JARVIS_HOST", s.host)
    s.port = int(env.get("JARVIS_PORT", s.port))
    if env.get("JARVIS_DATA_DIR"):
        s.data_dir = Path(env["JARVIS_DATA_DIR"]).expanduser()
    if env.get("JARVIS_PROVIDERS_FILE"):
        s.providers_file = Path(env["JARVIS_PROVIDERS_FILE"]).expanduser()
    s.log_level = env.get("JARVIS_LOG_LEVEL", s.log_level).upper()
    s.allow_remote = env.get("JARVIS_ALLOW_REMOTE") == "1"
    s.memory_enabled = env.get("JARVIS_MEMORY", "on") != "off"
    s.allowed_dirs = [str(Path(p).expanduser()) for p in env.get("JARVIS_ALLOWED_DIRS", "").split(":") if p]
    if env.get("JARVIS_WORKFLOW_OMNIROUTE") == "off":
        s.workflow_omniroute_logs = None
    elif env.get("JARVIS_WORKFLOW_OMNIROUTE_LOG_DIR"):
        s.workflow_omniroute_logs = Path(env["JARVIS_WORKFLOW_OMNIROUTE_LOG_DIR"]).expanduser()
    if env.get("JARVIS_WORKFLOW_ASSIGNMENTS") != "off":
        s.workflow_project_root = Path(env.get("JARVIS_WORKFLOW_PROJECT_ROOT", str(PROJECT_ROOT))).expanduser()
    if not _is_loopback(s.host) and not s.allow_remote:
        raise ValueError(f"JARVIS_HOST={s.host} is not loopback; set JARVIS_ALLOW_REMOTE=1 to allow it on purpose")
    return s
