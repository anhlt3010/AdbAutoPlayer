"""Read and write the memory of the game process through a root device shell.

Only text goes over the shell (hex out with ``od``, base64 in), so nothing depends on
binary-safe adb transport. Reads are cached by 4 KB page and many pages are fetched in
one device call (``prefetch``), because one adb call costs far more than the data.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable, Iterable

from .errors import GameNotRunning, RootUnavailable

PACKAGE = "com.farlightgames.pgame.gp.vn"
# Runs one shell command on the device and returns its stdout.
Shell = Callable[[str], "bytes | str"]

_PAGE = 4096
_READ_AHEAD = 3  # extra pages fetched after a missing page
_RUNS_PER_CALL = 30  # dd commands joined into one device call
_PAGES_PER_CALL = (
    32  # pages returned by one device call (40 runs / ~80 pages failed on MuMu)
)


def _text(out) -> str:
    return (
        out.decode("utf-8", "replace")
        if isinstance(out, (bytes, bytearray))
        else str(out)
    )


class DeviceMemory:
    """Memory of one game process (call ``attach`` again after the game restarts)."""

    def __init__(self, shell: Shell, package: str = PACKAGE, su: str = "su -c") -> None:
        self._shell = shell
        self.package = package
        self._su = su
        self.pid = 0
        self._maps: list[tuple[int, int, int, str]] = []
        self._pages: dict[int, bytes] = {}

    # -- process -----------------------------------------------------------------
    def _root(self, command: str) -> str:
        return _text(self._shell(f'{self._su} "{command}"'))

    def attach(self) -> int:
        """Find the game process and its memory map; returns the pid."""
        out = _text(self._shell(f"pidof {self.package}")).strip().split()
        if not out:
            raise GameNotRunning(f"{self.package} is not running")
        pid = int(out[0])
        if pid == self.pid and self._maps:
            return pid
        maps = self._root(f"cat /proc/{pid}/maps")
        if "-" not in maps:
            raise RootUnavailable(
                "cannot read /proc/<pid>/maps as root (is su available?)"
            )
        self._pages.clear()
        self.pid = pid
        self._maps = []
        for line in maps.splitlines():
            p = line.split()
            if len(p) < 3 or "-" not in p[0]:
                continue
            start, end = (int(x, 16) for x in p[0].split("-"))
            self._maps.append((start, end, int(p[2], 16), p[5] if len(p) > 5 else ""))
        return pid

    def module_base(self, name: str) -> int:
        """Base address of a loaded shared library (its smallest offset-0 mapping)."""
        found = [m for m in self._maps if m[3].endswith("/" + name) and m[2] == 0]
        if not found:
            raise GameNotRunning(f"{name} is not mapped")
        return min(found, key=lambda m: m[1] - m[0])[0]

    # -- reading -----------------------------------------------------------------
    def _fetch_pages(self, pages: Iterable[int]) -> None:
        """Fetch pages (page base addresses) not cached yet, many per device call."""
        missing = sorted({p for p in pages if p not in self._pages})
        runs: list[list[int]] = []
        for page in missing:
            if runs and page == runs[-1][0] + runs[-1][1] * _PAGE:
                runs[-1][1] += 1
            else:
                runs.append([page, 1])
        batches: list[list[list[int]]] = []
        pages_in_batch = 0
        for (
            run
        ) in runs:  # a device call that returns too much text fails, so cap its size
            if (
                not batches
                or pages_in_batch + run[1] > _PAGES_PER_CALL
                or len(batches[-1]) >= _RUNS_PER_CALL
            ):
                batches.append([])
                pages_in_batch = 0
            batches[-1].append(run)
            pages_in_batch += run[1]
        for batch in batches:
            command = "; ".join(
                f"echo @{base:x}; dd if=/proc/{self.pid}/mem bs={_PAGE} skip={base // _PAGE} "
                f"count={count} 2>/dev/null | od -An -v -tx1"
                for base, count in batch
            )
            current, chunks = None, {}
            for line in self._root(command).splitlines():
                if line.startswith("@"):
                    current = int(line[1:], 16)
                    chunks[current] = []
                elif current is not None:
                    chunks[current].append(re.sub(r"\s+", "", line))
            for base, count in batch:
                data = bytes.fromhex("".join(chunks.get(base, [])))
                for k in range(count):
                    part = data[k * _PAGE : (k + 1) * _PAGE]
                    if len(part) == _PAGE:
                        self._pages[base + k * _PAGE] = part

    def prefetch(self, ranges: Iterable[tuple[int, int]]) -> None:
        """Load the pages covering ``(address, size)`` ranges in as few device calls as possible."""
        pages = set()
        for addr, size in ranges:
            for page in range(addr - addr % _PAGE, addr + max(size, 1), _PAGE):
                pages.add(page)
        self._fetch_pages(pages)

    def read(self, addr: int, size: int) -> bytes:
        """Read ``size`` bytes at ``addr`` (RuntimeError if the memory is unreadable)."""
        out = bytearray()
        while size > 0:
            page = addr - addr % _PAGE
            if page not in self._pages:
                self._fetch_pages(page + i * _PAGE for i in range(_READ_AHEAD + 1))
                if page not in self._pages:
                    self._fetch_pages([page])
                if page not in self._pages:
                    raise RuntimeError(f"unreadable memory at {addr:#x}")
            offset = addr - page
            take = min(size, _PAGE - offset)
            out += self._pages[page][offset : offset + take]
            addr += take
            size -= take
        return bytes(out)

    def u64(self, addr: int) -> int:
        """Read a little-endian 64-bit value."""
        return int.from_bytes(self.read(addr, 8), "little")

    # -- writing -----------------------------------------------------------------
    def write(self, addr: int, data: bytes) -> None:
        """Write ``data`` (4-byte aligned) and verify it by reading it back."""
        if addr % 4 or len(data) % 4:
            raise ValueError("writes must be 4-byte aligned")
        for i in range(0, len(data), 96):
            b64 = base64.b64encode(data[i : i + 96]).decode()
            self._root(
                f"echo {b64} | base64 -d | dd of=/proc/{self.pid}/mem "
                f"bs=4 seek={(addr + i) // 4} conv=notrunc 2>/dev/null"
            )
        for page in range(addr - addr % _PAGE, addr + len(data), _PAGE):
            self._pages.pop(page, None)
        if self.read(addr, len(data)) != data:
            raise RuntimeError(f"memory write at {addr:#x} did not stick")
