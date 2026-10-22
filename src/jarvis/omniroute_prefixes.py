"""Count OmniRoute's served models by provider prefix (the part before the first '/'); the key is never printed.

  python3 -I src/jarvis/omniroute_prefixes.py
"""
import collections
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

key = Path("~/.config/jarvis/omniroute_key").expanduser().read_text().strip()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(urllib.request.Request("http://127.0.0.1:20128/v1/models",
                                            headers={"Authorization": "Bearer " + key}), timeout=10) as r:
        data = json.loads(r.read().decode())
except urllib.error.HTTPError as e:
    sys.exit(f"HTTP {e.code}")
finally:
    key = None
c = collections.Counter(m.get("id", "").split("/")[0] if "/" in m.get("id", "") else "(no prefix)" for m in data.get("data", []))
for p, n in c.most_common():
    print(f"{n:4d}  {p}")
