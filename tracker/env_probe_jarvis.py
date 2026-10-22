"""Read-only environment probe for the Jarvis app build: Python version, which libraries import, which CLIs exist.
Prints names and versions only (no paths with secrets, no environment values).
Usage: python3 tracker/env_probe_jarvis.py
"""
import importlib
import os
import platform
import shutil
import sys

print("python", sys.version.split()[0], "|", sys.executable)
print("macOS", platform.mac_ver()[0], "| arch", platform.machine())
for mod in ["fastapi", "uvicorn", "starlette", "pydantic", "httpx", "requests", "anthropic", "openai", "jinja2",
            "yaml", "sqlite3", "pyarrow", "duckdb", "psutil", "pypdf", "PyPDF2", "fitz", "docx", "reportlab",
            "playwright", "sounddevice", "pyaudio", "speech_recognition", "whisper", "faster_whisper", "vosk",
            "pvporcupine", "openwakeword", "pyttsx3", "googleapiclient", "google_auth_oauthlib", "telegram",
            "twilio", "keyring", "mss", "PIL", "numpy", "websockets", "multipart", "aiosqlite"]:
    try:
        m = importlib.import_module(mod)
        print(f"  ok   {mod} {getattr(m, '__version__', '')}")
    except Exception as e:  # noqa: BLE001 - probe only
        print(f"  --   {mod} ({type(e).__name__})")
for cli in ["node", "npm", "ollama", "omniroute", "say", "afplay", "ffmpeg", "sox", "whisper", "tailscale", "brew", "git"]:
    print(f"  cli  {cli}: {'yes' if shutil.which(cli) else 'no'}")
print("ANTHROPIC_API_KEY set:", bool(os.environ.get("ANTHROPIC_API_KEY")))
print("OmniRoute key file present:", os.path.exists(os.path.expanduser("~/.config/flightops/omniroute_key")))
