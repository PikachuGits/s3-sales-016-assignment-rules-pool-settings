"""Pydantic schemas for the sales assignment configuration API.

Validation is intentionally split in two layers:

* pure shape/range/cross-field checks live here and produce FastAPI's native
  422 response;
* site-scoped checks that need data (name uniqueness, consultant membership)
  live in the router and also return 422/409.

Keeping the first layer pure makes it reusable by unit tests without a
database.
"""

from __future__ import annotations

import re
from datetime import datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import CONDITION_ENUMS

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_STRATEGY = Literal["round_robin", "least_holding", "fixed_user"]


class WorkHourWindow(BaseModel):
    """One contiguous working-time window on a weekday."""

    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(
        ge=0,
        le=6,
        description="0 = Monday … 6 = Sunday (ISO weekday order)",
    )
    start: str = Field(
        pattern=_TIME_RE.pattern,
        description="24-hour local time, HH:MM",
        examples=["09:00"],
    )
    end: str = Field(
        pattern=_TIME_RE.pattern,
        description="24-hour local time, HH:MM; must be later than start",
        examples=["18:00"],
    )

    @model_validator(mode="after")
    def _start_before_end(self) -> "WorkHourWindow":
        if time.fromisoformat(self.start) >= time.fromisoformat(self.end):
            raise ValueError("work_hours window must satisfy start < end")
        return self


class AssignmentRuleCreate(BaseModel):
    """Payload for ``POST /api/sales/assignment-rules``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64, examples=["华东制造业轮询"])
    strategy: _STRATEGY = Field(examples=["round_robin"])
    conditions: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Condition object. Keys and literals must come from the v1 "
            "condition vocabulary documented in README §5."
        ),
        examples=[{"region": ["east"], "industry": ["manufacturing"]}],
    )
    member_user_ids: list[UUID] = Field(
        min_length=1,
        description="Consultants of this site; fixed_user requires exactly one.",
    )
    work_hours: list[WorkHourWindow] = Field(min_length=1)
    priority: int = Field(default=100, ge=0, examples=[10])
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("conditions")
    @classmethod
    def _validate_conditions(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for key, literals in value.items():
            allowed = CONDITION_ENUMS.get(key)
            if allowed is None:
                raise ValueError(
                    f"unknown condition field {key!r}; "
                    f"allowed fields: {sorted(CONDITION_ENUMS)}"
                )
            if not literals:
                raise ValueError(f"condition {key!r} must contain at least one literal")
            unknown = [item for item in literals if item not in allowed]
            if unknown:
                raise ValueError(
                    f"condition {key!r} has invalid literal(s) {unknown}; "
                    f"allowed: {list(allowed)}"
                )
            if len(set(literals)) != len(literals):
                raise ValueError(f"condition {key!r} contains duplicate literals")
        return value

    @model_validator(mode="after")
    def _strategy_member_count(self) -> "AssignmentRuleCreate":
        ids = self.member_user_ids
        if len(set(ids)) != len(ids):
            raise ValueError("member_user_ids must not contain duplicates")
        if self.strategy == "fixed_user":
            if len(ids) != 1:
                raise ValueError(
                    "fixed_user strategy requires exactly one member_user_id"
                )
        elif len(ids) < 1:
            raise ValueError(
                f"{self.strategy} strategy requires at least one member_user_id"
            )
        return self

    @model_validator(mode="after")
    def _work_windows_do_not_overlap(self) -> "AssignmentRuleCreate":
        by_day: dict[int, list[tuple[time, time]]] = {}
        for window in self.work_hours:
            by_day.setdefault(window.weekday, []).append(
                (time.fromisoformat(window.start), time.fromisoformat(window.end))
            )
        for weekday, ranges in by_day.items():
            ranges.sort()
            for previous, current in zip(ranges, ranges[1:]):
                if current[0] < previous[1]:
                    raise ValueError(
                        f"work_hours windows overlap on weekday {weekday}"
                    )
        return self


class AssignmentRuleUpdate(BaseModel):
    """Payload for ``PUT /api/sales/assignment-rules/{id}``.

    Every field is optional; the router merges the patch with the stored rule
    and re-runs all create-time validators, so invariants cannot be bypassed
    by updating a single field.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    strategy: _STRATEGY | None = None
    conditions: dict[str, list[str]] | None = None
    member_user_ids: list[UUID] | None = Field(default=None, min_length=1)
    work_hours: list[WorkHourWindow] | None = Field(default=None, min_length=1)
    priority: int | None = Field(default=None, ge=0)
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("member_user_ids")
    @classmethod
    def _dedupe_members(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("member_user_ids must not contain duplicates")
        return value


class RuleToggle(BaseModel):
    """Optional explicit target state for ``POST .../toggle``."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = Field(
        default=None,
        description="Omit to flip the current state; set it to force a state.",
    )


class ReorderItem(BaseModel):
    """One rule's new priority in a reorder request."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    priority: int = Field(ge=0)


class ReorderPayload(BaseModel):
    """Payload for ``POST /api/sales/assignment-rules/reorder``."""

    model_config = ConfigDict(extra="forbid")

    items: list[ReorderItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "ReorderPayload":
        ids = [item.id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("reorder items must not contain duplicate rule ids")
        return self


class PoolSettingsValues(BaseModel):
    """The five public-pool parameters, with work-order defaults and ranges."""

    model_config = ConfigDict(extra="forbid")

    recycle_days: int = Field(default=7, ge=3, le=30)
    recycle_warn_days: int = Field(default=5, ge=1)
    daily_claim_limit: int = Field(default=10, ge=1)
    holding_limit: int = Field(default=150, ge=1)
    reclaim_cooldown_days: int = Field(default=15, ge=0)

    @model_validator(mode="after")
    def _warn_before_recycle(self) -> "PoolSettingsValues":
        if self.recycle_warn_days >= self.recycle_days:
            raise ValueError(
                "recycle_warn_days must be strictly smaller than recycle_days"
            )
        return self


class PoolSettingsUpdate(BaseModel):
    """Partial update; omitted fields keep the stored (or default) value."""

    model_config = ConfigDict(extra="forbid")

    recycle_days: int | None = Field(default=None, ge=3, le=30)
    recycle_warn_days: int | None = Field(default=None, ge=1)
    daily_claim_limit: int | None = Field(default=None, ge=1)
    holding_limit: int | None = Field(default=None, ge=1)
    reclaim_cooldown_days: int | None = Field(default=None, ge=0)


class AssignmentRuleOut(BaseModel):
    """A stored assignment rule as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    site_id: UUID
    name: str
    strategy: str
    conditions: dict[str, list[str]]
    member_user_ids: list[UUID]
    work_hours: list[WorkHourWindow]
    priority: int
    enabled: bool
    created_at: datetime
    created_by: UUID | None
    updated_at: datetime


class AssignmentRuleList(BaseModel):
    """Paged list envelope for assignment rules."""

    items: list[AssignmentRuleOut]
    total: int


class PoolSettingsOut(PoolSettingsValues):
    """Effective pool settings (explicit row or computed defaults)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID | None = None
    org_id: UUID
    site_id: UUID
    is_default: bool = False
    created_at: datetime | None = None
    created_by: UUID | None = None
    updated_at: datetime | None = None


class ConfigLogOut(BaseModel):
    """One configuration change log row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    site_id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    old_value: dict[str, object] | None
    new_value: dict[str, object] | None
    operator_id: UUID
    created_at: datetime


class ConfigLogPage(BaseModel):
    """Paged list envelope for configuration change logs."""

    items: list[ConfigLogOut]
    total: int
    page: int
    page_size: int
