"""Ping models through the local OmniRoute with a tiny prompt (no project text); the key is never printed.

  python3 -I src/jarvis/omniroute_ping.py <model-id> [<model-id> ...]
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if len(sys.argv) < 2:
    sys.exit(__doc__)
key = Path("~/.config/jarvis/omniroute_key").expanduser().read_text().strip()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for model in sys.argv[1:]:
    if model.startswith(("auto/", "aihorde/", "oc/")) or "free" in model:
        print(f"{model}: SKIPPED (not allowed for project use)")
        continue
    body = json.dumps({"model": model, "max_tokens": 20,
                       "messages": [{"role": "user", "content": "Reply with exactly: OK"}]}).encode()
    req = urllib.request.Request("http://127.0.0.1:20128/v1/chat/completions", data=body, method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    t = time.time()
    try:
        with opener.open(req, timeout=120) as r:
            d = json.loads(r.read().decode())
        txt = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        print(f"{model}: OK {time.time() - t:.1f}s · served by {d.get('model', '?')} · reply {txt.strip()[:40]!r}")
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:160].replace(key, "[key]")
        print(f"{model}: HTTP {e.code} {time.time() - t:.1f}s · {msg}")
    except Exception as e:
        print(f"{model}: FAILED {type(e).__name__} {time.time() - t:.1f}s")
key = None
