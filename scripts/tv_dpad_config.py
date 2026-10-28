#!/usr/bin/env python3
"""Back up DpadTV preferences; change or restore only its server URL."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import shlex
import sys
from urllib.parse import urlsplit
import uuid
import xml.etree.ElementTree as ET

from tv_common import Adb, TVError, add_adb_arguments, load_json, now, save_json

PACKAGE = "com.dpadtv.client"
PREFERENCES = "shared_prefs/dpadtv_native.xml"


def parse_preferences(data: bytes) -> ET.Element:
    try:
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("too large")
        root = ET.fromstring(data)
        names = [e.get("name") for e in root]
        if root.tag != "map" or None in names or len(set(names)) != len(names):
            raise ValueError("invalid map")
        server_state(root)
        return root
    except (ET.ParseError, ValueError) as exc:
        raise TVError("Invalid preference XML; keep the backup and use the client UI") from exc


def server_state(root: ET.Element) -> dict:
    for item in root:
        if item.get("name") == "server_url":
            if item.tag != "string" or len(item):
                raise ValueError("server_url is not a string")
            return {"present": True, "value": item.text or ""}
    return {"present": False, "value": None}


def changed_preferences(data: bytes, server: dict) -> bytes:
    root = parse_preferences(data)
    for item in list(root):
        if item.get("name") == "server_url":
            root.remove(item)
    if server["present"]:
        ET.SubElement(root, "string", name="server_url").text = server["value"]
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_url(url: str) -> str:
    if not isinstance(url, str):
        raise TVError("Expected a server URL string")
    url = url.strip().rstrip("/")
    try:
        value = urlsplit(url)
        if (value.scheme not in {"http", "https"} or not value.hostname
                or value.username is not None or value.password is not None
                or value.query or value.fragment or any(c.isspace() for c in url)):
            raise ValueError("unsupported URL")
        value.port
    except ValueError as exc:
        raise TVError("Use an HTTP(S) server URL without credentials, query or fragment") from exc
    return url


def check_access(adb: Adb) -> None:
    info = adb.shell("dumpsys", "package", PACKAGE)
    if not re.search(r"\bDEBUGGABLE\b", info):
        raise TVError("This installed DpadTV is not proven debuggable; use its settings UI")
    adb.shell_bytes("run-as", PACKAGE, "id")


def read_preferences(adb: Adb) -> bytes:
    data = adb.shell_bytes("run-as", PACKAGE, "cat", PREFERENCES)
    parse_preferences(data)
    return data


def stop_idle_client(adb: Adb) -> None:
    activities = adb.shell("dumpsys", "activity", "activities")
    resumed = "\n".join(x for x in activities.splitlines() if "mResumedActivity:" in x)
    if PACKAGE + "/.PlayerActivity" in resumed or PACKAGE + "/" + PACKAGE + ".PlayerActivity" in resumed:
        raise TVError("Exit DpadTV playback normally first so its latest progress is saved")
    adb.shell("am", "force-stop", PACKAGE)
    if adb.shell("sh", "-c", "pidof " + PACKAGE + " || true").strip():
        raise TVError("DpadTV is still running; no preference write performed")


def atomic_write(adb: Adb, original: bytes, payload: bytes) -> None:
    """Verify a harmless UTF-8 marker and staged bytes before touching the real file."""
    token = uuid.uuid4().hex
    marker = "shared_prefs/.tvskill-probe-" + token
    temporary = PREFERENCES + ".tvskill-" + token
    probe = "时钟\n'\"$()`\\UTF-8".encode("utf-8")

    def stage(path: str, value: bytes) -> None:
        command = "umask 077; cat > " + shlex.quote(path)
        adb.shell_bytes("run-as", PACKAGE, "sh", "-c", command, input_data=value)
        if adb.shell_bytes("run-as", PACKAGE, "cat", path) != value:
            raise TVError("Byte readback mismatch; original preference file was not replaced")

    try:
        stage(marker, probe)
        stage(temporary, payload)
        if read_preferences(adb) != original:
            raise TVError("Preferences changed during staging; no replacement performed")
        adb.shell_bytes("run-as", PACKAGE, "mv", temporary, PREFERENCES)
        if read_preferences(adb) != payload:
            raise TVError("Final readback failed; leave the client stopped and inspect the backup")
    finally:
        try:
            adb.shell_bytes("run-as", PACKAGE, "rm", "-f", marker, temporary)
        except TVError:
            pass


def backup(adb: Adb, output: Path) -> dict:
    device = adb.identity()
    check_access(adb)
    data = read_preferences(adb)
    document = {"schema": 1, "kind": "dpad-preferences-backup", "created_at": now(),
                "device": device, "preferences_xml": data.decode("utf-8"),
                "sha256": hashlib.sha256(data).hexdigest()}
    save_json(output, document, new=True)
    return document


def set_server(adb: Adb, url: str, record_path: Path) -> dict:
    url = validate_url(url)
    device = adb.identity(mutation=True)
    check_access(adb)
    if record_path.exists():
        raise TVError("Record already exists; choose a new private pathname")
    stop_idle_client(adb)
    original = read_preferences(adb)
    before = server_state(parse_preferences(original))
    after = {"present": True, "value": url}
    if before == after:
        raise TVError("Server URL already matches; no write performed")
    record = {"schema": 1, "kind": "dpad-server-record", "created_at": now(),
              "device": device, "before": before, "after": after,
              "preferences_before_xml": original.decode("utf-8"), "state": "attempted"}
    save_json(record_path, record, new=True)
    try:
        atomic_write(adb, original, changed_preferences(original, after))
    except (TVError, OSError) as exc:
        record.update(state="uncertain", error=str(exc))
        save_json(record_path, record)
        raise
    record.update(state="applied", completed_at=now())
    save_json(record_path, record)
    return record


def restore_server(adb: Adb, record: dict, record_path: Path) -> dict:
    if (record.get("schema") != 1 or record.get("kind") != "dpad-server-record"
            or not isinstance(record.get("device"), dict)
            or record.get("state") not in {"attempted", "applied", "uncertain", "restore_attempted", "restored"}):
        raise TVError("Unrecognized DpadTV server record")
    try:
        before = server_state(parse_preferences(record["preferences_before_xml"].encode("utf-8")))
        if before != record["before"] or record["after"] != {"present": True, "value": validate_url(record["after"]["value"])}:
            raise ValueError("invalid states")
    except (KeyError, TypeError, ValueError) as exc:
        raise TVError("Invalid private server record") from exc
    if adb.identity(mutation=True) != record["device"]:
        raise TVError("Device identity or firmware changed; refusing restore")
    check_access(adb)
    stop_idle_client(adb)
    latest = read_preferences(adb)
    current = server_state(parse_preferences(latest))
    if current not in (before, record["after"]):
        raise TVError("Restore conflict: server URL was changed later; no write performed")
    if current != before:
        # Merge into the latest preferences. Never replace newly accumulated history.
        record.update(state="restore_attempted", preferences_before_restore_xml=latest.decode("utf-8"))
        save_json(record_path, record)
        atomic_write(adb, latest, changed_preferences(latest, before))
    record.update(state="restored", restored_at=now())
    record.pop("error", None)
    save_json(record_path, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("backup", "set-server", "restore-server"):
        p = sub.add_parser(command)
        add_adb_arguments(p)
        if command == "backup":
            p.add_argument("--output", type=Path, required=True)
        else:
            p.add_argument("--record", type=Path, required=True)
        if command == "set-server":
            p.add_argument("--url", required=True)
    args = parser.parse_args()
    try:
        adb = Adb(args.serial, args.adb)
        if args.command == "backup":
            backup(adb, args.output)
        elif args.command == "set-server":
            set_server(adb, args.url, args.record)
        else:
            restore_server(adb, load_json(args.record), args.record)
        print(args.command + ": verified; private record saved; client is not auto-launched")
        return 0
    except (TVError, OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
