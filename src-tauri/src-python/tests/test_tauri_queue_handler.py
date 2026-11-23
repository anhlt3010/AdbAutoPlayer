# ruff: noqa: E402
"""Tests for the log handler that forwards task logs to the Tauri window."""

import logging
import sys
from unittest.mock import MagicMock, patch

# Same stand-ins as test_e2e_flow.py: pytauri and the extension module cannot be
# imported in a plain pytest run.
mock_pytauri = MagicMock()
mock_pytauri.Commands = MagicMock
mock_pytauri.AppHandle = MagicMock
mock_pytauri.Event = MagicMock
mock_pytauri.Listener = MagicMock
mock_pytauri.Manager = MagicMock
mock_pytauri.builder_factory = MagicMock
mock_pytauri.context_factory = MagicMock


class _MockEmitter:
    def emit(self, *args, **kwargs):
        pass


mock_pytauri.Emitter = _MockEmitter

sys.modules.setdefault("pytauri", mock_pytauri)
sys.modules.setdefault("adb_auto_player.ext_mod", MagicMock())

from adb_auto_player.__main__ import OpenCardsEvent, TauriQueueHandler

PROFILE = 3
OPEN_CARDS_EVENT = "formation-viewer:open-cards"


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _event_names(emit: MagicMock) -> list[str]:
    return [call.args[1] for call in emit.call_args_list]


def test_flagged_record_emits_open_cards_event() -> None:
    handle = MagicMock()
    with patch("adb_auto_player.__main__.Emitter.emit") as emit:
        TauriQueueHandler(handle, PROFILE).emit(_record(open_card_teaching=True))
    assert _event_names(emit) == ["log-message", OPEN_CARDS_EVENT]
    payload = emit.call_args_list[1].args[2]
    assert isinstance(payload, OpenCardsEvent)
    assert payload.profile_index == PROFILE


def test_plain_record_emits_no_open_cards_event() -> None:
    with patch("adb_auto_player.__main__.Emitter.emit") as emit:
        TauriQueueHandler(MagicMock(), PROFILE).emit(_record())
    assert _event_names(emit) == ["log-message"]


def test_emit_errors_are_swallowed() -> None:
    with patch("adb_auto_player.__main__.Emitter.emit", side_effect=RuntimeError):
        TauriQueueHandler(MagicMock(), PROFILE).emit(_record(open_card_teaching=True))
