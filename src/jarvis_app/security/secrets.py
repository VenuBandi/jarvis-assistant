"""Secret lookup: macOS Keychain (keyring, service "jarvis") → environment variable → mode-600 file.
Values are returned to the caller only; never logged, stored in the DB or sent to the UI. redact() scrubs
anything token-like from text that leaves the process (errors, logs, tool results)."""
import os
import re
import stat
from pathlib import Path

SERVICE = "jarvis"
_TOKEN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{12,}|nvapi-[A-Za-z0-9_\-]{12,}|sk-ant-[A-Za-z0-9_\-]{12,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}|Bearer\s+[A-Za-z0-9._\-]{12,}|"
    r"\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
_known: set = set()


def _remember(v):
    if v and len(v) >= 8:
        _known.add(v)
    return v


def get_secret(keychain_name=None, env_name=None, file_path=None):
    """Returns the secret or None. Never raises on a missing secret."""
    if keychain_name:
        try:
            import keyring  # optional; present on this Mac
            v = keyring.get_password(SERVICE, keychain_name)
            if v:
                return _remember(v.strip())
        except Exception:  # noqa: BLE001 - keyring backend unavailable → fall through
            pass
    if env_name and os.environ.get(env_name):
        return _remember(os.environ[env_name].strip())
    if file_path:
        p = Path(file_path).expanduser()
        try:
            if p.is_file() and stat.S_IMODE(p.stat().st_mode) == 0o600:
                v = p.read_text().strip()
                return _remember(v) if v else None
        except OSError:
            return None
    return None


def secret_status(keychain_name=None, env_name=None, file_path=None):
    """Where a secret would come from, without returning it (for the dashboard)."""
    if keychain_name:
        try:
            import keyring
            if keyring.get_password(SERVICE, keychain_name):
                return "keychain"
        except Exception:  # noqa: BLE001
            pass
    if env_name and os.environ.get(env_name):
        return "env"
    if file_path:
        p = Path(file_path).expanduser()
        if p.is_file():
            return "file" if stat.S_IMODE(p.stat().st_mode) == 0o600 else "file (bad permissions, must be 600)"
    return "missing"


def redact(text):
    s = _TOKEN.sub("[redacted]", str(text))
    for v in _known:
        s = s.replace(v, "[redacted]")
    return s
