"""Clash of Critters Settings Module."""

from typing import Annotated

from adb_auto_player.models.pydantic import TomlSettings
from pydantic import BaseModel, Field

CheckIntervalSeconds = Annotated[int, Field(ge=1, le=600)]
StartupWaitSeconds = Annotated[int, Field(ge=5, le=300)]
DislikeIconThreshold = Annotated[int, Field(ge=1, le=30)]
WinRatePercent = Annotated[int, Field(ge=0, le=100)]
AdvanceCount = Annotated[int, Field(ge=1, le=1000)]


class KeepAliveSettings(BaseModel):
    """Settings for the Keep Game Running task."""

    check_interval_seconds: CheckIntervalSeconds = Field(
        default=10,
        title="Check Interval (seconds)",
        description="How often to check that the game is running and battling.",
    )
    dislike_icon_threshold: DislikeIconThreshold = Field(
        default=3,
        title="Dislike Icons For Quick Deploy",
        description=(
            "On the battle preparation screen, press Quick Deploy once when at "
            "least this many red Dislike icons are shown (unfavorable formation)."
        ),
    )
    startup_wait_seconds: StartupWaitSeconds = Field(
        default=30,
        title="Startup Wait (seconds)",
        description="How long to wait for the game to load after restarting it.",
    )


class ArtifactAdventureSettings(BaseModel):
    """Settings for the Phiêu Lưu Cổ Vật task."""

    min_win_rate_percent: WinRatePercent = Field(
        default=40,
        title="Min Win Rate (%)",
        description=(
            "On a fight-or-retreat choice, fight only if the win rate shown on "
            "screen (base + bonus) is at least this value; otherwise retreat. "
            "Retreat is also chosen when the win rate cannot be read."
        ),
    )
    limited_advance_count: AdvanceCount = Field(
        default=100,
        title="Limited Run: Advances",
        description=(
            "Phiêu Lưu Cổ Vật Giới Hạn stops after pressing Tiến Lên this many times."
        ),
    )


class Settings(TomlSettings):
    """Clash of Critters Settings model."""

    keep_alive: KeepAliveSettings = Field(
        default_factory=KeepAliveSettings, title="Tự Chiến Đấu"
    )
    artifact_adventure: ArtifactAdventureSettings = Field(
        default_factory=ArtifactAdventureSettings, title="Phiêu Lưu Cổ Vật"
    )
