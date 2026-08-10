import uuid

from pydantic import BaseModel, ConfigDict, Field, computed_field


class CourtIn(BaseModel):
    """Creating a Court by hand yields a provisional one: a name and nothing else.

    Portal values are not accepted here on purpose. They are recorded at Ingestion
    from what the advocate actually chose in the portal's own dropdowns, so that
    they cannot be mistyped into something no search will match (ADR-0005).
    """

    name: str = Field(min_length=1, max_length=300)


class CourtOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    portal_state: str | None
    portal_district: str | None
    portal_establishment: str | None

    @computed_field
    @property
    def is_complete(self) -> bool:
        """A complete Court can be searched on DCMS; a provisional one cannot."""
        return bool(self.portal_state and self.portal_district and self.portal_establishment)
