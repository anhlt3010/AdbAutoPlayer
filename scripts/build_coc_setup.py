"""Build a Windows setup (NSIS) of AdbAutoPlayer that contains only Clash of Critters.

The build runs in a throw-away staging copy of a git ref (default HEAD), so the
working tree is never modified and uncommitted changes are not included. In the
staging copy every other game (code, templates, seed settings) is deleted before
the Python package is installed and the Tauri bundle is built.

Usage:
    python scripts/build_coc_setup.py 0.4.0
    python scripts/build_coc_setup.py 0.4.0 --ref coc-vn-v0.4.0 --out N:/dir
    python scripts/build_coc_setup.py 0.4.0 --stage-only   # stop after staging
    python scripts/build_coc_setup.py 0.4.0 --updater --pubkey-file k.key.pub

--updater builds a self-updating setup signed with your own key: set
TAURI_SIGNING_PRIVATE_KEY (key content or path) and
TAURI_SIGNING_PRIVATE_KEY_PASSWORD, and pass the matching .pub file. It also
writes latest.json and copies the .sig next to the setup.
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KEEP_GAME = "clash_of_critters"
GAMES_REL = "src-tauri/src-python/adb_auto_player/games"
KEEP_SETTINGS = {"ADB.toml", "App.toml", "ClashOfCritters.toml"}
TARGET = "x86_64-pc-windows-msvc"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
REPO_URL = "https://github.com/anhlt3010/AdbAutoPlayer"
UPDATER_ENDPOINT = f"{REPO_URL}/releases/latest/download/latest.json"


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"\n$ {' '.join(cmd)}  (cwd={cwd})", flush=True)
    full_env = {**os.environ, **(env or {})}
    subprocess.run(cmd, cwd=cwd, env=full_env, check=True)


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        sys.exit(f"Required tool not found on PATH: {name}")
    return path


def _stage(ref: str, stage: Path) -> None:
    """Export the git ref into a clean staging folder."""
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    tar_path = stage.parent / "_stage.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(tar_path), ref],
        cwd=REPO,
        check=True,
    )
    with tarfile.open(tar_path) as tar:
        tar.extractall(stage, filter="data")
    tar_path.unlink()


def _strip_other_games(stage: Path) -> None:
    games = stage / GAMES_REL
    for child in games.iterdir():
        if child.is_dir() and child.name != KEEP_GAME and child.name != "__pycache__":
            print(f"remove game: {child.name}")
            shutil.rmtree(child)
    settings = stage / "src-tauri" / "settings"
    for toml in settings.glob("*.toml"):
        if toml.name not in KEEP_SETTINGS:
            print(f"remove settings: {toml.name}")
            toml.unlink()
    left = sorted(p.name for p in games.iterdir() if p.is_dir())
    if KEEP_GAME not in left:
        sys.exit(f"{KEEP_GAME} missing from {games}")


def _patch_config(stage: Path, version: str, pubkey: str | None) -> None:
    _run(["node", "scripts/set-version.cjs", version], stage)
    conf_path = stage / "src-tauri" / "tauri.conf.json"
    conf = json.loads(conf_path.read_text(encoding="utf-8"))
    # A CoC-only build must never auto-update to the full upstream app.
    conf["plugins"]["updater"]["endpoints"] = [UPDATER_ENDPOINT]
    if pubkey:
        conf["plugins"]["updater"]["pubkey"] = pubkey
        conf["bundle"]["createUpdaterArtifacts"] = True
    else:
        conf["bundle"]["createUpdaterArtifacts"] = False  # no signing key needed
    conf_path.write_text(json.dumps(conf, indent=2) + "\n", encoding="utf-8")


def _link_node_modules(stage: Path) -> None:
    src = REPO / "node_modules"
    if not src.exists():
        sys.exit("node_modules missing in the repo - run `pnpm install` first")
    dst = stage / "node_modules"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(dst), str(src)], check=True, capture_output=True
    )


def _prepare_pyembed(stage: Path) -> Path:
    src = REPO / "src-tauri" / "pyembed"
    if not (src / "python" / "python.exe").exists():
        sys.exit(
            "src-tauri/pyembed/python missing - download python-build-standalone "
            "as in .github/workflows/publish.yaml first"
        )
    dst = stage / "src-tauri" / "pyembed"
    print("copy pyembed (this takes a moment)...")
    shutil.copytree(src, dst)
    return dst / "python" / "python.exe"


def _install_python(stage: Path, python_exe: Path) -> None:
    _run(
        [
            _tool("uv"),
            "pip",
            "install",
            "--exact",
            "--compile-bytecode",
            f"--python={python_exe}",
            "./src-tauri",
        ],
        stage,
        {"PYTAURI_STANDALONE": "1"},
    )
    site_games = python_exe.parent / "Lib/site-packages/adb_auto_player/games"
    for child in site_games.iterdir():
        if child.is_dir() and child.name not in (KEEP_GAME, "__pycache__"):
            print(f"remove leftover from embedded python: {child.name}")
            shutil.rmtree(child)


def _build(stage: Path, python_exe: Path) -> Path:
    _run(["node", "scripts/bundle-templates.cjs"], stage)
    env = {
        "PYO3_PYTHON": str(python_exe),
        "CARGO_TARGET_DIR": str(REPO / "target"),  # reuse the compiled dependencies
    }
    _run(
        [
            _tool("pnpm"),
            "tauri",
            "build",
            "--target",
            TARGET,
            "--config",
            "src-tauri/tauri.bundle.windows.json",
            "--config",
            "src-tauri/tauri.bundle.templates.json",
        ],
        stage,
        env,
    )
    nsis = REPO / "target" / TARGET / "release" / "bundle" / "nsis"
    exes = sorted(nsis.glob("*-setup.exe"), key=lambda p: p.stat().st_mtime)
    if not exes:
        sys.exit(f"no setup exe found in {nsis}")
    return exes[-1]


def _write_updater_files(built: Path, final: Path, version: str, tag: str) -> None:
    """Copy the .sig and write latest.json next to the setup."""
    sig = built.with_name(built.name + ".sig")
    if not sig.exists():
        sys.exit(f"missing signature {sig} - is the private key set?")
    shutil.copy2(sig, final.with_name(final.name + ".sig"))
    latest = {
        "version": version,
        "notes": f"Clash of Critters setup {version}",
        "pub_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": {
            "windows-x86_64": {
                "signature": sig.read_text(encoding="utf-8").strip(),
                "url": f"{REPO_URL}/releases/download/{tag}/{final.name}",
            }
        },
    }
    out = final.with_name("latest.json")
    out.write_text(json.dumps(latest, indent=2) + "\n", encoding="utf-8")
    print(f"Updater files: {final.name}.sig, {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="X.Y.Z (a leading v is ignored)")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--out", type=Path, default=REPO.parent.parent)
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--updater", action="store_true", help="signed, self-updating")
    parser.add_argument("--pubkey-file", type=Path, help="public key from tauri signer")
    parser.add_argument("--tag", help="release tag the exe will be uploaded to")
    args = parser.parse_args()

    version = args.version.lstrip("v")
    if not VERSION_RE.match(version):
        sys.exit(f"Bad version: {args.version} (expected X.Y.Z)")

    pubkey = None
    if args.updater:
        if not args.pubkey_file or not args.pubkey_file.exists():
            sys.exit("--updater needs --pubkey-file pointing to the .pub file")
        if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
            sys.exit("--updater needs env TAURI_SIGNING_PRIVATE_KEY (+ _PASSWORD)")
        raw = args.pubkey_file.read_text(encoding="utf-8").strip()
        # tauri.conf wants the base64 of the minisign text; the .pub file that
        # `tauri signer generate` writes is already that base64 string.
        if raw.startswith("untrusted comment"):
            raw = base64.b64encode(raw.encode()).decode()
        pubkey = raw

    stage = REPO.parent.parent / "coc_setup_build" / "src"
    print(f"staging {args.ref} -> {stage}")
    _stage(args.ref, stage)
    _strip_other_games(stage)
    _patch_config(stage, version, pubkey)
    if args.stage_only:
        print("stage-only: done")
        return

    _link_node_modules(stage)
    python_exe = _prepare_pyembed(stage)
    _install_python(stage, python_exe)
    built = _build(stage, python_exe)

    args.out.mkdir(parents=True, exist_ok=True)
    final = args.out / f"AdbAutoPlayer_CoC_{version}_x64-setup.exe"
    shutil.copy2(built, final)
    if pubkey:
        tag = args.tag or f"coc-vn-setup-v{version}"
        _write_updater_files(built, final, version, tag)
    print(f"\nSetup: {final} ({final.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
