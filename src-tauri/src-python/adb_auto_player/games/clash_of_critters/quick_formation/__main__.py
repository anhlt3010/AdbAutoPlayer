"""Command line for trying the module on a MuMu device (``python -m quick_formation``).

  python -m quick_formation apply <formation.json> [--index N]   deploy a formation
  python -m quick_formation restore                              undo the patch in RAM
  python -m quick_formation status                               is AutoLineup original?

Options: --adb <path to adb.exe>, --serial <host:port> (default 127.0.0.1:7555).
Run it from the folder that contains the ``quick_formation`` folder.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import QuickDeployer, QuickDeployError

# "Triển Khai Nhanh" on the 1080x1920 preparation screen.
QUICK_DEPLOY_POINT = (390, 1800)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quick_formation")
    parser.add_argument("command", choices=("apply", "restore", "status"))
    parser.add_argument(
        "formation",
        nargs="?",
        help="formation file (tatari_formations/<chapter>/<stage>.json)",
    )
    parser.add_argument(
        "--index", type=int, default=0, help="which formation of the file"
    )
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", default="127.0.0.1:7555")
    args = parser.parse_args(argv)

    def shell(command: str) -> bytes:
        return subprocess.check_output(
            [args.adb, "-s", args.serial, "shell", command], timeout=60
        )

    def press() -> None:
        subprocess.check_call(
            [
                args.adb,
                "-s",
                args.serial,
                "shell",
                "input",
                "tap",
                *map(str, QUICK_DEPLOY_POINT),
            ]
        )

    deployer = QuickDeployer(shell, press, state_dir=Path.cwd())
    try:
        if args.command == "status":
            print(
                "AutoLineup is original"
                if deployer.is_original()
                else "AutoLineup is patched (restore it)"
            )
            return 0
        if args.command == "restore":
            print(
                "restored"
                if deployer.restore()
                else "no original recorded (restart the game)"
            )
            return 0
        if not args.formation:
            parser.error("apply needs a formation file")
        data = json.loads(Path(args.formation).read_text(encoding="utf-8"))
        result = deployer.deploy(data["formations"][args.index]["units"])
        if result.verified:
            print(f"deployed {result.count}/{result.needed}")
        else:
            print(
                f"pressed Quick Deploy for {result.needed} cells (not verified: look at the screen; "
                "the game must be on the battle preparation screen)"
            )
    except QuickDeployError as error:
        print(f"quick deploy not possible: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
