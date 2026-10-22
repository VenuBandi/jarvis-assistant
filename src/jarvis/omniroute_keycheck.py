"""Check the Jarvis OmniRoute key file and list the models OmniRoute serves (the key is NEVER printed).

  python3 -I src/jarvis/omniroute_keycheck.py [filter]

1. key file ~/.config/jarvis/omniroute_key: exists, mode 600, exactly one non-empty line, no spaces / log text
2. GET http://127.0.0.1:20128/v1/models with the key → model ids (optionally filtered by a substring)
"""
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path

KEY = Path("~/.config/jarvis/omniroute_key").expanduser()
BASE = "http://127.0.0.1:20128"
flt = sys.argv[1].lower() if len(sys.argv) > 1 else ""

if not KEY.exists():
    sys.exit("key file: MISSING")
mode = stat.S_IMODE(KEY.stat().st_mode)
raw = KEY.read_text(errors="replace")
lines = [l for l in raw.splitlines() if l.strip()]
key = lines[0].strip() if lines else ""
problems = []
if mode != 0o600:
    problems.append(f"mode is {oct(mode)}, not 0o600")
if len(lines) != 1:
    problems.append(f"{len(lines)} non-empty lines (expected 1)")
if not key or " " in key or "Loaded env" in raw or "⚠" in raw or "📋" in raw:
    problems.append("content does not look like a single key (log text or spaces present)")
print(f"key file: exists · mode {oct(mode)} · {len(lines)} line(s) · {len(key)} chars · "
      + ("OK" if not problems else "PROBLEM: " + "; ".join(problems)))
if problems:
    sys.exit(1)

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a proxy
req = urllib.request.Request(BASE + "/v1/models", headers={"Authorization": "Bearer " + key})
try:
    with opener.open(req, timeout=10) as r:
        data = json.loads(r.read().decode())
except urllib.error.HTTPError as e:
    sys.exit(f"GET /v1/models → HTTP {e.code} (key rejected?)")
except Exception as e:
    sys.exit(f"GET /v1/models failed: {type(e).__name__}")
finally:
    key = None
ids = sorted(m.get("id", "") for m in data.get("data", []) if isinstance(m, dict))
shown = [i for i in ids if flt in i.lower()]
print(f"GET /v1/models → {len(ids)} models" + (f"; matching '{flt}': {len(shown)}" if flt else ""))
for i in shown[:60]:
    print("  " + i)
