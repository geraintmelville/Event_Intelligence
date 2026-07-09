"""
Pydantic validation model for a single cleaned event record.

Validation rules:
  - event_id and name are required; any record missing either is dropped.
  - date must be parseable as YYYY-MM-DD.
  - longitude must be in [-180, 180]; latitude in [-90, 90].
  - capacity must be a positive integer when present.
  - segment, genre and sub_genre are all optional.
"""

from datetime import date as Date
from datetime import time as Time
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


class EventRecord(BaseModel):
    event_id:        str
    name:            str
    date:            Optional[Date] = None
    time:            Optional[Time] = None
    multi_day_event: Optional[bool]  = None
    city:            Optional[str]   = None
    longitude:       Optional[float] = None
    latitude:        Optional[float] = None
    venue:           Optional[str]   = None
    capacity:        Optional[int]   = None
    segment:         str
    genre:           Optional[str]   = None
    sub_genre:       Optional[str]   = None

    # ------------------------------------------------------------------
    # Field-level validators
    # ------------------------------------------------------------------

    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v: object) -> Optional[Date]:
        if v is None or v == '':
            return None
        if isinstance(v, Date):
            return v
        if isinstance(v, str):
            # Accept both "YYYY-MM-DD" and full ISO datetime strings
            return Date.fromisoformat(v[:10])
        raise ValueError(f'Cannot parse date from {v!r}')

    @field_validator('time', mode='before')
    @classmethod
    def parse_time(cls, v: object) -> Optional[Time]:
        if v is None or v == '':
            return None
        if isinstance(v, Time):
            return v
        if isinstance(v, str):
            # Handles both "HH:MM:SS" and "HH:MM"
            parts = v.split(':')
            h, m = int(parts[0]), int(parts[1])
            s = int(parts[2]) if len(parts) > 2 else 0
            return Time(h, m, s)
        raise ValueError(f'Cannot parse time from {v!r}')

    @field_validator('longitude', mode='before')
    @classmethod
    def parse_longitude(cls, v: object) -> Optional[float]:
        if v is None or v == '':
            return None
        val = float(v)
        if not (-180.0 <= val <= 180.0):
            raise ValueError(f'Longitude {val} out of range [-180, 180]')
        return val

    @field_validator('latitude', mode='before')
    @classmethod
    def parse_latitude(cls, v: object) -> Optional[float]:
        if v is None or v == '':
            return None
        val = float(v)
        if not (-90.0 <= val <= 90.0):
            raise ValueError(f'Latitude {val} out of range [-90, 90]')
        return val

    @field_validator('capacity', mode='before')
    @classmethod
    def parse_capacity(cls, v: object) -> Optional[int]:
        if v is None or v == '':
            return None
        val = int(v)
        if val <= 0:
            raise ValueError(f'Capacity must be positive, got {val}')
        return val

    # ------------------------------------------------------------------
    # Cross-field validation
    # ------------------------------------------------------------------

    @model_validator(mode='after')
    def require_id_and_name(self) -> 'EventRecord':
        if not self.event_id or not self.event_id.strip():
            raise ValueError('event_id is required')
        if not self.name or not self.name.strip():
            raise ValueError('name is required')
        return self
