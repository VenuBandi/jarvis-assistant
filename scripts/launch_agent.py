"""J1a: start Jarvis at login and restart it after a crash (macOS LaunchAgent com.jarvis.assistant).

  python3 -I scripts/launch_agent.py            plan: shows the LaunchAgent and the checks, changes nothing
  python3 -I scripts/launch_agent.py install    write the LaunchAgent and start Jarvis through it
  python3 -I scripts/launch_agent.py status     is it loaded, which pid, what listens on 8770
  python3 -I scripts/launch_agent.py remove     stop Jarvis through launchd and move the LaunchAgent aside

Rules
  - install refuses while anything else listens on port 8770 (stop the hand-started Jarvis first: never two copies)
  - runs src/jarvis_app/run.py from this folder with the same Python as today; no extra environment
  - restarts only after a crash (KeepAlive SuccessfulExit=false): a clean stop stays stopped
  - log: data/jarvis_app/jarvis.log (git-ignored); nothing is deleted: remove moves the plist to data/jarvis_app/
  - touches only ~/Library/LaunchAgents/com.jarvis.assistant.plist; never another LaunchAgent
"""
import os
import plistlib
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

JA = Path(__file__).resolve().parents[1]
LABEL = "com.jarvis.assistant"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
PYTHON = "/opt/anaconda3/bin/python3"
PORT = 8770
DOMAIN = f"gui/{os.getuid()}"


def agent(ja=JA, python=PYTHON):
    log = str(ja / "data" / "jarvis_app" / "jarvis.log")
    return {
        "Label": LABEL,
        "ProgramArguments": [python, str(ja / "src" / "jarvis_app" / "run.py")],
        "WorkingDirectory": str(ja),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 5,
        "ProcessType": "Interactive",
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }


def port_pids(port=PORT):
    r = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True)
    return r.stdout.split()


def launchd_pid():
    r = subprocess.run(["launchctl", "print", f"{DOMAIN}/{LABEL}"], capture_output=True, text=True)
    if r.returncode != 0:
        return None, False
    for line in r.stdout.splitlines():
        if line.strip().startswith("pid ="):
            return line.split("=")[1].strip(), True
    return None, True


def wait_port(want_up, seconds=20):
    for _ in range(seconds * 2):
        if bool(port_pids()) == want_up:
            return True
        time.sleep(0.5)
    return False


def plan():
    print(f"LaunchAgent {PLIST} ({'exists' if PLIST.exists() else 'not installed'}):")
    print(plistlib.dumps(agent()).decode())
    pids = port_pids()
    print(f"port {PORT}: {'in use by pid ' + ', '.join(pids) if pids else 'free'}")
    if pids and not launchd_pid()[1]:
        print("install would refuse: stop the hand-started Jarvis first")
    return 0


def install():
    if not Path(PYTHON).is_file() or not (JA / "src/jarvis_app/run.py").is_file():
        sys.exit("refused: Python or run.py not found")
    if launchd_pid()[1]:
        sys.exit(f"refused: {LABEL} is already loaded (see status)")
    if pids := port_pids():
        sys.exit(f"refused: port {PORT} is in use by pid {', '.join(pids)}; stop that Jarvis first")
    data = plistlib.dumps(agent())
    if PLIST.exists() and PLIST.read_bytes() != data:
        sys.exit(f"refused: {PLIST} exists and differs; run remove first")
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(data)
    os.chmod(PLIST, 0o644)
    lint = subprocess.run(["plutil", "-lint", str(PLIST)], capture_output=True, text=True)
    if lint.returncode != 0:
        sys.exit(f"plutil: {lint.stdout.strip()}")
    r = subprocess.run(["launchctl", "bootstrap", DOMAIN, str(PLIST)], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"launchctl bootstrap failed: {r.stderr.strip()}")
    ok = wait_port(True)
    print(f"installed; Jarvis {'listening on ' + str(PORT) if ok else 'NOT listening after 20 s (see jarvis.log)'}; "
          f"launchd pid {launchd_pid()[0]}")
    return 0 if ok else 1


def status():
    pid, loaded = launchd_pid()
    pids = port_pids()
    print(f"{LABEL}: {'loaded, pid ' + str(pid) if loaded else 'not loaded'}; plist {'present' if PLIST.exists() else 'absent'}")
    print(f"port {PORT}: {'pid ' + ', '.join(pids) if pids else 'free'}"
          + ("" if not pids or pid in pids else "  (NOT the launchd copy)"))
    return 0


def remove():
    if launchd_pid()[1]:
        r = subprocess.run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"launchctl bootout failed: {r.stderr.strip()}")
        wait_port(False)
    if PLIST.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = JA / "data" / "jarvis_app" / f"{LABEL}.plist.removed_{stamp}"
        shutil.move(str(PLIST), str(dest))
        print(f"LaunchAgent moved to {dest}")
    return status()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    actions = {"plan": plan, "install": install, "status": status, "remove": remove}
    if cmd not in actions:
        sys.exit(__doc__)
    sys.exit(actions[cmd]())


if __name__ == "__main__":
    main()
