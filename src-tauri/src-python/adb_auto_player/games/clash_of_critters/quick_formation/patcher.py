"""Install a formation into the game by rewriting one Lua function in RAM.

What it does
------------
The battle preparation screen (``Src.UI.Battle.View.StageBattlePrepareView``) has a
Quick Deploy handler, ``AutoLineup``. While a formation is installed that function
(only its bytecode in the game's memory, no game file is touched) becomes::

    self:OnClickClearAllUnit()
    pets = self:GetAutoPetList()
    for each pet in pets whose species (``pet.tid``) is in the formation:
        self:AddUnitToGrid(pet, x[tid], y[tid], true, false)

so pressing the game's own "Triển Khai Nhanh" button puts every unit on its cell at
once. ``AddUnitToGrid`` is the call the game itself makes for each unit of its auto
lineup. Nothing is injected into the process and no debugger is attached.

The change lives in RAM only: a game restart removes it, and ``restore()`` puts the
original bytecode back (the deployer does that right after each deploy so the real
Quick Deploy button keeps working normally).
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from . import luabc as bc
from .errors import UnsupportedBuild
from .luastate import LuaMemory, LuaState, Proto
from .memory import DeviceMemory

MODULE = "Src.UI.Battle.View.StageBattlePrepareView"
MAX_CELLS = 15
_SLOT_TID, _SLOT_ADD = 15, 16  # constant slots reused for 'tid' and 'AddUnitToGrid'
_FUNCTIONS = ("AutoLineup", "BuildAutoLineupGSDict", "AutoLineupAddUnit")


def build_code(cells: list[tuple[int, int, int]]) -> list[int]:
    """Bytecode of the replacement ``AutoLineup``.

    Args:
        cells: ``(tid, x, y)`` per unit; ``tid`` is the game species id (1..255), ``x`` the
            column and ``y`` the row of the game's grid.

    Returns:
        The instruction words. Constants used: K1 ``OnClickClearAllUnit``, K5
        ``GetAutoPetList``, K15 ``tid``, K16 ``AddUnitToGrid``.
    """
    code = [
        bc.abc("SELF", 4, 0, 1, 1),
        bc.abc("CALL", 4, 2, 1),  # self:OnClickClearAllUnit()
        bc.abc("SELF", 1, 0, 5, 1),
        bc.abc("CALL", 1, 2, 2),  # R1 = self:GetAutoPetList()
        bc.abc("NEWTABLE", 2),
        bc.op("EXTRAARG"),  # R2 = {}  (x by tid)
        bc.abc("NEWTABLE", 3),
        bc.op("EXTRAARG"),  # R3 = {}  (y by tid)
    ]
    for tid, x, y in cells:
        if not 1 <= tid <= 255:
            raise ValueError(f"tid {tid} does not fit a SETI immediate")
        code += [
            bc.asbx("LOADI", 4, x),
            bc.abc("SETI", 2, tid, 4),
            bc.asbx("LOADI", 4, y),
            bc.abc("SETI", 3, tid, 4),
        ]
    loop = len(code)
    code += [
        bc.asbx("LOADI", 5, 1),
        bc.abc("LEN", 6, 1),
        bc.asbx("LOADI", 7, 1),
        0,
    ]  # 0: FORPREP
    body = len(code)
    code += [
        bc.abc("GETTABLE", 9, 1, 8),
        bc.abc("GETFIELD", 10, 9, _SLOT_TID),  # pet, pet.tid
        bc.abc("GETTABLE", 11, 2, 10),  # x[tid]
        bc.abc("TEST", 11, 0, 0, 0),
        0,  # 0: JMP past the call
        bc.abc("GETFIELD", 12, 0, _SLOT_ADD),
        bc.abc("MOVE", 13, 0),
        bc.abc("MOVE", 14, 9),
        bc.abc("MOVE", 15, 11),
        bc.abc("GETTABLE", 16, 3, 10),
        bc.abc("LOADTRUE", 17),
        bc.abc("LOADFALSE", 18),
        bc.abc("CALL", 12, 7, 1),  # AddUnitToGrid
    ]
    jmp = body + 4
    end = len(code)
    code += [0, bc.abc("RETURN0")]  # 0: FORLOOP
    code[loop + 3] = bc.abx("FORPREP", 5, end - (loop + 3) - 1)
    code[jmp] = bc.sj("JMP", end - (jmp + 1))
    code[end] = bc.abx("FORLOOP", 5, end + 1 - body)
    return code


def _verified(protos: dict[str, Proto]) -> bool:
    auto, gs, add = (protos[n] for n in _FUNCTIONS)
    return (
        auto.consts[1:2] == ("OnClickClearAllUnit",)
        and auto.consts[3:4] == ("battleController",)
        and auto.consts[5:6] == ("GetAutoPetList",)
        and gs.consts[10:11] == ("tid",)
        and add.consts[6:7] == ("AddUnitToGrid",)
        and auto.code_size >= 4 * MAX_CELLS + 30
    )


class FormationPatcher:
    """Finds ``AutoLineup`` in the running game and swaps its code.

    The addresses it finds (and the original code) are kept per game process, in memory
    and, when ``state_dir`` is given, in a small json file so that a new Python process
    can skip the slow search while the same game process is still running.
    """

    def __init__(self, mem: DeviceMemory, state_dir: Path | None = None) -> None:
        self.mem = mem
        self._state_file = (
            Path(state_dir, "quick_formation_state.json") if state_dir else None
        )
        self._lm = LuaMemory(mem)
        self._pid = 0
        self._protos: dict[str, Proto] | None = None
        self._pristine: dict | None = None

    # -- state file --------------------------------------------------------------
    def _load_state(self) -> dict:
        if self._state_file and self._state_file.exists():
            try:
                state = json.loads(self._state_file.read_text(encoding="utf-8"))
                if state.get("pid") == self._pid:
                    return state
            except (OSError, ValueError):
                pass
        return {"pid": self._pid}

    def _save_state(self, state: dict) -> None:
        if self._state_file:
            self._state_file.write_text(json.dumps(state), encoding="utf-8")

    # -- resolving ---------------------------------------------------------------
    def _resolve(self) -> None:
        pid = self.mem.attach()
        if self._protos is not None and pid == self._pid:
            return
        self._pid, self._protos = pid, None
        state = self._load_state()
        saved = state.get("protos")
        if saved:  # the same game process as before: skip the slow search
            try:
                protos = {n: self._lm.proto_at(saved[n]) for n in _FUNCTIONS}
                if _verified(protos):
                    self._protos = protos
            except (KeyError, RuntimeError, ValueError, struct.error):
                self._protos = None
        if self._protos is None:
            lua = LuaState(self.mem)
            module = lua.module(MODULE)
            protos = {n: lua.closure_proto(module[n]["address"]) for n in _FUNCTIONS}
            if not _verified(protos):
                raise UnsupportedBuild(
                    "AutoLineup does not look like the verified game build"
                )
            self._protos = protos
            state["protos"] = {n: p.address for n, p in protos.items()}
        auto = self._protos["AutoLineup"]
        words = self._lm.code(auto)
        if words[0] & 127 == bc.op("EQK"):  # the original function starts with EQK
            state["pristine"] = {
                "code": struct.pack(f"<{len(words)}I", *words).hex(),
                "k": self.mem.read(auto.k_address + _SLOT_TID * 16, 32).hex(),
            }
        self._pristine = state.get("pristine")
        self._save_state(state)

    # -- public API ----------------------------------------------------------------
    def install(self, cells: list[tuple[int, int, int]]) -> int:
        """Rewrite ``AutoLineup`` for these ``(tid, x, y)`` cells; returns the code size."""
        if len(cells) > MAX_CELLS:
            raise ValueError(f"at most {MAX_CELLS} cells")
        self._resolve()
        assert self._protos
        auto, gs, add = (self._protos[n] for n in _FUNCTIONS)
        words = build_code(cells)
        if len(words) > auto.code_size:
            raise UnsupportedBuild("the formation does not fit in AutoLineup")
        consts = self.mem.read(gs.k_address + 10 * 16, 16) + self.mem.read(
            add.k_address + 6 * 16, 16
        )
        self.mem.write(auto.k_address + _SLOT_TID * 16, consts)
        self.mem.write(auto.code_address, struct.pack(f"<{len(words)}I", *words))
        return len(words)

    def restore(self) -> bool:
        """Put the original ``AutoLineup`` back; False if no original was recorded."""
        self._resolve()
        assert self._protos
        if not self._pristine:
            return False
        auto = self._protos["AutoLineup"]
        self.mem.write(auto.code_address, bytes.fromhex(self._pristine["code"]))
        self.mem.write(
            auto.k_address + _SLOT_TID * 16, bytes.fromhex(self._pristine["k"])
        )
        return True

    def is_original(self) -> bool:
        """True when ``AutoLineup`` currently has its original code."""
        self._resolve()
        assert self._protos
        return bool(self._lm.code(self._protos["AutoLineup"])[0] & 127 == bc.op("EQK"))
