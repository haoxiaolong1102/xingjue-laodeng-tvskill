#!/usr/bin/env python3
"""Build the offline TV installer from pinned upstream release files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile


SOURCE = Path(__file__).resolve().parent
KEY_ALIAS = "tvsetup"


def run(*args: str | Path, env: dict[str, str] | None = None) -> None:
    subprocess.run([str(value) for value in args], check=True, env=env, timeout=120)


def pinned_file(entry: dict, directory: Path) -> Path:
    file = directory / entry["name"]
    if not file.is_file():
        if "url" not in entry:
            raise ValueError(f"Place the built release artifact in the vendor directory: {file.name}")
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
        try:
            with urllib.request.urlopen(entry["url"], timeout=25) as response, temporary.open("wb") as out:
                shutil.copyfileobj(response, out)
            check_sha256(temporary, entry["sha256"])
            temporary.replace(file)
        finally:
            temporary.unlink(missing_ok=True)
    check_sha256(file, entry["sha256"])
    return file


def check_sha256(path: Path, expected: str) -> None:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected:
        raise ValueError(f"SHA-256 does not match the release lock: {path.name}")


def signing_files(jdk: Path, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = directory / "tvsetup.p12"
    password = directory / "tvsetup-password"
    if key.is_file() != password.is_file():
        raise ValueError("Incomplete signing state. Restore the existing key and password together.")
    if not key.is_file():
        secret = secrets.token_urlsafe(32)
        with password.open("x", encoding="ascii") as out:
            out.write(secret)
        env = dict(os.environ, XINGJUE_SETUP_KEY_PASSWORD=secret)
        run(jdk / "keytool", "-genkeypair", "-alias", KEY_ALIAS, "-keyalg", "RSA",
            "-keysize", "3072", "-validity", "10000", "-keystore", key, "-storetype", "PKCS12",
            "-storepass:env", "XINGJUE_SETUP_KEY_PASSWORD", "-dname", "CN=Xingjue TVSkill",
            env=env)
    key.chmod(0o600)
    password.chmod(0o600)
    return key, password


def build(args: argparse.Namespace) -> None:
    platform = args.sdk / "platforms/android-28/android.jar"
    tools = args.sdk / "build-tools/35.0.0"
    jdk = args.java_home / "bin"
    java = jdk / "java"
    args.vendor.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    lock = json.loads((SOURCE / "upstream-lock.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="tvsetup-build-", dir=args.output.parent) as temp:
        work = Path(temp)
        assets = work / "assets"
        packages = assets / "packages"
        licenses = assets / "licenses"
        classes = work / "classes"
        dex = work / "dex"
        generated = work / "gen"
        for directory in (packages, licenses, classes, dex, generated):
            directory.mkdir(parents=True)
        for app in lock["apps"]:
            original = pinned_file(app, args.vendor)
            shutil.copyfile(original, packages / app["asset"])
        for notice in lock["notices"]:
            original = pinned_file(notice, args.vendor)
            shutil.copyfile(original, licenses / original.name)
        shutil.copyfile(SOURCE / "LICENSE", licenses / "TVSkill-LICENSE.txt")
        shutil.copyfile(SOURCE / "THIRD-PARTY.txt", licenses / "THIRD-PARTY.txt")
        (assets / "app-list.json").write_text(json.dumps(lock["apps"], ensure_ascii=False), encoding="utf-8")
        resources = work / "resources.zip"
        unsigned = work / "unsigned.apk"
        aligned = work / "aligned.apk"
        signed = work / "signed.apk"
        run(tools / "aapt2", "compile", "--dir", SOURCE / "res", "-o", resources)
        run(tools / "aapt2", "link", "-I", platform, "--manifest", SOURCE / "AndroidManifest.xml",
            "--java", generated, "-A", assets, "-0", "apk", "-0", "zip", "-o", unsigned, resources)
        java_sources = sorted((SOURCE / "src").rglob("*.java")) + sorted(generated.rglob("*.java"))
        run(jdk / "javac", "--release", "8", "-encoding", "UTF-8", "-cp", platform,
            "-d", classes, *java_sources)
        jar = work / "classes.jar"
        run(jdk / "jar", "cf", jar, "-C", classes, ".")
        run(java, "-cp", tools / "lib/d8.jar", "com.android.tools.r8.D8",
            "--lib", platform, "--min-api", "28", "--output", dex, jar)
        with zipfile.ZipFile(unsigned, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(dex / "classes.dex", "classes.dex")
        run(tools / "zipalign", "-f", "4", unsigned, aligned)
        key, password = signing_files(jdk, args.signing_dir)
        signer = tools / "lib/apksigner.jar"
        run(java, "-jar", signer, "sign", "--ks", key, "--ks-key-alias", KEY_ALIAS,
            "--ks-pass", "file:" + str(password), "--v1-signing-enabled", "false",
            "--v2-signing-enabled", "true", "--v4-signing-enabled", "false", "--out", signed, aligned)
        run(java, "-jar", signer, "verify", "--verbose", signed)
        run(tools / "zipalign", "-c", "4", signed)
        signed.replace(args.output)
        args.output.chmod(0o644)
    print(f"Built {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True, help="Android SDK with API 28 and build-tools 35.0.0")
    parser.add_argument("--java-home", type=Path, required=True, help="JDK 17 or newer")
    parser.add_argument("--vendor", type=Path, required=True, help="Cache for pinned public release files")
    parser.add_argument("--signing-dir", type=Path, required=True, help="Private directory for the release signing key")
    parser.add_argument("--output", type=Path, required=True, help="Path for the signed APK")
    args = parser.parse_args()
    old_umask = os.umask(0o077)
    try:
        build(args)
    finally:
        os.umask(old_umask)


if __name__ == "__main__":
    main()
