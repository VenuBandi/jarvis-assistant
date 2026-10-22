"""J1a LaunchAgent script (scripts/launch_agent.py): plist content and refusals. Uses a temporary LaunchAgents folder;
launchctl, lsof and port 8770 are faked (no real LaunchAgent is written or loaded)."""
import importlib.util
import io
import plistlib
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("launch_agent", ROOT / "scripts" / "launch_agent.py")
la = importlib.util.module_from_spec(spec)
spec.loader.exec_module(la)


class LaunchAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.plist = self.tmp / "LaunchAgents" / f"{la.LABEL}.plist"
        self.calls = []
        p = [mock.patch.object(la, "PLIST", self.plist),
             mock.patch.object(la, "port_pids", return_value=[]),
             mock.patch.object(la, "launchd_pid", return_value=(None, False)),
             mock.patch.object(la, "wait_port", return_value=True),
             mock.patch.object(la.subprocess, "run", side_effect=self.fake_run)]
        for x in p:
            x.start()
            self.addCleanup(x.stop)

    def fake_run(self, args, **kw):
        self.calls.append(args)
        return mock.Mock(returncode=0, stdout="", stderr="")

    def test_agent_runs_jarvis_from_this_folder(self):
        a = la.agent()
        self.assertEqual(a["Label"], "com.jarvis.assistant")
        self.assertEqual(a["ProgramArguments"], [la.PYTHON, str(ROOT / "src/jarvis_app/run.py")])
        self.assertEqual(a["WorkingDirectory"], str(ROOT))
        self.assertTrue(a["RunAtLoad"])
        self.assertEqual(a["KeepAlive"], {"SuccessfulExit": False})   # crash → restart; clean stop stays stopped
        self.assertEqual(a["StandardOutPath"], str(ROOT / "data/jarvis_app/jarvis.log"))
        self.assertNotIn("EnvironmentVariables", a)
        self.assertNotIn("flightops", plistlib.dumps(a).decode().lower())

    def test_plan_changes_nothing(self):
        with redirect_stdout(io.StringIO()):
            la.plan()
        self.assertFalse(self.plist.exists())
        self.assertEqual(self.calls, [])

    def test_install_refuses_while_port_in_use(self):
        with mock.patch.object(la, "port_pids", return_value=["28966"]), self.assertRaises(SystemExit) as e:
            la.install()
        self.assertIn("port 8770 is in use by pid 28966", str(e.exception))
        self.assertFalse(self.plist.exists())
        self.assertFalse(any("bootstrap" in c for c in self.calls))

    def test_install_refuses_when_already_loaded(self):
        with mock.patch.object(la, "launchd_pid", return_value=("1", True)), self.assertRaises(SystemExit):
            la.install()
        self.assertFalse(self.plist.exists())

    def test_install_writes_plist_and_bootstraps(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(la.install(), 0)
        self.assertEqual(plistlib.loads(self.plist.read_bytes()), la.agent())
        self.assertEqual(oct(self.plist.stat().st_mode & 0o777), "0o644")
        self.assertIn(["launchctl", "bootstrap", la.DOMAIN, str(self.plist)], self.calls)

    def test_install_refuses_to_overwrite_a_different_plist(self):
        self.plist.parent.mkdir(parents=True)
        self.plist.write_bytes(b"other")
        with self.assertRaises(SystemExit):
            la.install()
        self.assertEqual(self.plist.read_bytes(), b"other")

    def test_remove_moves_plist_aside(self):
        self.plist.parent.mkdir(parents=True)
        self.plist.write_bytes(plistlib.dumps(la.agent()))
        with mock.patch.object(la, "JA", self.tmp), redirect_stdout(io.StringIO()):
            (self.tmp / "data/jarvis_app").mkdir(parents=True)
            la.remove()
        self.assertFalse(self.plist.exists())
        self.assertEqual(len(list((self.tmp / "data/jarvis_app").glob("com.jarvis.assistant.plist.removed_*"))), 1)



class BarAgent(unittest.TestCase):
    """Jarvis Bar's LaunchAgent: same rules, faked launchctl / pgrep, temporary LaunchAgents folder."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.plist = self.tmp / "LaunchAgents" / f"{la.BAR_LABEL}.plist"
        self.bin = self.tmp / "JarvisBar"
        self.bin.write_text("")
        self.calls = []
        p = [mock.patch.object(la, "BAR_PLIST", self.plist), mock.patch.object(la, "BAR_BIN", self.bin),
             mock.patch.object(la, "JA", self.tmp),
             mock.patch.object(la, "bar_pids", return_value=[]),
             mock.patch.object(la, "launchd_pid", return_value=(None, False)),
             mock.patch.object(la, "wait_bar", return_value=True),
             mock.patch.object(la.subprocess, "run", side_effect=self.fake_run)]
        for x in p:
            x.start()
            self.addCleanup(x.stop)

    def fake_run(self, args, **kw):
        self.calls.append(args)
        return mock.Mock(returncode=0, stdout="", stderr="")

    def test_bar_agent(self):
        a = la.bar_agent(ROOT)
        self.assertEqual(a["Label"], "com.jarvis.bar")
        self.assertEqual(a["ProgramArguments"], [str(ROOT / "mac/JarvisBar/build/JarvisBar.app/Contents/MacOS/JarvisBar")])
        self.assertEqual(a["KeepAlive"], {"SuccessfulExit": False})  # Quit Jarvis Bar stays quit
        self.assertEqual(a["LimitLoadToSessionType"], "Aqua")
        self.assertNotIn("EnvironmentVariables", a)

    def test_refuses_while_hand_started_bar_runs(self):
        with mock.patch.object(la, "bar_pids", return_value=["31098"]), self.assertRaises(SystemExit) as e:
            la.bar_install()
        self.assertIn("Jarvis Bar is running (pid 31098)", str(e.exception))
        self.assertFalse(self.plist.exists())

    def test_refuses_when_not_built(self):
        self.bin.unlink()
        with self.assertRaises(SystemExit):
            la.bar_install()
        self.assertFalse(self.plist.exists())

    def test_install_and_remove(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(la.bar_install(), 0)
            self.assertEqual(plistlib.loads(self.plist.read_bytes()), la.bar_agent())
            self.assertIn(["launchctl", "bootstrap", la.DOMAIN, str(self.plist)], self.calls)
            la.bar_remove()
        self.assertFalse(self.plist.exists())
        self.assertEqual(len(list((self.tmp / "data/jarvis_bar").glob("com.jarvis.bar.plist.removed_*"))), 1)

    def test_server_plist_untouched_by_bar_commands(self):
        with mock.patch.object(la, "PLIST", self.tmp / "server.plist"), redirect_stdout(io.StringIO()):
            la.bar_install()
        self.assertFalse((self.tmp / "server.plist").exists())


if __name__ == "__main__":
    unittest.main()
