"""Domain primitives: scalar aliases + small value objects.

Scalar aliases may be promoted to proper value objects later without changing imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from .enums import AreaRole

if TYPE_CHECKING:
    from .enums import AreaType

type CountryCode = str
type CatalogNumber = str
type Barcode = str
type Mbid = str
type Isrc = str
type DurationMs = int


@dataclass(frozen=True)
class PartialDate:
    year: int | None = None
    month: int | None = None
    day: int | None = None

    @property
    def as_date(self) -> date | None:
        if self.year is None:
            return None
        month = self.month or 1
        day = self.day or 1
        return date(self.year, month, day)

    def __composite_values__(self) -> tuple[int | None, int | None, int | None]:
        """For SQLAlchemy composite columns (adapter-side convenience)."""
        return (self.year, self.month, self.day)


@dataclass(frozen=True)
class LifeSpan:
    begin: PartialDate | None = None
    end: PartialDate | None = None
    ended: bool | None = None


@dataclass(frozen=True)
class Area:
    name: str
    area_type: AreaType | None = None
    role: AreaRole = AreaRole.PRIMARY
    country_codes: tuple[CountryCode, ...] = field(default_factory=tuple)
