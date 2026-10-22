"""Local API protection. The server binds to loopback, and every state-changing request must carry the
per-install token in the X-Jarvis-Token header. A custom header forces a CORS preflight, which this server never
approves, so another website open in the browser cannot drive Jarvis. The Host header must be loopback too
(blocks DNS-rebinding). The token file lives in the data dir with mode 600."""
import hmac
import os
import secrets as pysecrets
from pathlib import Path

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}


def load_or_create_token(data_dir: Path) -> str:
    p = Path(data_dir) / "api_token"
    if p.exists():
        return p.read_text().strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    tok = pysecrets.token_urlsafe(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(tok)
    return tok


def host_ok(host_header: str, allow_remote: bool) -> bool:
    if allow_remote:
        return True
    host = (host_header or "").rsplit(":", 1)[0] if not (host_header or "").startswith("[") else host_header.split("]")[0] + "]"
    return host in LOOPBACK_HOSTS


def token_ok(sent: str, expected: str) -> bool:
    return bool(sent) and hmac.compare_digest(sent, expected)
