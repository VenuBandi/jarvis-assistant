"""Web search through the local OmniRoute gateway (/v1/search), e.g. the Tavily connection set up in the dashboard.
OmniRoute key read from ~/.config/flightops/omniroute_key at call time, never printed. Sends only the query text.

  python3 -I src/jarvis/omniroute_search.py "<query>" [provider] [max_results]     provider default: tavily-search
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:20128/v1/search"


def search(query, provider="tavily-search", max_results=5):
    key = Path("~/.config/flightops/omniroute_key").expanduser().read_text().strip()
    body = json.dumps({"query": query, "provider": provider, "max_results": int(max_results)}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Authorization": "Bearer " + key,
                                                          "Content-Type": "application/json"})
    key = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    q = sys.argv[1]
    prov = sys.argv[2] if len(sys.argv) > 2 else "tavily-search"
    n = sys.argv[3] if len(sys.argv) > 3 else 5
    try:
        res = search(q, prov, n)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")
    items = res.get("results") or res.get("data") or []
    for i, it in enumerate(items, 1):
        print(f"{i}. {it.get('title', '')}\n   {it.get('url', '')}\n   {str(it.get('content') or it.get('snippet') or '')[:160]}")
    print("keys:", sorted(res.keys()), "| results:", len(items))


if __name__ == "__main__":
    main()
