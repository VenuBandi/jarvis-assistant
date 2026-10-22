"""Start Jarvis at login and restart it after a crash: macOS LaunchAgents for the server (J1a,
com.jarvis.assistant) and the menu-bar app Jarvis Bar (J1b, com.jarvis.bar).

  python3 -I scripts/launch_agent.py [plan|install|status|remove] [server|bar]     default: plan server
    plan     shows the LaunchAgent and the checks, changes nothing
    install  write the LaunchAgent and start the program through it
    status   is it loaded, which pid (server: what listens on 8770)
    remove   stop the program through launchd and move the LaunchAgent aside

Rules
  - install refuses while another copy runs (server: anything on port 8770; bar: a Jarvis Bar started by hand):
    never two copies
  - server: src/jarvis_app/run.py from this folder with the same Python as today; bar: the app built by
    scripts/build_jarvis_bar.sh. No extra environment
  - restarts only after a crash (KeepAlive SuccessfulExit=false): a clean stop (or Quit Jarvis Bar) stays stopped
  - logs in data/ (git-ignored); nothing is deleted: remove moves the plist to data/
  - touches only the two plists below in ~/Library/LaunchAgents; never another LaunchAgent
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
BAR_LABEL = "com.jarvis.bar"
BAR_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{BAR_LABEL}.plist"
BAR_BIN = JA / "mac" / "JarvisBar" / "build" / "JarvisBar.app" / "Contents" / "MacOS" / "JarvisBar"
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


def bar_agent(ja=JA):
    log = str(ja / "data" / "jarvis_bar" / "jarvis_bar.log")
    return {
        "Label": BAR_LABEL,
        "ProgramArguments": [str(ja / "mac" / "JarvisBar" / "build" / "JarvisBar.app" / "Contents" / "MacOS" / "JarvisBar")],
        "WorkingDirectory": str(ja),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 5,
        "ProcessType": "Interactive",
        "LimitLoadToSessionType": "Aqua",
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }


def bar_pids():
    r = subprocess.run(["pgrep", "-f", str(BAR_BIN)], capture_output=True, text=True)
    return r.stdout.split()


def wait_bar(want_up, seconds=20):
    for _ in range(seconds * 2):
        if bool(bar_pids()) == want_up:
            return True
        time.sleep(0.5)
    return False


def port_pids(port=PORT):
    r = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True)
    return r.stdout.split()


def launchd_pid(label=LABEL):
    r = subprocess.run(["launchctl", "print", f"{DOMAIN}/{label}"], capture_output=True, text=True)
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


def bar_plan():
    print(f"LaunchAgent {BAR_PLIST} ({'exists' if BAR_PLIST.exists() else 'not installed'}):")
    print(plistlib.dumps(bar_agent()).decode())
    pids = bar_pids()
    print(f"Jarvis Bar: {'running, pid ' + ', '.join(pids) if pids else 'not running'}")
    if pids and not launchd_pid(BAR_LABEL)[1]:
        print("install would refuse: quit the Jarvis Bar started by hand first")
    return 0


def bar_install():
    if not BAR_BIN.is_file():
        sys.exit("refused: Jarvis Bar not built (sh scripts/build_jarvis_bar.sh)")
    if launchd_pid(BAR_LABEL)[1]:
        sys.exit(f"refused: {BAR_LABEL} is already loaded (see status)")
    if pids := bar_pids():
        sys.exit(f"refused: Jarvis Bar is running (pid {', '.join(pids)}); quit it first")
    data = plistlib.dumps(bar_agent())
    if BAR_PLIST.exists() and BAR_PLIST.read_bytes() != data:
        sys.exit(f"refused: {BAR_PLIST} exists and differs; run remove first")
    (JA / "data" / "jarvis_bar").mkdir(parents=True, exist_ok=True)
    BAR_PLIST.parent.mkdir(parents=True, exist_ok=True)
    BAR_PLIST.write_bytes(data)
    os.chmod(BAR_PLIST, 0o644)
    lint = subprocess.run(["plutil", "-lint", str(BAR_PLIST)], capture_output=True, text=True)
    if lint.returncode != 0:
        sys.exit(f"plutil: {lint.stdout.strip()}")
    r = subprocess.run(["launchctl", "bootstrap", DOMAIN, str(BAR_PLIST)], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"launchctl bootstrap failed: {r.stderr.strip()}")
    ok = wait_bar(True)
    print(f"installed; Jarvis Bar {'running' if ok else 'NOT running after 20 s (see jarvis_bar.log)'}; "
          f"launchd pid {launchd_pid(BAR_LABEL)[0]}")
    return 0 if ok else 1


def bar_status():
    pid, loaded = launchd_pid(BAR_LABEL)
    pids = bar_pids()
    print(f"{BAR_LABEL}: {'loaded, pid ' + str(pid) if loaded else 'not loaded'}; "
          f"plist {'present' if BAR_PLIST.exists() else 'absent'}")
    print(f"Jarvis Bar: {'pid ' + ', '.join(pids) if pids else 'not running'}"
          + ("" if not pids or pid in pids else "  (NOT the launchd copy)"))
    return 0


def bar_remove():
    if launchd_pid(BAR_LABEL)[1]:
        r = subprocess.run(["launchctl", "bootout", f"{DOMAIN}/{BAR_LABEL}"], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"launchctl bootout failed: {r.stderr.strip()}")
        wait_bar(False)
    if BAR_PLIST.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = JA / "data" / "jarvis_bar" / f"{BAR_LABEL}.plist.removed_{stamp}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(BAR_PLIST), str(dest))
        print(f"LaunchAgent moved to {dest}")
    return bar_status()


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "plan"
    target = args[1] if len(args) > 1 else "server"
    actions = {"server": {"plan": plan, "install": install, "status": status, "remove": remove},
               "bar": {"plan": bar_plan, "install": bar_install, "status": bar_status, "remove": bar_remove}}
    if target not in actions or cmd not in actions[target]:
        sys.exit(__doc__)
    sys.exit(actions[target][cmd]())


if __name__ == "__main__":
    main()
