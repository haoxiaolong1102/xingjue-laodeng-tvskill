"""Shared ADB transport and private local evidence helpers (Python 3.10+)."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile


class TVError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save_json(path: Path, value: dict, *, new: bool = False) -> None:
    """Atomic, mode-0600 output. new=True reserves an unused pathname first."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if new:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError as exc:
            raise TVError(f"Output already exists: {path}") from exc
    fd, temp = tempfile.mkstemp(prefix=".tv-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TVError(f"Cannot read JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TVError("Expected a JSON object")
    return value


class Adb:
    def __init__(self, serial: str, executable: str = "adb", timeout: float = 25):
        if not re.fullmatch(r"[A-Za-z0-9_.:\[\]-]+", serial):
            raise TVError("Use one explicit ADB serial from `adb devices -l`")
        resolved = shutil.which(executable)
        if not resolved:
            raise TVError("adb not found; install Android SDK Platform-Tools or use --adb")
        self.base = [resolved, "-s", serial]
        self.serial = serial
        self.timeout = timeout

    def run(self, *args: str) -> str:
        try:
            result = subprocess.run(self.base + list(args), capture_output=True,
                                    text=True, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TVError(f"ADB transport failed: {exc}") from exc
        message = result.stdout + "\n" + result.stderr
        if result.returncode or re.search(
            r"SecurityException|Exception occurred while executing|"
            r"Error while accessing settings provider|error:.*(?:offline|unauthorized|not found)",
            message, re.I,
        ):
            raise TVError(f"ADB command failed: {message.strip()[:1500]}")
        return result.stdout

    def shell(self, *args: str) -> str:
        # adb shell joins its arguments: quote at the remote shell boundary as well.
        return self.run("shell", shlex.join(list(args)))

    def ready(self) -> None:
        if self.run("get-state").strip() != "device":
            raise TVError("Device is not authorized and online")

    def settings(self, table: str) -> dict[str, str]:
        if table not in {"system", "secure", "global"}:
            raise TVError("Invalid settings table")
        text = self.shell("settings", "list", table)
        return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)

    def identity(self, *, mutation: bool = False) -> dict[str, str]:
        self.ready()
        props = {
            "manufacturer": "ro.product.manufacturer", "model": "ro.product.model",
            "sdk": "ro.build.version.sdk", "fingerprint": "ro.build.fingerprint",
            "incremental": "ro.build.version.incremental", "abi": "ro.product.cpu.abi",
            "hardware_serial": "ro.serialno",
        }
        device = {key: self.shell("getprop", prop).strip() for key, prop in props.items()}
        device["serial"] = self.serial
        device["android_id"] = self.settings("secure").get("android_id", "")
        if mutation:
            if not all(device[key] for key in ("model", "sdk", "fingerprint")):
                raise TVError("Incomplete device identity; refusing settings mutation")
            unique = (device["hardware_serial"], device["android_id"])
            if not any(x and x.lower() not in {"unknown", "null"} for x in unique):
                raise TVError("No stable device identifier; refusing settings mutation")
        return device


def entry(values: dict[str, str], key: str) -> dict:
    # `settings get` prints 'null' for both absence and a literal value. Use list.
    return {"present": key in values, "value": values.get(key)}


def add_adb_arguments(parser, *, serial_required: bool = True) -> None:
    parser.add_argument("--serial", required=serial_required, help="Exact authorized ADB serial")
    parser.add_argument("--adb", default="adb", help="Platform-Tools adb executable")
