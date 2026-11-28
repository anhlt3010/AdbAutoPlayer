"""Offline tests of the quick formation deploy (no device needed)."""

import base64
import re
import tempfile
import unittest
from pathlib import Path

from adb_auto_player.games.clash_of_critters.quick_formation import (
    DeployResult,
    QuickDeployer,
    TatariMap,
    UnknownTatari,
    UnsupportedLayout,
    cell_for,
)
from adb_auto_player.games.clash_of_critters.quick_formation import luabc as bc
from adb_auto_player.games.clash_of_critters.quick_formation.memory import DeviceMemory
from adb_auto_player.games.clash_of_critters.quick_formation.patcher import build_code


class FakeDevice:
    """A tiny fake of the device shell: one process with a flat memory image."""

    def __init__(self) -> None:
        self.memory = bytearray(range(256)) * 128  # 32 KB, 8 pages
        self.commands: list[str] = []

    def __call__(self, command: str) -> str:
        self.commands.append(command)
        if command.startswith("pidof"):
            return "4242\n"
        inner = re.match(r'su -c "(.*)"$', command, re.S).group(1)
        if inner.startswith("cat /proc/4242/maps"):
            return "10000-18000 r-xp 00000000 00:00 0 /data/app/lib/libigame.so\n"
        if "base64 -d" in inner:
            b64, seek = re.search(r"echo (\S+) \|.*seek=(\d+)", inner).groups()
            data = base64.b64decode(b64)
            self.memory[
                int(seek) * 4 - 0x10000 : int(seek) * 4 - 0x10000 + len(data)
            ] = data
            return ""
        out = []
        for part in re.split(r"; (?=echo @)", inner):
            marker = re.match(r"echo @(\w+)", part).group(1)
            skip, count = (
                int(x) for x in re.search(r"skip=(\d+) count=(\d+)", part).groups()
            )
            start = skip * 4096 - 0x10000
            chunk = bytes(self.memory[start : start + count * 4096])
            out.append(f"@{marker}")
            out += [
                " " + " ".join(f"{b:02x}" for b in chunk[i : i + 16])
                for i in range(0, len(chunk), 16)
            ]
        return "\n".join(out)


class CellTests(unittest.TestCase):
    def test_battle_grid(self):
        self.assertEqual(cell_for(1, 5), (5, 5))  # top row, right column
        self.assertEqual(cell_for(5, 1), (1, 1))  # bottom row, left column
        self.assertEqual(cell_for(3, 3), (3, 3))

    def test_other_layouts_are_refused(self):
        with self.assertRaises(UnsupportedLayout):
            cell_for(1, 1, "dojo")
        with self.assertRaises(ValueError):
            cell_for(6, 1)


class MappingTests(unittest.TestCase):
    def test_rank_rule_and_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            mapping = TatariMap(override_file=Path(tmp, "o.json"))
            self.assertEqual(mapping.tid("rock-5"), 24)  # Punchimp / Monkey
            self.assertEqual(mapping.tid("fire-9"), 42)  # Tindercub / FireTiger
            mapping.set_override("fire-9", 99)
            self.assertEqual(
                TatariMap(override_file=Path(tmp, "o.json")).tid("fire-9"), 99
            )
            mapping.clear_override("fire-9")
            self.assertEqual(mapping.tid("fire-9"), 42)
            with self.assertRaises(UnknownTatari):
                mapping.tid("fire-99")

    def test_every_element_has_14_species(self):
        counts = {}
        for key, tid in TatariMap().items().items():
            counts.setdefault(key.split("-")[0], set()).add(tid)
        self.assertEqual(
            {k: len(v) for k, v in counts.items()},
            {e: 14 for e in ("water", "fire", "grass", "rock", "lightning")},
        )


class CodeTests(unittest.TestCase):
    def test_jumps_land_where_intended(self):
        cells = [(24, 3, 5), (12, 1, 1), (7, 5, 2)]
        code = build_code(cells)
        names = [bc.OPS[w & 127] for w in code]
        self.assertEqual(names.count("SETI"), 2 * len(cells))
        prep, loop = names.index("FORPREP"), names.index("FORLOOP")
        self.assertEqual(names[-1], "RETURN0")
        self.assertEqual(
            prep + 1 + (code[prep] >> 15) + 1, len(code) - 1
        )  # empty list skips to RETURN0
        self.assertEqual(
            loop + 1 - (code[loop] >> 15), prep + 1
        )  # loop returns to the body
        jmp = names.index("JMP")
        self.assertEqual(
            jmp + 1 + (code[jmp] >> 7) - ((1 << 24) - 1), loop
        )  # "no cell" goes to FORLOOP

    def test_fits_in_the_original_function(self):
        self.assertLessEqual(len(build_code([(i + 1, 1, 1) for i in range(15)])), 177)

    def test_tid_must_fit_an_immediate(self):
        with self.assertRaises(ValueError):
            build_code([(300, 1, 1)])


class MemoryTests(unittest.TestCase):
    def test_read_write_roundtrip_and_batching(self):
        device = FakeDevice()
        mem = DeviceMemory(device)
        mem.attach()
        self.assertEqual(mem.module_base("libigame.so"), 0x10000)
        self.assertEqual(mem.read(0x10000 + 5, 4), bytes([5, 6, 7, 8]))
        mem.prefetch([(0x10000 + 4096 * 3, 8), (0x10000 + 4096 * 6, 8)])
        before = len(device.commands)
        self.assertEqual(mem.read(0x10000 + 4096 * 6 + 1, 2), bytes([1, 2]))
        self.assertEqual(len(device.commands), before)  # served from the cache
        mem.write(0x10000 + 64, bytes([9, 9, 9, 9, 8, 8, 8, 8]))
        self.assertEqual(mem.read(0x10000 + 64, 8), bytes([9, 9, 9, 9, 8, 8, 8, 8]))

    def test_unaligned_write_is_refused(self):
        mem = DeviceMemory(FakeDevice())
        mem.attach()
        with self.assertRaises(ValueError):
            mem.write(0x10001, b"1234")


class DeployerTests(unittest.TestCase):
    def test_cells_from_units(self):
        deployer = QuickDeployer(FakeDevice(), lambda: None)
        units = [
            {"row": 1, "col": 5, "tatari_id": "water-12"},
            {"row": 5, "col": 1, "tatari_id": "rock-4"},
        ]
        self.assertEqual(deployer.cells(units), [(56, 5, 5), (19, 1, 1)])

    def test_unverified_result_is_never_complete(self):
        self.assertFalse(DeployResult(0, 15, verified=False).complete)
        self.assertTrue(DeployResult(15, 15).complete)
        self.assertFalse(DeployResult(14, 15).complete)


if __name__ == "__main__":
    unittest.main()
