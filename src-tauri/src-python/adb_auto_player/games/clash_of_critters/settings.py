"""Clash of Critters Settings Module."""

from typing import Annotated

from adb_auto_player.models.pydantic import TomlSettings
from pydantic import BaseModel, Field

PollIntervalSeconds = Annotated[int, Field(ge=1, le=60)]
StartupWaitSeconds = Annotated[int, Field(ge=5, le=300)]
IdleLimitSeconds = Annotated[int, Field(ge=30, le=900)]
FormationAttempts = Annotated[int, Field(ge=1, le=20)]
WinRatePercent = Annotated[int, Field(ge=0, le=100)]
AdvanceCount = Annotated[int, Field(ge=1, le=1000)]


class AutoBattleSettings(BaseModel):
    """Settings for the Tự Động Chiến Đấu task."""

    poll_interval_seconds: PollIntervalSeconds = Field(
        default=2,
        title="Poll Interval (seconds)",
        description="How often the screen is checked.",
    )
    startup_wait_seconds: StartupWaitSeconds = Field(
        default=30,
        title="Startup Wait (seconds)",
        description="How long to wait for the game to load after restarting it.",
    )
    idle_limit_seconds: IdleLimitSeconds = Field(
        default=120,
        title="Idle Limit (seconds)",
        description="Stop when no known screen was seen for this long.",
    )
    max_formation_attempts: FormationAttempts = Field(
        default=3,
        title="Max Formation Attempts",
        description=(
            "How many times to fight a stage with the prepared formation before "
            "stopping."
        ),
    )


class ArtifactAdventureSettings(BaseModel):
    """Settings for the Phiêu Lưu Cổ Vật task."""

    min_win_rate_percent: WinRatePercent = Field(
        default=10,
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

    auto_battle: AutoBattleSettings = Field(
        default_factory=AutoBattleSettings, title="Tự Động Chiến Đấu"
    )
    artifact_adventure: ArtifactAdventureSettings = Field(
        default_factory=ArtifactAdventureSettings, title="Phiêu Lưu Cổ Vật"
    )
