"""Tests for the Clash of Critters auto battle settings."""

import pytest
from adb_auto_player.games.clash_of_critters.settings import (
    AutoBattleSettings,
    Settings,
)
from pydantic import ValidationError


def test_defaults() -> None:
    settings = AutoBattleSettings()
    assert settings.poll_interval_seconds == 2
    assert settings.startup_wait_seconds == 30
    assert settings.idle_limit_seconds == 300
    assert settings.max_formation_attempts == 3
    assert settings.keep_formation_after_win is False
    assert settings.tray_settle_poll_seconds == 0.5


def test_bounds_rejected() -> None:
    with pytest.raises(ValidationError):
        AutoBattleSettings(max_formation_attempts=0)
    with pytest.raises(ValidationError):
        AutoBattleSettings(idle_limit_seconds=10)
    with pytest.raises(ValidationError):
        AutoBattleSettings(tray_settle_poll_seconds=0.05)
    with pytest.raises(ValidationError):
        AutoBattleSettings(tray_settle_poll_seconds=6)


def test_old_keep_alive_removed() -> None:
    assert "keep_alive" not in Settings.model_fields
    assert "auto_battle" in Settings.model_fields


def test_card_teaching_wait_default() -> None:
    assert AutoBattleSettings().card_teaching_wait_seconds == 180


def test_card_teaching_wait_is_bounded() -> None:
    with pytest.raises(ValidationError):
        AutoBattleSettings(card_teaching_wait_seconds=9)
    with pytest.raises(ValidationError):
        AutoBattleSettings(card_teaching_wait_seconds=3601)
