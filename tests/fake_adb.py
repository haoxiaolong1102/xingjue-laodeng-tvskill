#!/usr/bin/env python3
"""Offline ADB fixture. Refuses to run without an explicit temporary state file."""
import base64
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import time


def main():
    name = os.environ.get("TV_SKILL_FAKE_STATE")
    if not name or sys.argv[1:3] != ["-s", "tv-fixture"]:
        sys.exit("This is an offline fixture, not adb")
    path = Path(name)
    state = json.loads(path.read_text())
    args = sys.argv[3:]
    command = shlex.split(args[1]) if args[:1] == ["shell"] else args
    state.setdefault("trace", []).append(command)

    def save():
        # logcat and polling commands run concurrently; never expose partial JSON.
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".fixture-")
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream)
        os.replace(temp, path)

    save()
    if command == ["get-state"]:
        print(state.get("connection", "device"))
    elif command[:1] == ["getprop"]:
        print(state["props"].get(command[1], ""))
    elif command[:2] == ["settings", "list"]:
        print("\n".join(f"{k}={v}" for k, v in state["settings"][command[2]].items()))
    elif command[:2] in (["settings", "put"], ["settings", "delete"]):
        _, operation, table, key, *value = command
        if operation == "put":
            state["settings"][table][key] = value[0]
        else:
            state["settings"][table].pop(key, None)
        save()
        if state.get("fail_after_write") == key:
            print("error: simulated transport failure after accepted write", file=sys.stderr)
            return 1
    elif command[:2] == ["uiautomator", "dump"]:
        if not state.get("dump_ok"):
            print("ERROR: could not get idle state.", file=sys.stderr)
            return 0
        package = state.get("ui_package", "com.leslie.tvhome")
        state.setdefault("remote", {})[command[2]] = f'<hierarchy><node package="{package}" /></hierarchy>'
        save()
        print(f"UI hierarchy dumped to: {command[2]}")
    elif command[:1] == ["cat"] and command[1] in state.get("remote", {}):
        print(state["remote"][command[1]])
    elif command[:2] == ["rm", "-f"]:
        state.setdefault("remote", {}).pop(command[2], None)
        save()
    elif command == ["exec-out", "screencap", "-p"]:
        sys.stdout.buffer.write(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII="))
    elif command[:1] == ["logcat"]:
        print(state.get("log_line", "I/Fixture: live stream"), flush=True)
        if state.get("log_exit"):
            return 1
        while True:
            time.sleep(0.1)
    elif command == ["dumpsys", "activity", "activities"]:
        print("mResumedActivity: ActivityRecord{abc u0 com.leslie.tvhome/.HomeActivity t1}")
    elif command == ["dumpsys", "power"]:
        print("mWakefulness=Awake\nmLastUserActivityTime=100\nmLastUserActivityTimeNoChangeLights=100")
    elif command == ["cat", "/proc/meminfo"]:
        print("MemTotal: 2000000 kB\nMemAvailable: 900000 kB")
    elif command == ["cat", "/proc/uptime"]:
        print(f"{time.monotonic():.3f} 1000.0")
    elif command == ["df", "/data"]:
        print("Filesystem 1K-blocks Used Available Use% Mounted on\nfixture 10000 2100 7900 21% /data")
    elif command[:3] == ["pm", "list", "packages"]:
        print("" if "-d" in command else "package:com.leslie.tvhome\npackage:com.factory.home")
    elif command[:3] == ["cmd", "package", "resolve-activity"]:
        print("com.factory.home/.MainActivity")
    elif command[:1] == ["dumpsys"]:
        print("Fixture service state")
    else:
        print(f"Unsupported fixture command: {command}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
