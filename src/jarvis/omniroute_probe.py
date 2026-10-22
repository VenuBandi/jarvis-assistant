"""Read-only safety probe of a locally running OmniRoute (no keys sent, no POST, never touches /api/acp).

  python3 -I src/jarvis/omniroute_probe.py [port]

Reports only HTTP status codes / reachability:
  1. loopback reachability (127.0.0.1:<port>)
  2. whether the Mac's network address also accepts connections (exposed beyond this Mac?)
  3. whether model listing (/v1/models) answers WITHOUT an API key (auth enforced?)
  4. whether the dashboard root redirects to a login page
Response bodies are never printed (they could contain account details).
"""
import socket
import sys
import urllib.error
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20128


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def get(url):
    opener = urllib.request.build_opener(NoRedirect)
    try:
        r = opener.open(urllib.request.Request(url, method="GET"), timeout=5)
        return r.status, r.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location", "")
    except Exception as e:  # connection refused, timeout ...
        return None, type(e).__name__


def can_connect(host):
    try:
        with socket.create_connection((host, PORT), timeout=3):
            return True
    except OSError:
        return False


def lan_addresses():
    addrs = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    try:  # address of the default route interface (no packet is sent for UDP connect)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))
        addrs.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(a for a in addrs if not a.startswith("127."))


base = f"http://127.0.0.1:{PORT}"
print(f"1. loopback 127.0.0.1:{PORT} reachable: {can_connect('127.0.0.1')}")
lan = lan_addresses()
exposed = {a: can_connect(a) for a in lan}
print(f"2. network addresses {lan or 'none found'} accept connections: {exposed or '-'}"
      + ("  <-- EXPOSED beyond this Mac" if any(exposed.values()) else ""))
st, loc = get(base + "/v1/models")
print(f"3. GET /v1/models without key -> {st} {('(auth NOT enforced!)' if st == 200 else '(auth enforced)' if st in (401, 403) else '')}")
st, loc = get(base + "/")
print(f"4. GET / (dashboard) -> {st} {('redirect to ' + loc) if loc and st and 300 <= st < 400 else ''}")
st, loc = get(base + "/dashboard")
print(f"5. GET /dashboard -> {st} {('redirect to ' + loc + ' (login required)') if loc and st and 300 <= st < 400 else '(page served WITHOUT login?)' if st == 200 else ''}")
