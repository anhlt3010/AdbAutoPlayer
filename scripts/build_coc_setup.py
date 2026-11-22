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
PRODUCT_NAME = "CocAutoPlayer"
IDENTIFIER = "com.anhlt3010.CocAutoPlayer"
DOCS_URL = "https://anhlt3010.github.io/AdbAutoPlayer/"
# (file, old, new) text swaps applied in the staging copy only.
REBRAND = (
    ("src-tauri/src/tray.rs", "Show AdbAutoPlayer", f"Show {PRODUCT_NAME}"),
    ("src-tauri/src/tray.rs", '.tooltip("AdbAutoPlayer")', f'.tooltip("{PRODUCT_NAME}")'),
    ("src-tauri/src/main.rs", "AdbAutoPlayer_crash.log", f"{PRODUCT_NAME}_crash.log"),
    ("src-tauri/src/main.rs", "AdbAutoPlayer - Startup Error", f"{PRODUCT_NAME} - Startup Error"),
    ("src-tauri/src/discord.rs", '"username": "AdbAutoPlayer"', f'"username": "{PRODUCT_NAME}"'),
    (
        "src-tauri/src/discord.rs",
        "https://raw.githubusercontent.com/AdbAutoPlayer/AdbAutoPlayer/refs/heads/main/app-icon.png",
        DOCS_URL + "icon.png",
    ),
    (
        "src/lib/components/sticky/DocumentationIconSticky.svelte",
        "https://AdbAutoPlayer.github.io/AdbAutoPlayer/",
        DOCS_URL,
    ),
    ("src/lib/components/modern/StatusBar.svelte", ">AdbAutoPlayer<", f">{PRODUCT_NAME}<"),
    ("src/lib/components/updater/UpdateContainer.svelte", "new version of AdbAutoPlayer", f"new version of {PRODUCT_NAME}"),
)
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
    # Own identity so it installs beside the original AdbAutoPlayer: the install
    # folder, uninstall entry and shortcuts come from productName, and the
    # settings folder (%APPDATA%\<identifier>) comes from identifier.
    conf["productName"] = PRODUCT_NAME
    conf["mainBinaryName"] = PRODUCT_NAME
    conf["identifier"] = IDENTIFIER
    for window in conf["app"]["windows"]:
        window["title"] = PRODUCT_NAME
    # A CoC-only build must never auto-update to the full upstream app.
    conf["plugins"]["updater"]["endpoints"] = [UPDATER_ENDPOINT]
    if pubkey:
        conf["plugins"]["updater"]["pubkey"] = pubkey
        conf["bundle"]["createUpdaterArtifacts"] = True
    else:
        conf["bundle"]["createUpdaterArtifacts"] = False  # no signing key needed
    # MIT: the copyright notice must ship with the app.
    win_path = stage / "src-tauri" / "tauri.bundle.windows.json"
    win = json.loads(win_path.read_text(encoding="utf-8"))
    win["bundle"]["resources"]["../LICENSE"] = "./LICENSE"
    win_path.write_text(json.dumps(win, indent=2) + chr(10), encoding="utf-8")
    conf_path.write_text(json.dumps(conf, indent=2) + "\n", encoding="utf-8")


def _rebrand(stage: Path) -> None:
    """Swap the visible app name (tray, crash log, UI) in the staging copy."""
    for rel, old, new in REBRAND:
        path = stage / rel
        text = path.read_text(encoding="utf-8")
        if old not in text:
            sys.exit(f"rebrand: {old!r} not found in {rel} - update REBRAND")
        path.write_text(text.replace(old, new), encoding="utf-8")


def _apply_icon(stage: Path, icon: Path | None) -> None:
    """Regenerate every app icon from one square PNG (>= 1024 px recommended)."""
    if icon is None:
        print("WARNING: no --icon given, keeping the original AdbAutoPlayer icon")
        return
    _run([_tool("pnpm"), "tauri", "icon", str(icon.resolve())], stage)


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


# Data folders of the game that the upstream bundle-templates.cjs does not know: it
# only lists ``templates/`` and rewrites tauri.bundle.templates.json on every build.
COC_DATA_DIRS = ("tatari_db", "tatari_formations")


def _add_coc_data_resources(stage: Path) -> None:
    """Add the CoC data folders to the regenerated templates bundle config."""
    games = "src-python/adb_auto_player/games"
    path = stage / "src-tauri" / "tauri.bundle.templates.json"
    conf = json.loads(path.read_text(encoding="utf-8"))
    for name in COC_DATA_DIRS:
        src = f"{games}/{KEEP_GAME}/{name}/"
        if not (stage / "src-tauri" / src).is_dir():
            sys.exit(f"{src} missing in the staging copy - is it committed?")
        conf["bundle"]["resources"][src] = f"./games/{KEEP_GAME}/{name}/"
    path.write_text(json.dumps(conf, indent=2) + "\n", encoding="utf-8")


def _build(stage: Path, python_exe: Path) -> Path:
    _run(["node", "scripts/bundle-templates.cjs"], stage)
    _add_coc_data_resources(stage)
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


KEYS_DIR = REPO.parent.parent / "release-keys"  # outside the repo, never committed


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE (or `export KEY=VALUE`) lines; real env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    print(f"loaded signing env from {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="X.Y.Z (a leading v is ignored)")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--out", type=Path, default=REPO.parent.parent)
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--updater", action="store_true", help="signed, self-updating")
    parser.add_argument("--pubkey-file", type=Path, help="public key from tauri signer")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=KEYS_DIR / "coc.env",
        help="file with the TAURI_SIGNING_* variables (default: release-keys/coc.env)",
    )
    parser.add_argument("--icon", type=Path, help="square PNG for the new app icon")
    parser.add_argument("--tag", help="release tag the exe will be uploaded to")
    args = parser.parse_args()

    version = args.version.lstrip("v")
    if not VERSION_RE.match(version):
        sys.exit(f"Bad version: {args.version} (expected X.Y.Z)")

    pubkey = None
    if args.updater:
        if args.env_file != KEYS_DIR / "coc.env" and not args.env_file.exists():
            sys.exit(f"--env-file not found: {args.env_file}")
        _load_env_file(args.env_file)
        pubkey_file = args.pubkey_file or KEYS_DIR / "coc.key.pub"
        if not pubkey_file.exists():
            sys.exit(f"--updater needs the .pub file ({pubkey_file} not found)")
        args.pubkey_file = pubkey_file
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
    _rebrand(stage)
    if args.stage_only:
        print("stage-only: done")
        return

    _link_node_modules(stage)
    icon = args.icon or (REPO / "scripts" / "coc_icon.png")
    _apply_icon(stage, icon if icon.exists() else None)
    python_exe = _prepare_pyembed(stage)
    _install_python(stage, python_exe)
    built = _build(stage, python_exe)

    args.out.mkdir(parents=True, exist_ok=True)
    final = args.out / f"{PRODUCT_NAME}_{version}_x64-setup.exe"
    shutil.copy2(built, final)
    if pubkey:
        tag = args.tag or f"coc-vn-setup-v{version}"
        _write_updater_files(built, final, version, tag)
    print(f"\nSetup: {final} ({final.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
