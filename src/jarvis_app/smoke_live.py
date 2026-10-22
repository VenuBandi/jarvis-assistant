"""Live end-to-end smoke test (real models, no mocks), in-process via TestClient, separate temp data dir.
Usage: python3 src/jarvis_app/smoke_live.py [model-key ...]   (default: local-qwen gemini-flash)
For each model: switch (validates with a ping) → ask 'what time is it' → ask for FlightOps status.
Prints the tool steps and replies so a human can check the answer matches the real tool result."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from jarvis_app.config.settings import Settings  # noqa: E402
from jarvis_app.main import create_app  # noqa: E402

QUESTIONS = ["What time is it right now?", "What is the FlightOps project doing right now? Use the status tool."]


def main(keys):
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(data_dir=Path(tmp))
        app = create_app(s)
        c = TestClient(app)
        h = {"X-Jarvis-Token": (Path(tmp) / "api_token").read_text()}
        for key in keys:
            sw = c.post("/api/model", json={"name": key}, headers=h).json()
            print(f"\n=== {key}: switch ok={sw['ok']} · {sw['message']}")
            if not sw["ok"]:
                continue
            for i, q in enumerate(QUESTIONS):
                r = c.post("/api/chat", json={"text": q, "conv": f"{key.replace('-', '_')}{i}"}, headers=h).json()
                for st in r["steps"]:
                    print(f"  tool {st['tool']} → {st['status']} · {st.get('result_preview', '')[:160]}")
                print(f"  Q: {q}\n  A: {r['reply'][:500]}")
        print("\naudit:", [(a["tool"], a["status"]) for a in c.get("/api/audit", headers=h).json()])


if __name__ == "__main__":
    main(sys.argv[1:] or ["local-qwen", "gemini-flash"])
