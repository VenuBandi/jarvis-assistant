"""Tavily web search (REST API, no CLI / skills install). Key read at call time from
~/.config/jarvis/keys/tavily (mode 600), never printed; errors redacted. Sends only the query text given.

  python3 -I src/jarvis/tavily_search.py status
  python3 -I src/jarvis/tavily_search.py search "<query>" [max_results] [domain,domain...]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.jarvis_app.models.adapters import _client  # noqa: E402
from src.jarvis_app.security.secrets import get_secret, redact, secret_status  # noqa: E402

URL = "https://api.tavily.com/search"
KEY_FILE = "~/.config/jarvis/keys/tavily"


def search(query, max_results=5, domains=None):
    key = get_secret(file_path=KEY_FILE)
    if not key:
        raise RuntimeError("no Tavily key (" + secret_status(file_path=KEY_FILE) + ")")
    body = {"query": query, "max_results": int(max_results), "search_depth": "basic"}
    if domains:
        body["include_domains"] = domains
    try:
        with _client() as c:
            r = c.post(URL, headers={"authorization": "Bearer " + key, "content-type": "application/json"}, json=body)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(redact(f"{type(e).__name__}: {e}")) from None
    if r.status_code >= 400:
        raise RuntimeError(redact(f"HTTP {r.status_code}: {r.text[:300]}"))
    return r.json()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    print("key:", secret_status(file_path=KEY_FILE))
    if cmd != "search":
        return
    q = sys.argv[2]
    n = sys.argv[3] if len(sys.argv) > 3 else 5
    doms = sys.argv[4].split(",") if len(sys.argv) > 4 else None
    try:
        res = search(q, n, doms)
    except RuntimeError as e:
        sys.exit(str(e))
    for i, item in enumerate(res.get("results", []), 1):
        print(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}\n   {str(item.get('content', ''))[:200]}")
    print(json.dumps({"results": len(res.get("results", [])), "response_time": res.get("response_time")}))


if __name__ == "__main__":
    main()
