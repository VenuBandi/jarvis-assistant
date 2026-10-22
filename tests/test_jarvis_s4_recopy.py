"""S4 database re-copy (scripts/s4_recopy_db.py) on temporary folders only: never the real FlightOps or Jarvis data,
never port 8770 (the "is Jarvis running" checks are faked)."""
import importlib.util
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("s4_recopy_db", ROOT / "scripts" / "s4_recopy_db.py")
s4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s4)
NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)


def make_db(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as c, c:
        c.execute("CREATE TABLE settings (k TEXT PRIMARY KEY, v TEXT)")
        c.executemany("INSERT INTO settings VALUES (?, ?)", [(f"k{i}", "v") for i in range(rows)])
    os.chmod(path, 0o644)


def snapshot(folder):
    return {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}


class Recopy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.fo, self.ja = self.tmp / "flightops-ai", self.tmp / "jarvis-assistant"
        make_db(self.fo / "data/jarvis_app/jarvis.sqlite", 5)   # old Jarvis kept writing: 5 rows
        make_db(self.ja / "data/jarvis_app/jarvis.sqlite", 3)   # S3 copy: 3 rows
        for f in (self.fo, self.ja):
            (f / "data/jarvis_app/api_token").write_bytes(b"same-token")
        p = [mock.patch.object(s4, "port_listening", return_value=[]),
             mock.patch.object(s4, "open_by", return_value=[])]
        for x in p:
            x.start()
            self.addCleanup(x.stop)

    def rows(self, path):
        with closing(sqlite3.connect(path)) as c:
            return c.execute("SELECT COUNT(*) FROM settings").fetchone()[0]

    def test_dry_run_changes_nothing(self):
        before = snapshot(self.tmp)
        rep = s4.run(self.fo, self.ja, apply=False, now=NOW)
        self.assertEqual(rep["errors"], [])
        self.assertEqual(rep["source_tables"], {"settings": 5})
        self.assertEqual(rep["s3_copy_tables"], {"settings": 3})
        self.assertEqual(snapshot(self.tmp), before)

    def test_apply_copies_and_moves_s3_copy_aside(self):
        fo_before = snapshot(self.fo)
        rep = s4.run(self.fo, self.ja, apply=True, now=NOW)
        self.assertEqual(rep["errors"], [])
        dst = self.ja / "data/jarvis_app/jarvis.sqlite"
        self.assertEqual(self.rows(dst), 5)
        self.assertEqual(rep["integrity"], "ok")
        self.assertEqual(oct(dst.stat().st_mode & 0o777), "0o644")
        aside = self.ja / "data/jarvis_app/s3_copy_backup_20261022T120000Z/jarvis.sqlite"
        self.assertEqual(self.rows(aside), 3)
        self.assertFalse((self.ja / "data/jarvis_app/jarvis.sqlite.part").exists())
        self.assertTrue((self.ja / "data/jarvis_app/S4_RECOPY_REPORT.json").is_file())
        self.assertEqual(snapshot(self.fo), fo_before)   # FlightOps untouched

    def test_refuses_while_jarvis_runs(self):
        before = snapshot(self.tmp)
        with mock.patch.object(s4, "port_listening", return_value=["79449"]):
            rep = s4.run(self.fo, self.ja, apply=True, now=NOW)
        self.assertTrue(any("port 8770" in e for e in rep["errors"]))
        self.assertEqual(snapshot(self.tmp), before)

    def test_refuses_while_database_open(self):
        before = snapshot(self.tmp)
        with mock.patch.object(s4, "open_by", return_value=["123"]):
            rep = s4.run(self.fo, self.ja, apply=True, now=NOW)
        self.assertTrue(any("is open by pid 123" in e for e in rep["errors"]))
        self.assertEqual(snapshot(self.tmp), before)

    def test_refuses_when_token_differs_and_never_prints_it(self):
        (self.fo / "data/jarvis_app/api_token").write_bytes(b"other-token")
        before = snapshot(self.tmp)
        rep = s4.run(self.fo, self.ja, apply=True, now=NOW)
        self.assertTrue(any("api_token differs" in e for e in rep["errors"]))
        self.assertNotIn("other-token", str(rep))
        self.assertNotIn("same-token", str(rep))
        self.assertEqual(snapshot(self.tmp), before)

    def test_refuses_overlapping_folders(self):
        rep = s4.run(self.fo, self.fo / "inner", apply=True, now=NOW)
        self.assertTrue(any("overlap" in e for e in rep["errors"]))


if __name__ == "__main__":
    unittest.main()
