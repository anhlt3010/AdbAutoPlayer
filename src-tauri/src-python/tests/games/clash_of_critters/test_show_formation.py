"""Tests for the Xem Đội Hình command."""

import logging
import webbrowser
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from adb_auto_player.games.clash_of_critters import main
from adb_auto_player.games.clash_of_critters.formation_view import (
    FormationViewResponse,
    ViewFormation,
    ViewUnit,
)
from adb_auto_player.games.clash_of_critters.main import ClashOfCritters
from adb_auto_player.games.clash_of_critters.settings import Settings


def _response(status: str = "ok") -> FormationViewResponse:
    unit = ViewUnit(
        row=1,
        col=1,
        tatari_id="grass-4",
        evolution_id="grass-4-2",
        name="Mochi",
        tier=2,
        glitter=False,
    )
    formations = [ViewFormation(level=None, units=[unit])] if status == "ok" else []
    return FormationViewResponse(
        status=status,  # type: ignore[arg-type]
        stage="15-50" if status == "ok" else None,
        formations=formations,
        sprites={},
    )


@pytest.fixture
def bot(tmp_path: Path):
    """Game with settings, the page loader and the browser mocked."""
    game = object.__new__(ClashOfCritters)
    settings = Settings()
    game.get_settings = MagicMock(return_value=settings)
    with (
        patch.object(main, "load_formation_view") as load,
        patch.object(main, "webbrowser") as browser,
        patch.object(main.tempfile, "gettempdir", return_value=str(tmp_path)),
    ):
        load.return_value = _response()
        browser.open.return_value = True
        browser.Error = webbrowser.Error
        game.load = load
        game.browser = browser
        game.settings_obj = settings
        yield game


@pytest.mark.parametrize("typed", ["", "   "])
def test_an_empty_stage_reads_it_from_the_screen(bot, typed: str) -> None:
    bot.settings_obj.formation_view.stage = typed
    bot.show_formation()
    bot.load.assert_called_once_with(None)


def test_a_typed_stage_is_stripped_and_used(bot) -> None:
    bot.settings_obj.formation_view.stage = " 15\u201350 "
    bot.show_formation()
    bot.load.assert_called_once_with("15\u201350")


def test_ok_writes_the_page_and_opens_it(
    bot, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    bot.show_formation()
    files = list(tmp_path.glob("coc_formation_*.html"))
    assert len(files) == 1
    assert "15-50" in files[0].name
    assert "Mochi" in files[0].read_text(encoding="utf-8")
    bot.browser.open.assert_called_once_with(files[0].as_uri())
    assert str(files[0]) in " ".join(r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "status", ["no_device", "stage_unreadable", "stage_invalid", "no_formation"]
)
def test_other_statuses_only_log_a_warning(
    bot, tmp_path: Path, caplog: pytest.LogCaptureFixture, status: str
) -> None:
    bot.load.return_value = _response(status)
    bot.show_formation()
    assert list(tmp_path.glob("*.html")) == []
    bot.browser.open.assert_not_called()
    assert [r for r in caplog.records if r.levelno == logging.WARNING]


def test_each_status_has_its_own_message(bot, caplog: pytest.LogCaptureFixture) -> None:
    messages = set()
    for status in ["no_device", "stage_unreadable", "stage_invalid", "no_formation"]:
        caplog.clear()
        bot.load.return_value = _response(status)
        bot.show_formation()
        messages.add(caplog.records[-1].getMessage())
    assert len(messages) == 4


@pytest.mark.parametrize("failure", [False, webbrowser.Error("no browser")])
def test_a_browser_that_cannot_open_is_not_an_error(
    bot, tmp_path: Path, caplog: pytest.LogCaptureFixture, failure: object
) -> None:
    if isinstance(failure, Exception):
        bot.browser.open.side_effect = failure
    else:
        bot.browser.open.return_value = failure
    bot.show_formation()
    page = next(tmp_path.glob("coc_formation_*.html"))
    assert str(page) in " ".join(r.getMessage() for r in caplog.records)
