"""Lua 5.4 bytecode helpers: instruction encoding and a small disassembler."""

OPS = (
    "MOVE LOADI LOADF LOADK LOADKX LOADFALSE LFALSESKIP LOADTRUE LOADNIL GETUPVAL "
    "SETUPVAL GETTABUP GETTABLE GETI GETFIELD SETTABUP SETTABLE SETI SETFIELD NEWTABLE "
    "SELF ADDI ADDK SUBK MULK MODK POWK DIVK IDIVK BANDK BORK BXORK SHRI SHLI ADD SUB "
    "MUL MOD POW DIV IDIV BAND BOR BXOR SHL SHR MMBIN MMBINI MMBINK UNM BNOT NOT LEN "
    "CONCAT CLOSE TBC JMP EQ LT LE EQK EQI LTI LEI GTI GEI TEST TESTSET CALL TAILCALL "
    "RETURN RETURN0 RETURN1 FORLOOP FORPREP TFORPREP TFORCALL TFORLOOP SETLIST CLOSURE "
    "VARARG VARARGPREP EXTRAARG"
).split()

_OP = {name: i for i, name in enumerate(OPS)}
_SBX = 65535  # offset of a signed Bx
_SJ = (1 << 24) - 1  # offset of a signed jump


def op(name: str) -> int:
    """Numeric opcode of an instruction name."""
    return _OP[name]


def abc(name: str, a: int = 0, b: int = 0, c: int = 0, k: int = 0) -> int:
    """Encode an iABC instruction."""
    return _OP[name] | (a << 7) | (k << 15) | (b << 16) | (c << 24)


def abx(name: str, a: int, bx: int) -> int:
    """Encode an iABx instruction (LOADK, FORLOOP, FORPREP...)."""
    return _OP[name] | (a << 7) | (bx << 15)


def asbx(name: str, a: int, sbx: int) -> int:
    """Encode an iAsBx instruction (LOADI)."""
    return _OP[name] | (a << 7) | ((sbx + _SBX) << 15)


def sj(name: str, offset: int) -> int:
    """Encode an isJ instruction (JMP); offset is relative to the next instruction."""
    return _OP[name] | ((offset + _SJ) << 7)


def disassemble(words, consts=()) -> list[str]:
    """Return one readable line per instruction (debugging aid)."""
    lines = []
    for i, w in enumerate(words):
        o, a, k = w & 127, (w >> 7) & 255, (w >> 15) & 1
        b, c, bx = (w >> 16) & 255, (w >> 24) & 255, w >> 15
        name = OPS[o] if o < len(OPS) else f"OP{o}"
        extra = ""
        if name == "LOADK" and bx < len(consts):
            extra = repr(consts[bx])
        elif name in ("GETFIELD", "GETTABUP") and c < len(consts):
            extra = repr(consts[c])
        elif name == "SELF" and k and c < len(consts):
            extra = repr(consts[c])
        elif name == "LOADI":
            extra = str(bx - _SBX)
        elif name == "JMP":
            extra = f"-> {i + 1 + (w >> 7) - _SJ}"
        lines.append(f"{i:3d} {name:<9} A={a:<3} B={b:<3} C={c:<3} k={k} {extra}")
    return lines
