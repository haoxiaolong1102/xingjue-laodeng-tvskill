#!/usr/bin/env python3
"""Read-only baseline for one authorized TV; raw output stays private and local."""
import argparse
from pathlib import Path
import sys

from tv_common import Adb, TVError, add_adb_arguments, entry, now, save_json


KEYS = {
    "system": ["screen_saver_timeout", "screen_off_timeout", "boot_ad_switch",
               "boot_ad_sound_enable", "boot_ad_switch_show", "boot_ad"],
    "secure": ["screensaver_components", "screensaver_enabled", "enabled_accessibility_services",
               "accessibility_enabled", "enabled_notification_listeners", "sleep_timeout"],
    "global": ["individual_privacy_enabled", "mitv.settings.advertise.state",
               "adb_enabled", "low_power", "window_animation_scale",
               "transition_animation_scale", "animator_duration_scale"],
}
COMMANDS = {
    "activities": ("dumpsys", "activity", "activities"),
    "power": ("dumpsys", "power"), "dreams": ("dumpsys", "dreams"),
    "memory": ("cat", "/proc/meminfo"), "cpu": ("dumpsys", "cpuinfo"),
    "process_memory": ("dumpsys", "meminfo"), "storage": ("df", "/data"),
    "packages": ("pm", "list", "packages"),
    "disabled_packages": ("pm", "list", "packages", "-d"),
    "home": ("cmd", "package", "resolve-activity", "--brief", "-a",
             "android.intent.action.MAIN", "-c", "android.intent.category.HOME"),
    "tv_inputs": ("dumpsys", "tv_input"),
    "system_ad_property": ("getprop", "persist.sys.adswitch"),
}


def snapshot(adb: Adb) -> dict:
    result = {"schema": 1, "kind": "tv-snapshot", "at": now(),
              "device": adb.identity(), "settings": {}, "observations": {}, "errors": {}}
    for table, keys in KEYS.items():
        values = adb.settings(table)
        result["settings"][table] = {key: entry(values, key) for key in keys}
    for name, command in COMMANDS.items():
        try:
            result["observations"][name] = adb.shell(*command)
        except TVError as exc:
            result["errors"][name] = str(exc)
    result["complete"] = not result["errors"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_adb_arguments(parser)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = snapshot(Adb(args.serial, args.adb))
        save_json(args.output, result, new=True)
        print(f"Snapshot saved: {args.output}; complete={result['complete']}")
        return 0 if result["complete"] else 2
    except (TVError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
