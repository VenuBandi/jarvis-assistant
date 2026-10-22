"""Start Jarvis: python3 src/jarvis_app/run.py   → http://127.0.0.1:8770 (loopback only by default).
Options come from environment variables (see .env.example). --check runs startup checks and exits."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make 'jarvis_app' importable from src/

from jarvis_app.config.settings import load_settings  # noqa: E402


def startup_checks(s):
    from jarvis_app.database.db import DB
    from jarvis_app.models.manager import ModelManager
    db = DB(s.db_path)
    mm = ModelManager(s.providers_file, db)
    key, m = mm.current()
    print(f"data dir: {s.data_dir}")
    print(f"active model: {key} ({m['provider']}: {m['model']})")
    for x in mm.status():
        if x["key"] != "mock":
            print(f"  {x['key']:<13} credential={x['credential']:<12} {x['provider']}:{x['model']}")
    return mm


def main():
    s = load_settings()
    if "--check" in sys.argv:
        mm = startup_checks(s)
        if "--ping" in sys.argv:
            key, _ = mm.current()
            print("ping active:", mm.validate(key))
        return 0
    import uvicorn
    from jarvis_app.main import create_app
    startup_checks(s)
    print(f"Jarvis → http://{s.host}:{s.port}")
    uvicorn.run(create_app(s), host=s.host, port=s.port, log_level=s.log_level.lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
