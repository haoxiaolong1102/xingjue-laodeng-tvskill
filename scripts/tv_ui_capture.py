#!/usr/bin/env python3
"""Capture fresh UI XML and screenshot; never accept stale XML after an idle error."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

from tv_common import Adb, TVError, add_adb_arguments, now, save_json


def fresh_xml(adb: Adb, expected_package: str | None) -> str:
    remote = f"/data/local/tmp/tv-skill-{uuid.uuid4().hex}.xml"
    try:
        command = shlex.join(["uiautomator", "dump", remote])
        result = subprocess.run(adb.base + ["shell", command], capture_output=True,
                                text=True, timeout=adb.timeout)
        message = result.stdout + "\n" + result.stderr
        # Android can exit zero on `ERROR: could not get idle state.`
        if result.returncode or "ERROR" in message.upper():
            raise TVError(f"Fresh XML unavailable: {message.strip()[:1000]}")
        xml = adb.shell("cat", remote)
        root = ET.fromstring(xml)
        if root.tag != "hierarchy":
            raise TVError("Not an Android UI hierarchy")
        if expected_package and not any(n.get("package") == expected_package for n in root.iter("node")):
            raise TVError("Fresh XML does not contain the expected package; inspect screenshot")
        return xml
    except (subprocess.TimeoutExpired, ET.ParseError) as exc:
        raise TVError(f"Fresh XML unavailable: {exc}") from exc
    finally:
        try:
            adb.shell("rm", "-f", remote)  # Only this invocation's UUID path.
        except TVError:
            pass


def capture(adb: Adb, output: Path, expected_package: str | None) -> dict:
    adb.ready()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    result = {"at": now(), "xml_valid": False, "screenshot_valid": False, "errors": {}}
    try:
        xml = fresh_xml(adb, expected_package)
        path = output / "ui.xml"
        with path.open("x", encoding="utf-8") as stream:
            os.chmod(path, 0o600)
            stream.write(xml)
        result["xml_valid"] = True
    except TVError as exc:
        result["errors"]["xml"] = str(exc)
    try:
        image = subprocess.run(adb.base + ["exec-out", "screencap", "-p"], capture_output=True,
                               timeout=adb.timeout)
        if image.returncode or not image.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
            raise TVError("No valid PNG from screencap")
        path = output / "screen.png"
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(image.stdout)
        result["screenshot_valid"] = True
    except (TVError, subprocess.TimeoutExpired) as exc:
        result["errors"]["screenshot"] = str(exc)
    save_json(output / "capture.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_adb_arguments(parser)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-package")
    args = parser.parse_args()
    try:
        result = capture(Adb(args.serial, args.adb), args.output, args.expect_package)
        print(f"Fresh XML={result['xml_valid']}; screenshot={result['screenshot_valid']}; {args.output}")
        return 0 if result["xml_valid"] and result["screenshot_valid"] else 2
    except (TVError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
