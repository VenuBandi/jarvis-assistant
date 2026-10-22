"""Jarvis separation S4: re-copy the Jarvis database from FlightOps after the old Jarvis has stopped.

  python3 -I scripts/s4_recopy_db.py            dry run: checks only, changes nothing
  python3 -I scripts/s4_recopy_db.py --apply    move the S3 copy aside, copy again, verify

Rules
  - refuses while anything listens on port 8770 or has either database file open (the old Jarvis must be stopped)
  - NEVER writes to FlightOps: the source <FLIGHTOPS_ROOT>/data/jarvis_app/jarvis.sqlite is opened read-only
  - checks api_token is byte-identical in both folders before changing anything; content is never printed
  - nothing is deleted: the S3 copy (and any -wal/-shm) is moved to data/jarvis_app/s3_copy_backup_<UTC>/
  - copy with SQLite's backup API into a .part file, then integrity_check + per-table row counts vs the source,
    then rename into place; the source's file mode is kept
  - writes data/jarvis_app/S4_RECOPY_REPORT.json (git-ignored) on --apply
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

JA = Path(__file__).resolve().parents[1]
FO = Path(os.environ.get("FLIGHTOPS_ROOT", "~/flightops-ai")).expanduser().resolve()
PORT = 8770


def port_listening(port=PORT):
    r = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True)
    return r.stdout.split()


def open_by(path):
    if not path.exists():
        return []
    r = subprocess.run(["lsof", "-t", "--", str(path)], capture_output=True, text=True)
    return r.stdout.split()


def table_counts(con):
    names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {n: con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}


def run(fo, ja, apply, now=None):
    src_dir, dst_dir = fo / "data" / "jarvis_app", ja / "data" / "jarvis_app"
    src, dst = src_dir / "jarvis.sqlite", dst_dir / "jarvis.sqlite"
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    rep = {"utc": stamp, "source": str(src), "target": str(dst), "apply": apply, "errors": []}
    err = rep["errors"]

    if fo == ja or fo in ja.parents or ja in fo.parents:
        err.append("refused: Jarvis folder and FlightOps folder overlap")
    if not src.is_file():
        err.append(f"missing source database: {src}")
    if pids := port_listening():
        err.append(f"refused: port {PORT} is still in use (pid {', '.join(pids)}); stop the old Jarvis first")
    for p in (src, dst):
        if pids := open_by(p):
            err.append(f"refused: {p} is open by pid {', '.join(pids)}")
    tokens = [src_dir / "api_token", dst_dir / "api_token"]
    if not all(t.is_file() for t in tokens):
        err.append("api_token missing in one of the folders")
    elif tokens[0].read_bytes() != tokens[1].read_bytes():
        err.append("api_token differs between FlightOps and Jarvis (not copied; Director decides)")
    else:
        rep["api_token"] = "identical"
    if err:
        return rep

    with closing(sqlite3.connect(f"file:{src}?mode=ro", uri=True)) as s:
        rep["source_tables"] = table_counts(s)
    if dst.exists():
        with closing(sqlite3.connect(f"file:{dst}?mode=ro", uri=True)) as d:
            rep["s3_copy_tables"] = table_counts(d)
    rep["source_mtime"] = datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    if not apply:
        return rep

    backup = dst_dir / f"s3_copy_backup_{stamp}"
    backup.mkdir()
    rep["moved_aside"] = []
    for p in (dst, dst.with_name(dst.name + "-wal"), dst.with_name(dst.name + "-shm")):
        if p.exists():
            shutil.move(str(p), str(backup / p.name))
            rep["moved_aside"].append(str(backup / p.name))
    part = dst.with_name(dst.name + ".part")
    with closing(sqlite3.connect(f"file:{src}?mode=ro", uri=True)) as s, closing(sqlite3.connect(part)) as d:
        s.backup(d)
        rep["integrity"] = d.execute("PRAGMA integrity_check").fetchone()[0]
        rep["copy_tables"] = table_counts(d)
    if rep["integrity"] != "ok":
        err.append("integrity_check failed on the new copy (left as .part, S3 copy is in the backup folder)")
    elif rep["copy_tables"] != rep["source_tables"]:
        err.append("row counts differ from the source (left as .part, S3 copy is in the backup folder)")
    else:
        os.chmod(part, src.stat().st_mode & 0o777)
        part.rename(dst)
    (dst_dir / "S4_RECOPY_REPORT.json").write_text(json.dumps(rep, indent=1))
    return rep


def main():
    rep = run(FO, JA, "--apply" in sys.argv)
    print(json.dumps(rep, indent=1))
    sys.exit(1 if rep["errors"] else 0)


if __name__ == "__main__":
    main()
