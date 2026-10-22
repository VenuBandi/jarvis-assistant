"""List OmniRoute's served model ids for the given provider prefixes; the key is never printed.

  python3 -I src/jarvis/omniroute_models.py antigravity openai oc ollama-local
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

prefixes = tuple(p + "/" for p in sys.argv[1:])
key = Path("~/.config/flightops/omniroute_key").expanduser().read_text().strip()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(urllib.request.Request("http://127.0.0.1:20128/v1/models",
                                            headers={"Authorization": "Bearer " + key}), timeout=10) as r:
        data = json.loads(r.read().decode())
except urllib.error.HTTPError as e:
    sys.exit(f"HTTP {e.code}")
finally:
    key = None
for m in sorted(data.get("data", []), key=lambda m: m.get("id", "")):
    if not prefixes or m.get("id", "").startswith(prefixes):
        print(m.get("id"), m.get("owned_by", ""))
