#!/usr/bin/env python3
"""Build the original loopback helper using a local Android SDK; never connects to a TV."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import zipfile


def require(path: Path, label: str) -> Path:
    if not path.is_file():
        raise ValueError(f"Missing {label}: {path}")
    return path


def executable(directory: Path | None, name: str) -> Path:
    names = (name + ".exe", name + ".bat", name) if os.name == "nt" else (name,)
    if directory:
        for candidate in names:
            if (directory / candidate).is_file():
                return directory / candidate
    for candidate in names:
        found = shutil.which(candidate)
        if found:
            return Path(found)
    raise ValueError(f"Missing {name}; configure the JDK / Android build-tools paths")


def run(args: list, env: dict) -> None:
    subprocess.run(list(map(str, args)), check=True, timeout=60, env=env)


def build(args) -> dict:
    source = Path(__file__).resolve().parent
    sdk_name = args.sdk or os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    sdk = Path(sdk_name).expanduser().resolve() if sdk_name else None
    android = args.android_jar or (sdk / "platforms/android-28/android.jar" if sdk else None)
    if not android:
        raise ValueError("Set --sdk / ANDROID_SDK_ROOT or pass --android-jar and --build-tools")
    android = require(Path(android).expanduser().resolve(), "Android API 28 android.jar")
    tools = args.build_tools
    if not tools and sdk:
        versions = [p for p in (sdk / "build-tools").glob("*") if p.is_dir() and p.name[:1].isdigit()]
        if versions:
            tools = max(versions, key=lambda p: tuple(int(x) for x in re.findall(r"\d+", p.name)))
    if not tools:
        raise ValueError("Install Android SDK build-tools or pass --build-tools")
    tools = Path(tools).expanduser().resolve()
    signer = require(tools / "lib/apksigner.jar", "apksigner.jar")
    java_home = args.java_home or os.environ.get("JAVA_HOME")
    java_bin = Path(java_home).expanduser().resolve() / "bin" if java_home else None
    java, javac, jar, keytool = [executable(java_bin, name) for name in ("java", "javac", "jar", "keytool")]
    aapt, align, d8 = [executable(tools, name) for name in ("aapt2", "zipalign", "d8")]
    env = dict(os.environ)
    if java_home:
        env["JAVA_HOME"] = str(Path(java_home).expanduser().resolve())
    state = args.state_dir.expanduser().resolve()
    if state == source or source in state.parents:
        raise ValueError("Use a private state directory outside the helper source tree")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    signing = state / "signing"
    signing.mkdir(exist_ok=True, mode=0o700)
    key, password = signing / "bridge-signing.p12", signing / "signing-password.txt"
    if key.exists() != password.exists():
        raise ValueError("Incomplete signing state; restore the matching key/password instead of generating a replacement")
    if not key.exists():
        # Keep this private state for future `adb install -r` updates with the same certificate.
        secret = secrets.token_urlsafe(32)
        descriptor = os.open(password, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(secret)
        sign_env = dict(env, TV_BRIDGE_SIGNING_PASSWORD=secret)
        run([keytool, "-genkeypair", "-alias", "bridge", "-keyalg", "RSA", "-keysize", "2048",
             "-validity", "10000", "-storetype", "PKCS12", "-keystore", key,
             "-storepass:env", "TV_BRIDGE_SIGNING_PASSWORD", "-keypass:env", "TV_BRIDGE_SIGNING_PASSWORD",
             "-dname", "CN=Xingjue TV Local Bridge"], sign_env)
        key.chmod(0o600)
    password.chmod(0o600)
    out = state / "out"
    if out.exists():
        if out.is_symlink():
            raise ValueError("Build output must not be a symlink")
        shutil.rmtree(out)
    classes, dex, assets = out / "classes", out / "dex", out / "assets"
    for directory in (classes, dex, assets):
        directory.mkdir(parents=True, mode=0o700)
    # No user's source list or public collector is distributed in the helper.
    (assets / "default-sources.json").write_text('{"sources":[]}', encoding="utf-8")
    run([javac, "--release", "8", "-encoding", "UTF-8", "-cp", android, "-d", classes,
         *sorted((source / "src").rglob("*.java"))], env)
    run([jar, "cf", out / "classes.jar", "-C", classes, "."], env)
    run([d8, "--lib", android, "--min-api", "28", "--output", dex, out / "classes.jar"], env)
    run([aapt, "link", "--manifest", source / "AndroidManifest.xml", "-I", android,
         "-A", assets, "-o", out / "unsigned.apk"], env)
    with zipfile.ZipFile(out / "unsigned.apk", "a", zipfile.ZIP_DEFLATED) as archive:
        archive.write(dex / "classes.dex", "classes.dex")
    run([align, "-f", "4", out / "unsigned.apk", out / "aligned.apk"], env)
    apk = out / "xingjue-libretv-bridge.apk"
    run([java, "-jar", signer, "sign", "--ks", key, "--ks-key-alias", "bridge",
         "--ks-pass", "file:" + str(password), "--out", apk, out / "aligned.apk"], env)
    run([java, "-jar", signer, "verify", "--verbose", apk], env)
    result = {"apk": str(apk), "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
              "helper_version": "1.2", "min_sdk": 28, "bundled_sources": 0,
              "signing_state": str(signing)}
    (state / "build-info.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", help="Installed Android SDK with API 28 and build-tools")
    parser.add_argument("--android-jar", type=Path, help="Override platforms/android-28/android.jar")
    parser.add_argument("--build-tools", type=Path, help="SDK build-tools directory (aapt2, d8, zipalign, lib/apksigner.jar)")
    parser.add_argument("--java-home", help="JDK 17 home, otherwise JAVA_HOME / PATH")
    parser.add_argument("--state-dir", type=Path, required=True, help="Private build and persistent signing state")
    args = parser.parse_args()
    old_umask = os.umask(0o077)
    try:
        print(json.dumps(build(args), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        os.umask(old_umask)


if __name__ == "__main__":
    sys.exit(main())
