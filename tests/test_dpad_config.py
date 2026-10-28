import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from tv_common import Adb

PREFS = "shared_prefs/dpadtv_native.xml"
LOCAL = "http://127.0.0.1:17919"


def xml_preferences(server="https://old.example", history='[{"title":"旧记录"}]'):
    root = ET.Element("map")
    values = {"history": history, "sources": '[{"name":"自选源","url":"https://source.example/api"}]',
              "password": "fixture-secret-'\"$()&<中文", "cookie": "fixture-cookie", "pos:42": "4321"}
    if server is not None:
        values["server_url"] = server
    for name, value in values.items():
        ET.SubElement(root, "string", name=name).text = value
    ET.SubElement(root, "boolean", name="filter_adult", value="true")
    return ET.tostring(root, encoding="unicode")


def entries(xml):
    return {e.get("name"): (e.tag, tuple(sorted(e.attrib.items())), e.text) for e in ET.fromstring(xml)}


class DpadConfigWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fake = self.root / "fake-adb"
        shutil.copyfile(Path(__file__).with_name("fake_adb.py"), self.fake)
        self.fake.chmod(0o700)
        self.path = self.root / "fixture.json"
        self.record = self.root / "server-record.json"
        self.original = xml_preferences()
        self.write({"props": {"ro.product.model": "FixtureTV", "ro.build.version.sdk": "28",
                              "ro.build.fingerprint": "fixture/1", "ro.serialno": "fixture-hardware"},
                    "settings": {"secure": {"android_id": "fixture-id"}}, "trace": [],
                    "preference_files": {PREFS: self.original}})
        self.env = dict(os.environ, TV_SKILL_FAKE_STATE=str(self.path))

    def write(self, state):
        self.path.write_text(json.dumps(state))

    def read(self):
        return json.loads(self.path.read_text())

    def prefs(self):
        return self.read()["preference_files"][PREFS]

    def cli(self, command, *args, expected=0):
        result = subprocess.run([sys.executable, str(SCRIPTS / "tv_dpad_config.py"), command,
                                 "--serial", "tv-fixture", "--adb", str(self.fake), *map(str, args)],
                                env=self.env, capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn("fixture-secret", result.stdout + result.stderr)
        self.assertNotIn("fixture-cookie", result.stdout + result.stderr)
        return result

    def switch(self, expected=0):
        return self.cli("set-server", "--url", LOCAL, "--record", self.record, expected=expected)

    def restore(self, expected=0):
        return self.cli("restore-server", "--record", self.record, expected=expected)

    def replacements(self):
        return [c for c in self.read()["trace"] if c[:3] == ["run-as", "com.dpadtv.client", "mv"]]

    def test_backup_is_readonly_private_and_complete(self):
        output = self.root / "backup.json"
        self.cli("backup", "--output", output)
        self.assertEqual(json.loads(output.read_text())["preferences_xml"], self.original)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.prefs(), self.original)
        self.assertNotIn(["am", "force-stop", "com.dpadtv.client"], self.read()["trace"])
        self.assertFalse(self.replacements())

    def test_switch_preserves_unicode_credentials_types_and_all_other_keys(self):
        self.switch()
        before, after = entries(self.original), entries(self.prefs())
        self.assertEqual(after.pop("server_url")[2], LOCAL)
        before.pop("server_url")
        self.assertEqual(after, before)
        record = json.loads(self.record.read_text())
        self.assertEqual(record["state"], "applied")
        self.assertEqual(record["preferences_before_xml"], self.original)
        self.assertEqual(self.record.stat().st_mode & 0o777, 0o600)
        self.assertEqual(set(self.read()["preference_files"]), {PREFS})

    def test_restore_changes_only_server_and_keeps_new_history_and_progress(self):
        self.switch()
        state = self.read()
        state["preference_files"][PREFS] = xml_preferences(LOCAL, '[{"title":"旧记录"},{"title":"新增记录"}]')
        root = ET.fromstring(state["preference_files"][PREFS])
        ET.SubElement(root, "long", name="pos:99", value="98765")
        latest = ET.tostring(root, encoding="unicode")
        state["preference_files"][PREFS] = latest
        self.write(state)
        self.restore()
        before, after = entries(latest), entries(self.prefs())
        self.assertEqual(after.pop("server_url")[2], "https://old.example")
        before.pop("server_url")
        self.assertEqual(after, before)
        self.assertEqual(json.loads(self.record.read_text())["state"], "restored")

    def test_later_server_change_blocks_restore_without_file_write(self):
        self.switch()
        state = self.read()
        state["preference_files"][PREFS] = xml_preferences("https://new-choice.example")
        self.write(state)
        count = len(self.replacements())
        self.restore(expected=2)
        self.assertEqual(len(self.replacements()), count)
        self.assertEqual(entries(self.prefs())["server_url"][2], "https://new-choice.example")

    def test_probe_truncation_never_replaces_original_and_keeps_recovery_record(self):
        state = self.read()
        state["truncate_probe"] = True
        self.write(state)
        self.switch(expected=2)
        self.assertEqual(self.prefs(), self.original)
        self.assertFalse(self.replacements())
        self.assertEqual(json.loads(self.record.read_text())["state"], "uncertain")
        self.assertEqual(set(self.read()["preference_files"]), {PREFS})

    def test_transport_loss_after_rename_can_restore_from_uncertain_record(self):
        state = self.read()
        state["fail_after_preference_move"] = True
        self.write(state)
        self.switch(expected=2)
        self.assertEqual(entries(self.prefs())["server_url"][2], LOCAL)
        self.assertEqual(json.loads(self.record.read_text())["state"], "uncertain")
        state = self.read()
        state.pop("fail_after_preference_move")
        self.write(state)
        self.restore()
        self.assertEqual(entries(self.prefs()), entries(self.original))

    def test_restore_refuses_different_device(self):
        self.switch()
        state = self.read()
        state["props"]["ro.serialno"] = "another-device"
        self.write(state)
        count = len(self.replacements())
        self.restore(expected=2)
        self.assertEqual(len(self.replacements()), count)

    def test_nondebuggable_client_is_not_stopped_or_modified(self):
        state = self.read()
        state["dpad_debuggable"] = False
        self.write(state)
        self.switch(expected=2)
        self.assertEqual(self.prefs(), self.original)
        self.assertFalse(self.record.exists())
        self.assertNotIn(["am", "force-stop", "com.dpadtv.client"], self.read()["trace"])

    def test_active_playback_is_not_interrupted(self):
        state = self.read()
        state["foreground"] = "com.dpadtv.client/.PlayerActivity"
        self.write(state)
        self.switch(expected=2)
        self.assertNotIn(["am", "force-stop", "com.dpadtv.client"], self.read()["trace"])
        self.assertFalse(self.replacements())

    def test_missing_original_server_restores_absence(self):
        state = self.read()
        state["preference_files"][PREFS] = xml_preferences(None)
        self.write(state)
        self.switch()
        self.restore()
        self.assertNotIn("server_url", entries(self.prefs()))

    def test_existing_record_is_not_overwritten(self):
        self.record.write_text("keep this record")
        self.switch(expected=2)
        self.assertEqual(self.record.read_text(), "keep this record")
        self.assertFalse(self.replacements())

    def test_credential_or_invalid_server_urls_are_rejected_before_device_actions(self):
        for url in ["file:///tmp/private", "https://user:secret@example.org", "https://example.org/#token", "https://example.org/?token=secret", "http://example.org:bad", "http://exa\nmple.org"]:
            with self.subTest(url=url):
                self.cli("set-server", "--url", url, "--record", self.record, expected=2)
                self.assertEqual(self.read()["trace"], [])
        self.assertFalse(self.record.exists())

    def test_invalid_xml_is_not_replaced(self):
        state = self.read()
        state["preference_files"][PREFS] = "not XML"
        self.write(state)
        self.switch(expected=2)
        self.assertEqual(self.prefs(), "not XML")
        self.assertFalse(self.replacements())

    def test_nonutf8_log_output_does_not_abort_text_diagnostics(self):
        with mock.patch.dict(os.environ, self.env):
            output = Adb("tv-fixture", str(self.fake)).shell("invalid-utf8-log")
        self.assertEqual(output, "log\ufffdline")


if __name__ == "__main__":
    unittest.main()
