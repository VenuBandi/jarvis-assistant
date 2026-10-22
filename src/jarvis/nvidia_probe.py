"""NVIDIA build.nvidia.com (direct, not via OmniRoute): key status, model list, tiny ping. The key is read from
~/.config/jarvis/keys/nvidia (mode 600) at call time and never printed; errors are redacted.
Pings send only a fixed one-line prompt (no project text, no data rows).

  python3 -I src/jarvis/nvidia_probe.py status
  python3 -I src/jarvis/nvidia_probe.py models [substring ...]
  python3 -I src/jarvis/nvidia_probe.py ping <model-id> [<model-id> ...]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.jarvis_app.models.adapters import OpenAICompatProvider, _client  # noqa: E402
from src.jarvis_app.models.base import ProviderError  # noqa: E402
from src.jarvis_app.security.secrets import get_secret, redact, secret_status  # noqa: E402

DIRECT = {"nvidia": "https://integrate.api.nvidia.com/v1", "mistral": "https://api.mistral.ai/v1",
          "groq": "https://api.groq.com/openai/v1"}
NAME = sys.argv.pop(1) if len(sys.argv) > 1 and sys.argv[1] in DIRECT else "nvidia"  # e.g. ... nvidia_probe.py mistral models
BASE = DIRECT[NAME]
KEY_FILE = f"~/.config/jarvis/keys/{NAME}"
PROMPT = "Reply with exactly: OK"


def key():
    return get_secret(file_path=KEY_FILE)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    st = secret_status(file_path=KEY_FILE)
    print("key:", st)
    if cmd == "status" or st != "file":
        return
    if cmd == "models":
        try:
            with _client() as c:
                r = c.get(BASE + "/models", headers={"authorization": "Bearer " + key()})
        except Exception as e:  # noqa: BLE001
            sys.exit(redact(f"{type(e).__name__}: {e}"))
        if r.status_code >= 400:
            sys.exit(redact(f"HTTP {r.status_code}: {r.text[:300]}"))
        ids = sorted(m.get("id", "") for m in r.json().get("data", []))
        subs = [s.lower() for s in sys.argv[2:]]
        shown = [i for i in ids if not subs or any(s in i.lower() for s in subs)]
        print(f"{len(ids)} models served; showing {len(shown)}")
        for i in shown:
            print(i)
    elif cmd == "ping":
        p = OpenAICompatProvider(BASE, key)
        for model in sys.argv[2:]:
            t = time.time()
            try:
                res = p.chat(model, "You are a test endpoint.", [{"role": "user", "content": PROMPT}], [])
                print(f"OK   {model}  {time.time() - t:.1f}s  reply={res.text.strip()[:40]!r}")
            except ProviderError as e:
                print(f"FAIL {model}  {time.time() - t:.1f}s  {e}")


if __name__ == "__main__":
    main()
