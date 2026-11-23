"""Build the Clash of Critters patch zip.

Layout (same as the earlier clash_of_critters_patch_v0.1.x zips)::

    Lib/site-packages/adb_auto_player/games/clash_of_critters/*.py
    games/clash_of_critters/{templates,tatari_db,tatari_formations,tatari_dojo}/...

Files are taken from a git ref (default HEAD), so uncommitted changes are not
included.

Usage:
    python scripts/build_coc_patch.py 0.2.0
    python scripts/build_coc_patch.py 0.2.0 --ref coc-vn-v0.2.0 --out N:/dir
"""

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GAME_DIR = "src-tauri/src-python/adb_auto_player/games/clash_of_critters"
DATA_DIRS = ("templates", "tatari_db", "tatari_formations", "tatari_dojo")
PY_DEST = "Lib/site-packages/adb_auto_player/games/clash_of_critters"
DATA_DEST = "games/clash_of_critters"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True
    ).stdout


def _list_files(ref: str) -> list[tuple[str, str]]:
    """Return (blob sha, path) for every file of the game folder at ref."""
    out = _git("ls-tree", "-r", "-z", ref, "--", GAME_DIR).decode("utf-8")
    files = []
    for entry in out.split("\0"):
        if entry:
            meta, path = entry.split("\t", 1)
            files.append((meta.split()[2], path))
    return files


def _read_blobs(shas: list[str]) -> list[bytes]:
    """Read many blobs with a single git process."""
    out = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=REPO,
        input=("\n".join(shas) + "\n").encode(),
        check=True,
        capture_output=True,
    ).stdout
    blobs = []
    pos = 0
    for _ in shas:
        end = out.index(b"\n", pos)
        size = int(out[pos:end].split()[2])
        blobs.append(out[end + 1 : end + 1 + size])
        pos = end + 1 + size + 1
    return blobs


def _map_path(path: str) -> str | None:
    """Map a repo path to its path inside the zip, or None to skip it."""
    rel = path[len(GAME_DIR) + 1 :]
    if "/" not in rel:
        return f"{PY_DEST}/{rel}" if rel.endswith(".py") else None
    if rel.split("/", 1)[0] in DATA_DIRS:
        return f"{DATA_DEST}/{rel}"
    return None


def main() -> int:
    """Parse arguments and write the patch zip.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="patch version, e.g. 0.2.0")
    parser.add_argument("--ref", default="HEAD", help="git ref to package")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO.parent.parent,
        help="output directory (default: two levels above the repo)",
    )
    args = parser.parse_args()
    if not VERSION_RE.match(args.version):
        print("version must look like 0.2.0", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    zip_path = args.out / f"clash_of_critters_patch_v{args.version}.zip"
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        wanted = [
            (sha, dest)
            for sha, path in _list_files(args.ref)
            if (dest := _map_path(path)) is not None
        ]
        blobs = _read_blobs([sha for sha, _ in wanted])
        for (_, dest), data in zip(wanted, blobs, strict=True):
            zf.writestr(dest, data)
            count += 1
    print(f"{zip_path} ({count} files, {zip_path.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
