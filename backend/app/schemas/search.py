import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.case import CaseSummary
from app.schemas.record import HearingOut, TaskOut


class SearchMatch(BaseModel):
    """Why a Case came back. `snippet` marks the hit with `<<` and `>>` for the
    prose kinds; identifier, party, advocate and counsel matches carry the
    value itself.

    `advocate` is our own side: the Assignment roster or the Vakalath holder.
    `counsel` is the opposite party's lawyer, as the portal names them - never
    a Counsel row against our own client's side, which is a documented mixup
    rather than opposing counsel (ROADMAP 2026-08-10, ADR-0008).
    """

    kind: Literal["identifier", "party", "diary", "note", "advocate", "counsel"]
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
