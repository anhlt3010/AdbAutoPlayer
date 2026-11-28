"""Read-only view of the game's embedded Lua 5.4 state (Lua tables, strings, closures).

The address of the Lua state is derived from the game's own ``igame_getLuaState``
export, so no offset of a specific game build is hard coded; the result is validated.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .errors import UnsupportedBuild
from .memory import DeviceMemory

_LUA_TTHREAD = 8
_LUA_TTABLE = 5
_LUA_TSTRING = 4
_LUA_TNUMBER = 3


@dataclass(frozen=True)
class Proto:
    """A Lua function prototype living in the game's memory."""

    address: int
    code_address: int
    code_size: int  # instructions
    k_address: int
    k_size: int
    consts: tuple  # decoded constants (str/int/float/bool/None/'<tN>')


# -- finding the Lua state ------------------------------------------------------------
def _exported_address(mem: DeviceMemory, base: int, wanted: str) -> int:
    """Address of an exported dynamic symbol of the loaded library at ``base``."""
    head = mem.read(base, 4096)
    phoff = struct.unpack_from("<Q", head, 32)[0]
    entsize, count = struct.unpack_from("<HH", head, 54)
    phdrs = [
        struct.unpack_from("<IIQQQQQQ", head, phoff + i * entsize) for i in range(count)
    ]
    dynamic = next(p for p in phdrs if p[0] == 2)
    block = mem.read(base + dynamic[3], dynamic[6])
    tags: dict[int, int] = {}
    for pos in range(0, len(block), 16):
        tag, val = struct.unpack_from("<QQ", block, pos)
        if not tag:
            break
        tags[tag] = val

    def absolute(value: int) -> int:
        return value if value >= base else base + value

    nsyms = struct.unpack("<II", mem.read(absolute(tags[4]), 8))[1]
    symtab, strtab = absolute(tags[6]), absolute(tags[5])
    mem.prefetch([(symtab, nsyms * 24), (strtab, tags[10])])
    symbols = mem.read(symtab, nsyms * 24)
    strings = mem.read(strtab, tags[10])
    for i in range(nsyms):
        name_off, _info, _other, section, value, _size = struct.unpack_from(
            "<IBBHQQ", symbols, i * 24
        )
        if section and name_off < len(strings):
            if strings[name_off : strings.find(b"\0", name_off)] == wanted.encode():
                return base + value
    raise UnsupportedBuild(f"export {wanted} not found")


def _bl_target(word: int, pc: int) -> int | None:
    if word >> 26 != 0b100101:
        return None
    imm = word & 0x3FFFFFF
    if imm & 0x2000000:
        imm -= 0x4000000
    return pc + imm * 4


def _global_slot(mem: DeviceMemory, getter: int) -> int:
    """Address of the global that a lazy-singleton getter (adrp + ldr) reads."""
    words = struct.unpack("<12I", mem.read(getter, 48))
    page: dict[int, int] = {}
    for i, w in enumerate(words):
        pc = getter + i * 4
        if w & 0x9F000000 == 0x90000000:  # ADRP
            imm = ((w >> 5) & 0x7FFFF) << 2 | ((w >> 29) & 3)
            if imm & (1 << 20):
                imm -= 1 << 21
            page[w & 31] = (pc & ~0xFFF) + (imm << 12)
        elif w & 0xFFC00000 == 0xF9400000:  # LDR Xt, [Xn, #imm]
            rn = (w >> 5) & 31
            if rn in page:
                return page[rn] + ((w >> 10) & 0xFFF) * 8
    raise UnsupportedBuild("cannot decode the Lua state getter")


def locate_lua_state(mem: DeviceMemory) -> int:
    """Return the address of the game's ``lua_State``."""
    base = mem.module_base("libigame.so")
    fn = _exported_address(mem, base, "igame_getLuaState")
    words = struct.unpack("<16I", mem.read(fn, 64))
    calls = [
        t for i, w in enumerate(words) if (t := _bl_target(w, fn + i * 4)) is not None
    ]
    if len(calls) < 2:
        raise UnsupportedBuild("igame_getLuaState has an unexpected shape")
    slot = _global_slot(mem, calls[1])
    engine = mem.u64(mem.u64(slot))
    state = mem.u64(mem.u64(engine + 8) + 8)
    if mem.read(state + 8, 1)[0] & 15 != _LUA_TTHREAD:
        raise UnsupportedBuild("the located Lua state is not a thread")
    return state


# -- reading Lua values -----------------------------------------------------------
class LuaMemory:
    """Decodes Lua objects (strings, tables, prototypes) found in the game's memory."""

    def __init__(self, mem: DeviceMemory) -> None:
        self.mem = mem

    def string(self, addr: int) -> str:
        head = self.mem.read(addr, 24)
        size = head[11] if head[8] & 63 == 4 else struct.unpack_from("<Q", head, 16)[0]
        if size > 1_000_000:
            raise ValueError("invalid string length")
        return self.mem.read(addr + 24, size).decode("utf-8", errors="replace")

    def value(self, data: int, tag: int):
        t = tag & 15
        if t == 0:
            return None
        if t == _LUA_TSTRING:
            return self.string(data)
        if t == _LUA_TNUMBER:
            fmt = "<d" if tag & 16 else "<q"
            return struct.unpack(fmt, struct.pack("<Q", data))[0]
        if t == 1:
            return bool(tag & 16)
        return {"type": t, "tag": tag, "address": data}

    def table(self, addr: int, arrays: bool = True) -> dict:
        """Entries of a Lua table; reference values come back as ``{'address': ...}``."""
        head = self.mem.read(addr, 56)
        if head[8] & 15 != _LUA_TTABLE:
            raise ValueError("not a table")
        lsize, asize = head[11], struct.unpack_from("<I", head, 12)[0]
        array, node = struct.unpack_from("<QQ", head, 16)
        if lsize > 24 or asize > 1_000_000:
            raise ValueError("implausible table size")
        out: dict = {}
        if arrays and array and asize:
            raw = self.mem.read(array, asize * 16)
            for i in range(asize):
                if raw[i * 16 + 8] & 15:
                    out[i + 1] = self.value(
                        struct.unpack_from("<Q", raw, i * 16)[0], raw[i * 16 + 8]
                    )
        raw = self.mem.read(node, (1 << lsize) * 24)
        strings = []  # fetch every string of the table in as few device calls as possible
        for i in range(1 << lsize):
            o = i * 24
            vt, kt = raw[o + 8], raw[o + 9]
            if vt & 15 and kt & 15 == _LUA_TSTRING:
                strings.append((struct.unpack_from("<Q", raw, o + 16)[0], 80))
            if vt & 15 == _LUA_TSTRING:
                strings.append((struct.unpack_from("<Q", raw, o)[0], 80))
        self.mem.prefetch(strings)
        for i in range(1 << lsize):
            o = i * 24
            vt, kt = raw[o + 8], raw[o + 9]
            if not vt & 15 or kt & 15 not in (_LUA_TNUMBER, _LUA_TSTRING):
                continue
            try:
                key = self.value(struct.unpack_from("<Q", raw, o + 16)[0], kt)
                out[key] = self.value(struct.unpack_from("<Q", raw, o)[0], vt)
            except (RuntimeError, ValueError):
                continue
        return out

    def proto_at(self, proto_addr: int) -> Proto:
        """Decode the function prototype stored at ``proto_addr``."""
        head = self.mem.read(proto_addr, 128)
        nk, ncode = struct.unpack_from("<ii", head, 20)
        k_addr, code_addr = struct.unpack_from("<QQ", head, 56)
        raw = self.mem.read(k_addr, nk * 16)
        self.mem.prefetch(
            [
                (struct.unpack_from("<Q", raw, i * 16)[0], 80)
                for i in range(nk)
                if raw[i * 16 + 8] & 15 == _LUA_TSTRING
            ]
        )
        consts = []
        for i in range(nk):
            tag = raw[i * 16 + 8]
            data = struct.unpack_from("<Q", raw, i * 16)[0]
            if tag & 15 in (0, 1, _LUA_TNUMBER, _LUA_TSTRING):
                try:
                    consts.append(self.value(data, tag))
                    continue
                except (RuntimeError, ValueError):
                    pass
            consts.append(f"<t{tag & 15}>")
        return Proto(proto_addr, code_addr, ncode, k_addr, nk, tuple(consts))

    def closure_proto(self, closure_address: int) -> Proto:
        """Prototype (code, constants) of a Lua closure."""
        return self.proto_at(
            struct.unpack_from("<Q", self.mem.read(closure_address, 40), 24)[0]
        )

    def code(self, proto: Proto) -> list[int]:
        """The instruction words of a prototype."""
        return list(
            struct.unpack(
                f"<{proto.code_size}I",
                self.mem.read(proto.code_address, proto.code_size * 4),
            )
        )


class LuaState(LuaMemory):
    """The game's global Lua state."""

    def __init__(self, mem: DeviceMemory) -> None:
        super().__init__(mem)
        self.L = locate_lua_state(mem)
        g = mem.u64(self.L + 24)
        registry = mem.u64(g + 64)
        self.globals_addr = mem.u64(mem.u64(registry + 16) + 16)
        version = self.table(self.globals_addr, arrays=False).get("_VERSION")
        if not (isinstance(version, str) and version.startswith("Lua 5.4")):
            raise UnsupportedBuild(f"unexpected Lua version {version!r}")

    def module(self, name: str) -> dict:
        """The table returned by ``require(name)`` (from ``package.loaded``)."""
        package = self.table(self.globals_addr, arrays=False)["package"]
        loaded = self.table(
            self.table(package["address"], arrays=False)["loaded"]["address"],
            arrays=False,
        )
        if name not in loaded:
            raise UnsupportedBuild(f"Lua module {name} is not loaded")
        return self.table(loaded[name]["address"])
