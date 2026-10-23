#!/usr/bin/env python3
"""Observe genuine idle, foreground and live logs without sending input or wakelocks."""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from tv_common import Adb, TVError, add_adb_arguments, now, save_json


DEFAULT_PATTERNS = [
    r"com\.duokan\.intent\.action\.show\.screensaver",
    r"com\.xiaomi\.tv\.gallery/\S*ScreenSaverActivity",
    r"AD-PLUGIN-MiAdClient|requestStreamAd",
]


def parse_sample(activity: str, power: str, memory: str, uptime: str) -> dict:
    resumed = re.search(r"(?:mResumedActivity|topResumedActivity|ResumedActivity)"
                        r"[^\n]*?u\d+\s+([^\s}]+)", activity)
    user = dict(re.findall(r"(mLastUserActivityTime(?:NoChangeLights)?)=(\d+)", power))
    wake = re.search(r"mWakefulness=(\w+)", power)
    available = re.search(r"MemAvailable:\s+(\d+)", memory)
    try:
        uptime_seconds = float(uptime.split()[0])
    except (ValueError, IndexError):
        uptime_seconds = None
    return {"foreground": resumed.group(1) if resumed else None,
            "user_activity": {k: int(v) for k, v in user.items()},
            "wakefulness": wake.group(1) if wake else None,
            "mem_available_kb": int(available.group(1)) if available else None,
            "uptime_seconds": uptime_seconds}


def assess(samples: list[dict], expected: str, threshold_ms: int,
           log_running: bool, log_bytes: int, matches: list[dict], errors: list[str]) -> dict:
    span = samples[-1]["elapsed_seconds"] - samples[0]["elapsed_seconds"] if len(samples) > 1 else 0
    user = samples[0]["user_activity"] if samples else {}
    no_input = bool(user) and all(s["user_activity"] == user for s in samples)
    uptimes = [s["uptime_seconds"] for s in samples]
    no_reboot = bool(uptimes) and all(t is not None for t in uptimes)
    if no_reboot:
        no_reboot = all(b >= a for a, b in zip(uptimes, uptimes[1:]))
    checks = {
        "at_least_two_samples": len(samples) >= 2,
        "user_activity_unchanged": no_input,
        "awake_at_every_sample": bool(samples) and all(s["wakefulness"] == "Awake" for s in samples),
        "expected_foreground_at_every_sample": bool(samples) and all(s["foreground"] == expected for s in samples),
        "no_observed_reboot": no_reboot,
        "live_log_stream_survived": log_running and log_bytes > 0,
        "no_collection_errors": not errors,
        "exceeds_original_idle_timeout_plus_60s": span >= threshold_ms / 1000 + 60,
    }
    valid = all(checks.values())
    return {"checks": checks, "sample_span_seconds": round(span, 3),
            "collection_valid_for_idle_comparison": valid,
            "suspect_log_matches": matches,
            "idle_ad_path_not_observed": valid and not matches,
            "limitations": "Periodic foreground samples plus continuous logs cover this run only. "
            "Matching SDK logs indicate requests, not a proven visible impression. "
            "No boot, HDMI, app-internal ads or future firmware behavior is established."}


def monitor(adb: Adb, output: Path, duration: float, interval: float,
            expected: str, threshold_ms: int, patterns: list[str]) -> dict:
    compiled = [re.compile(p, re.I) for p in patterns]
    device = adb.identity()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    samples, errors = [], []
    log_path = output / "live-logcat.txt"
    err_path = output / "logcat-stderr.txt"
    metadata = {"schema": 1, "kind": "idle-observation", "device": device,
                "started_at": now(), "duration_seconds": duration, "interval_seconds": interval,
                "expected_activity": expected, "original_idle_timeout_ms": threshold_ms,
                "log_patterns": patterns}
    save_json(output / "metadata.json", metadata)
    started = time.monotonic()
    log_running = False
    with log_path.open("xb") as log, err_path.open("xb") as err:
        os.chmod(log_path, 0o600)
        os.chmod(err_path, 0o600)
        # Start at the live tail, independent of host/TV clock and timezone.
        proc = subprocess.Popen(adb.base + ["logcat", "-v", "threadtime", "-T", "1"], stdout=log, stderr=err)
        try:
            while True:
                if proc.poll() is not None:
                    raise TVError("logcat exited before observation finished")
                activity = adb.shell("dumpsys", "activity", "activities")
                power = adb.shell("dumpsys", "power")
                memory = adb.shell("cat", "/proc/meminfo")
                uptime = adb.shell("cat", "/proc/uptime")
                row = parse_sample(activity, power, memory, uptime)
                row.update(at=now(), elapsed_seconds=time.monotonic() - started)
                samples.append(row)
                save_json(output / "samples.json", {"samples": samples})
                save_json(output / f"sample-{len(samples):03d}.json",
                          {"activity": activity, "power": power, "memory": memory, "uptime": uptime})
                print(f"sample={len(samples)} elapsed={row['elapsed_seconds']:.1f}s "
                      f"foreground={row['foreground']}", flush=True)
                if time.monotonic() - started >= duration:
                    break
                time.sleep(min(interval, max(0, duration - (time.monotonic() - started))))
            log_running = proc.poll() is None
        except (TVError, KeyboardInterrupt, OSError) as exc:
            errors.append(str(exc) or "Interrupted")
        finally:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    stderr = err_path.read_text(errors="replace").strip()
    if stderr:
        errors.append(f"logcat stderr (review required): {stderr[:1000]}")
    matches = []
    with log_path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if any(p.search(line) for p in compiled):
                matches.append({"line": line.rstrip()[:1500]})
                if len(matches) >= 200:
                    break
    result = assess(samples, expected, threshold_ms, log_running, log_path.stat().st_size, matches, errors)
    result.update(completed_at=now(), sample_count=len(samples), errors=errors)
    save_json(output / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_adb_arguments(parser)
    parser.add_argument("--output", type=Path, required=True, help="New private directory")
    parser.add_argument("--duration", type=float, default=620)
    parser.add_argument("--interval", type=float, default=20)
    parser.add_argument("--expect-activity", required=True)
    parser.add_argument("--baseline-timeout-ms", type=int, required=True)
    parser.add_argument("--log-pattern", action="append", help="Add a firmware-specific suspect pattern")
    args = parser.parse_args()
    if (not math.isfinite(args.duration) or args.duration <= 0
            or not (0 < args.interval <= 60) or args.baseline_timeout_ms <= 0):
        parser.error("Use positive duration/timeout and an interval of at most 60 seconds")
    try:
        result = monitor(Adb(args.serial, args.adb), args.output, args.duration, args.interval,
                         args.expect_activity, args.baseline_timeout_ms,
                         DEFAULT_PATTERNS + (args.log_pattern or []))
        print(f"idle_ad_path_not_observed={result['idle_ad_path_not_observed']}; {args.output / 'result.json'}")
        return 0 if result["idle_ad_path_not_observed"] else 2
    except (TVError, OSError, re.error) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
