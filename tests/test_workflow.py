import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from tv_idle_verify import assess, parse_sample


class OfflineWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fake = self.root / "adb-fixture"
        shutil.copyfile(Path(__file__).with_name("fake_adb.py"), self.fake)
        self.fake.chmod(0o700)
        self.state_path = self.root / "device.json"
        self.state = {
            "props": {"ro.product.manufacturer": "Fixture", "ro.product.model": "FixtureTV",
                      "ro.build.version.sdk": "28", "ro.build.fingerprint": "fixture/build/1",
                      "ro.build.version.incremental": "fixture-1", "ro.product.cpu.abi": "armeabi-v7a",
                      "ro.serialno": "fixture-hardware"},
            "settings": {"system": {"screen_saver_timeout": "480000", "boot_ad_sound_enable": "1"},
                         "secure": {"android_id": "fixture-android-id",
                                    "enabled_accessibility_services": "com.factory.voice/.Service"},
                         "global": {}},
            "trace": [],
        }
        self.write_state(self.state)
        self.env = dict(os.environ, TV_SKILL_FAKE_STATE=str(self.state_path))

    def write_state(self, state):
        self.state_path.write_text(json.dumps(state))

    def read_state(self):
        return json.loads(self.state_path.read_text())

    def run_cli(self, script, *args, expected=0):
        result = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args),
                                 "--serial", "tv-fixture", "--adb", str(self.fake)],
                                capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def plan(self, *changes):
        args = ["plan", "--output", self.root / "plan.json"]
        for change in changes or ("system:screen_saver_timeout=-1",):
            args.extend(["--change", change])
        self.run_cli("tv_settings.py", *args)
        return self.root / "plan.json"

    def apply(self, expected=0):
        self.run_cli("tv_settings.py", "apply", "--plan", self.root / "plan.json",
                     "--record", self.root / "record.json", expected=expected)

    def restore(self, expected=0):
        self.run_cli("tv_settings.py", "restore", "--record", self.root / "record.json", expected=expected)

    def writes(self):
        return [c for c in self.read_state()["trace"] if c[:2] in
                (["settings", "put"], ["settings", "delete"])]

    def test_plan_is_read_only_and_preserves_function_services(self):
        self.plan()
        self.assertFalse(self.writes())
        self.apply()
        self.assertEqual(self.read_state()["settings"]["secure"], self.state["settings"]["secure"])
        self.restore()
        self.assertEqual(self.read_state()["settings"], self.state["settings"])

    def test_absent_value_restores_by_delete(self):
        self.plan("system:boot_ad_switch=0")
        self.apply()
        self.restore()
        self.assertNotIn("boot_ad_switch", self.read_state()["settings"]["system"])
        self.assertIn(["settings", "delete", "system", "boot_ad_switch"], self.writes())

    def test_literal_null_is_not_treated_as_absence(self):
        self.state["settings"]["system"]["boot_ad_switch"] = "null"
        self.write_state(self.state)
        self.plan("system:boot_ad_switch=0")
        self.apply()
        self.restore()
        self.assertEqual(self.read_state()["settings"]["system"]["boot_ad_switch"], "null")

    def test_device_identity_mismatch_refuses_all_writes(self):
        self.plan()
        current = self.read_state()
        current["props"]["ro.serialno"] = "another-fixture"
        self.write_state(current)
        self.apply(expected=2)
        self.assertFalse(self.writes())

    def test_stale_later_entry_blocks_whole_apply(self):
        self.plan("system:screen_saver_timeout=-1", "system:boot_ad_sound_enable=0")
        current = self.read_state()
        current["settings"]["system"]["boot_ad_sound_enable"] = "0"
        self.write_state(current)
        self.apply(expected=2)
        self.assertFalse(self.writes())

    def test_ambiguous_write_record_restores_attempted_entry_only(self):
        self.plan("system:screen_saver_timeout=-1", "system:boot_ad_switch=0")
        current = self.read_state()
        current["fail_after_write"] = "screen_saver_timeout"
        self.write_state(current)
        self.apply(expected=2)
        record = json.loads((self.root / "record.json").read_text())
        self.assertEqual([c["status"] for c in record["changes"]], ["uncertain", "pending"])
        self.assertEqual(self.read_state()["settings"]["system"]["screen_saver_timeout"], "-1")
        current = self.read_state()
        current.pop("fail_after_write")
        self.write_state(current)
        self.restore()
        self.assertEqual(self.read_state()["settings"], self.state["settings"])
        self.assertFalse(any(c[3] == "boot_ad_switch" for c in self.writes()))

    def test_restore_conflict_does_not_overwrite_new_user_value(self):
        self.plan("system:screen_saver_timeout=-1", "system:boot_ad_switch=0")
        self.apply()
        count = len(self.writes())
        current = self.read_state()
        current["settings"]["system"]["screen_saver_timeout"] = "300000"
        self.write_state(current)
        self.restore(expected=2)
        self.assertEqual(len(self.writes()), count)
        self.assertEqual(self.read_state()["settings"]["system"]["boot_ad_switch"], "0")

    def test_existing_record_is_never_overwritten_by_new_apply(self):
        self.plan()
        record = self.root / "record.json"
        record.write_text("retain this original")
        self.apply(expected=2)
        self.assertFalse(self.writes())
        self.assertEqual(record.read_text(), "retain this original")

    def test_unauthorized_device_cannot_plan(self):
        self.state["connection"] = "unauthorized"
        self.write_state(self.state)
        self.run_cli("tv_settings.py", "plan", "--change", "system:boot_ad_switch=0",
                     "--output", self.root / "plan.json", expected=2)
        self.assertFalse((self.root / "plan.json").exists())
        self.assertFalse(self.writes())

    def test_runtime_ad_state_is_not_a_supported_switch(self):
        self.run_cli("tv_settings.py", "plan", "--change", "system:boot_ad=0",
                     "--output", self.root / "plan.json", expected=2)
        self.assertFalse(self.writes())

    def test_snapshot_uses_only_read_commands(self):
        path = self.root / "baseline.json"
        self.run_cli("tv_snapshot.py", "--output", path)
        data = json.loads(path.read_text())
        self.assertTrue(data["complete"])
        self.assertEqual(data["settings"]["system"]["boot_ad_switch"], {"present": False, "value": None})
        self.assertFalse(self.writes())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_ui_exit_zero_error_never_reuses_stale_xml(self):
        self.state["remote"] = {"/sdcard/window.xml": '<hierarchy><node package="com.leslie.tvhome" /></hierarchy>'}
        self.write_state(self.state)
        directory = self.root / "capture"
        self.run_cli("tv_ui_capture.py", "--output", directory,
                     "--expect-package", "com.leslie.tvhome", expected=2)
        result = json.loads((directory / "capture.json").read_text())
        self.assertFalse(result["xml_valid"])
        self.assertTrue(result["screenshot_valid"])
        self.assertFalse((directory / "ui.xml").exists())
        self.assertIn("/sdcard/window.xml", self.read_state()["remote"])

    def test_ui_fresh_expected_package_and_cleanup(self):
        self.state["dump_ok"] = True
        self.write_state(self.state)
        directory = self.root / "capture"
        self.run_cli("tv_ui_capture.py", "--output", directory, "--expect-package", "com.leslie.tvhome")
        self.assertIn("com.leslie.tvhome", (directory / "ui.xml").read_text())
        self.assertEqual(self.read_state().get("remote"), {})

    def test_ui_unexpected_package_is_not_accepted(self):
        self.state.update(dump_ok=True, ui_package="com.factory.home")
        self.write_state(self.state)
        self.run_cli("tv_ui_capture.py", "--output", self.root / "capture",
                     "--expect-package", "com.leslie.tvhome", expected=2)
        self.assertFalse((self.root / "capture" / "ui.xml").exists())

    def test_idle_short_window_cannot_pass_and_sends_no_input(self):
        directory = self.root / "idle"
        self.run_cli("tv_idle_verify.py", "--output", directory, "--duration", "0.5", "--interval", "0.2",
                     "--baseline-timeout-ms", "480000", "--expect-activity",
                     "com.leslie.tvhome/.HomeActivity", expected=2)
        result = json.loads((directory / "result.json").read_text())
        self.assertFalse(result["idle_ad_path_not_observed"])
        self.assertTrue(result["checks"]["live_log_stream_survived"])
        self.assertFalse(any(c[:1] in (["input"], ["svc"], ["am"]) for c in self.read_state()["trace"]))

    def test_idle_log_exit_invalidates_observation(self):
        self.state["log_exit"] = True
        self.write_state(self.state)
        directory = self.root / "idle"
        self.run_cli("tv_idle_verify.py", "--output", directory, "--duration", "0.5", "--interval", "0.2",
                     "--baseline-timeout-ms", "480000", "--expect-activity",
                     "com.leslie.tvhome/.HomeActivity", expected=2)
        result = json.loads((directory / "result.json").read_text())
        self.assertFalse(result["checks"]["live_log_stream_survived"])
        self.assertFalse(result["idle_ad_path_not_observed"])

    def test_idle_refuses_unbounded_duration(self):
        for duration in ("nan", "inf", "-1"):
            with self.subTest(duration=duration):
                self.run_cli("tv_idle_verify.py", "--output", self.root / "idle", "--duration", duration,
                             "--baseline-timeout-ms", "480000", "--expect-activity",
                             "com.leslie.tvhome/.HomeActivity", expected=2)
        self.assertFalse((self.root / "idle").exists())


class IdleAssessment(unittest.TestCase):
    def samples(self):
        parsed = parse_sample("mResumedActivity: ActivityRecord{abc u0 com.leslie.tvhome/.HomeActivity t1}",
                              "mWakefulness=Awake\nmLastUserActivityTime=100", "MemAvailable: 1000 kB", "1000.0 0")
        first = dict(parsed, elapsed_seconds=0)
        last = dict(copy.deepcopy(parsed), elapsed_seconds=620, uptime_seconds=1620)
        return [first, last]

    def result(self, samples, alive=True, matches=None, errors=None):
        return assess(samples, "com.leslie.tvhome/.HomeActivity", 480000, alive, 50, matches or [], errors or [])

    def test_complete_qualified_window_can_pass(self):
        self.assertTrue(self.result(self.samples())["idle_ad_path_not_observed"])

    def test_input_unknown_activity_sleep_reboot_or_stream_loss_cannot_pass(self):
        variants = [("user_activity", {"mLastUserActivityTime": 101}), ("user_activity", {}),
                    ("foreground", None), ("wakefulness", "Asleep"), ("uptime_seconds", 10)]
        for field, value in variants:
            with self.subTest(field=field, value=value):
                samples = self.samples()
                samples[-1][field] = value
                self.assertFalse(self.result(samples)["idle_ad_path_not_observed"])
        self.assertFalse(self.result(self.samples(), alive=False)["idle_ad_path_not_observed"])

    def test_ad_request_or_collection_error_requires_review(self):
        self.assertFalse(self.result(self.samples(), matches=[{"line": "requestStreamAd"}])["idle_ad_path_not_observed"])
        self.assertFalse(self.result(self.samples(), errors=["transport lost"])["idle_ad_path_not_observed"])


if __name__ == "__main__":
    unittest.main()
