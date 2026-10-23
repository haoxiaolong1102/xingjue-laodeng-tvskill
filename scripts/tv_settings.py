#!/usr/bin/env python3
"""Plan, apply and restore narrowly scoped TV settings with a write-ahead record."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import re
import sys

from tv_common import Adb, TVError, add_adb_arguments, entry, load_json, now, save_json


ALLOWED = {
    ("system", "screen_saver_timeout"),
    ("system", "boot_ad_switch"),
    ("system", "boot_ad_sound_enable"),
    ("system", "boot_ad_switch_show"),
    ("secure", "screensaver_enabled"),
    ("secure", "screensaver_components"),
}


def check_value(table: str, key: str, value: str) -> None:
    if (table, key) not in ALLOWED:
        raise TVError(f"Setting is outside the helper's scope: {table}:{key}")
    if key == "screen_saver_timeout":
        if not re.fullmatch(r"-?\d+", value) or not (-1 <= int(value) <= 2147483647) or int(value) == 0:
            raise TVError("Timeout must be -1 or a positive integer in milliseconds")
    elif key == "screensaver_components":
        if not re.fullmatch(r"[\w.]+/[\w.$]+(?:,[\w.]+/[\w.$]+)*", value, re.ASCII):
            raise TVError("Expected package/class component(s)")
    elif value not in {"0", "1"}:
        raise TVError("Switch values must be 0 or 1")


def validate_document(doc: dict, kind: str) -> None:
    if doc.get("schema") != 1 or doc.get("kind") != kind or not isinstance(doc.get("device"), dict):
        raise TVError("Unrecognized settings document")
    changes = doc.get("changes")
    if not isinstance(changes, list) or not changes:
        raise TVError("No changes in document")
    seen = set()
    for change in changes:
        if not isinstance(change, dict):
            raise TVError("Invalid change entry")
        table, key = change.get("table"), change.get("key")
        if not isinstance(table, str) or not isinstance(key, str) or (table, key) in seen:
            raise TVError("Invalid or duplicate setting")
        seen.add((table, key))
        for field in ("before", "after"):
            state = change.get(field)
            if (not isinstance(state, dict) or type(state.get("present")) is not bool
                    or (state["present"] and not isinstance(state.get("value"), str))
                    or (not state["present"] and state.get("value") is not None)):
                raise TVError("Invalid setting state")
        after = change["after"]
        if not after["present"]:
            raise TVError("Plans may only set explicit values")
        check_value(table, key, after["value"])
        if kind == "settings-record" and change.get("status") not in {
            "pending", "attempted", "applied", "uncertain", "restore_attempted", "restored"
        }:
            raise TVError("Invalid record status")


def read_changes(adb: Adb, changes: list[dict]) -> list[dict]:
    tables = {table: adb.settings(table) for table in {c["table"] for c in changes}}
    return [entry(tables[c["table"]], c["key"]) for c in changes]


def plan(adb: Adb, specs: list[str], output: Path) -> dict:
    device = adb.identity(mutation=True)
    changes, seen = [], set()
    for spec in specs:
        try:
            left, value = spec.split("=", 1)
            table, key = left.split(":", 1)
        except ValueError as exc:
            raise TVError("Use --change table:key=value") from exc
        check_value(table, key, value)
        if (table, key) in seen:
            raise TVError("Duplicate setting")
        seen.add((table, key))
        changes.append({"table": table, "key": key,
                        "after": {"present": True, "value": value}})
    for change, before in zip(changes, read_changes(adb, changes)):
        change["before"] = before
    changes = [c for c in changes if c["before"] != c["after"]]
    if not changes:
        raise TVError("Requested values already match; no plan created")
    document = {"schema": 1, "kind": "settings-plan", "created_at": now(),
                "device": device, "changes": changes}
    save_json(output, document, new=True)
    return document


def same_device(adb: Adb, doc: dict) -> None:
    if adb.identity(mutation=True) != doc["device"]:
        raise TVError("Device identity or firmware changed; create a new plan")


def put_state(adb: Adb, change: dict, state: dict) -> None:
    if state["present"]:
        adb.shell("settings", "put", change["table"], change["key"], state["value"])
    else:
        adb.shell("settings", "delete", change["table"], change["key"])
    actual = entry(adb.settings(change["table"]), change["key"])
    if actual != state:
        raise TVError(f"Readback failed for {change['table']}:{change['key']}")


def apply(adb: Adb, document: dict, record_path: Path) -> dict:
    validate_document(document, "settings-plan")
    same_device(adb, document)
    current = read_changes(adb, document["changes"])
    # Preflight the whole plan before creating a record or changing anything.
    if any(value != c["before"] for c, value in zip(document["changes"], current)):
        raise TVError("Stale plan: original settings changed; no writes performed")
    record = deepcopy(document)
    record.update(kind="settings-record", state="applying", started_at=now())
    for change in record["changes"]:
        change["status"] = "pending"
    save_json(record_path, record, new=True)
    for change in record["changes"]:
        change["status"] = "attempted"
        save_json(record_path, record)  # Durable intent BEFORE each ADB write.
        try:
            put_state(adb, change, change["after"])
        except (TVError, OSError) as exc:
            change["status"] = "uncertain"
            record.update(state="incomplete", error=str(exc))
            save_json(record_path, record)
            raise TVError(f"Apply interrupted; keep {record_path} and use restore: {exc}") from exc
        change["status"] = "applied"
        save_json(record_path, record)
    record.update(state="applied", completed_at=now())
    save_json(record_path, record)
    return record


def restore(adb: Adb, record: dict, record_path: Path) -> dict:
    validate_document(record, "settings-record")
    same_device(adb, record)
    attempted = [c for c in record["changes"] if c["status"] != "pending"]
    current = read_changes(adb, attempted)
    if any(value != c["before"] and value != c["after"] for c, value in zip(attempted, current)):
        raise TVError("Restore conflict: a later setting changed; no writes performed")
    record["state"] = "restoring"
    save_json(record_path, record)
    for change, value in reversed(list(zip(attempted, current))):
        if value != change["before"]:
            change["status"] = "restore_attempted"
            save_json(record_path, record)
            try:
                put_state(adb, change, change["before"])
            except (TVError, OSError) as exc:
                record.update(state="restore_incomplete", error=str(exc))
                save_json(record_path, record)
                raise TVError(f"Restore interrupted; keep the record and retry: {exc}") from exc
        change["status"] = "restored"
        save_json(record_path, record)
    record.update(state="restored", restored_at=now())
    record.pop("error", None)
    save_json(record_path, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    add_adb_arguments(p)
    p.add_argument("--change", action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("apply")
    add_adb_arguments(p)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--record", type=Path, required=True)
    p = sub.add_parser("restore")
    add_adb_arguments(p)
    p.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    try:
        adb = Adb(args.serial, args.adb)
        if args.command == "plan":
            result = plan(adb, args.change, args.output)
        elif args.command == "apply":
            result = apply(adb, load_json(args.plan), args.record)
        else:
            result = restore(adb, load_json(args.record), args.record)
        print(f"{args.command}: {len(result['changes'])} entries; local record saved")
        return 0
    except (TVError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
