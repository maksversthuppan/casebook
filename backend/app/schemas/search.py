import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.case import CaseSummary
from app.schemas.record import HearingOut, TaskOut


class SearchMatch(BaseModel):
    """Why a Case came back. `snippet` marks the hit with `<<` and `>>` for the
    prose kinds; identifier and party matches carry the value itself."""

    kind: Literal["identifier", "party", "diary", "note"]
    snippet: str | None


class SearchHit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case: CaseSummary
    matches: list[SearchMatch]


class DashboardHearing(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hearing: HearingOut
    case: CaseSummary


class Dashboard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    today: dt.date
    #: The last day counted as "this week", so the screen can say what it means
    #: rather than leaving the reader to guess the window.
    horizon: dt.date
    stale_after_days: int

    hearings: list[DashboardHearing]
    #: Scheduled dates that have passed with nothing recorded against them.
    hearings_passed: list[DashboardHearing]
    tasks: list[TaskOut]
    stale_cases: list[CaseSummary]
