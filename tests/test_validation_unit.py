"""Pure schema validation tests (no database required)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.sales import (
    AssignmentRuleCreate,
    PoolSettingsValues,
    PoolSettingsUpdate,
    ReorderPayload,
)
from tests.factories import CONSULTANT_A1, CONSULTANT_A2, OUTSIDER, rule_payload


def test_pool_defaults_match_work_order() -> None:
    values = PoolSettingsValues()
    assert values.recycle_days == 7
    assert values.recycle_warn_days == 5
    assert values.daily_claim_limit == 10
    assert values.holding_limit == 150
    assert values.reclaim_cooldown_days == 15


def test_pool_warn_days_must_be_smaller_than_recycle_days() -> None:
    with pytest.raises(ValidationError):
        PoolSettingsValues(recycle_days=7, recycle_warn_days=7)
    with pytest.raises(ValidationError):
        PoolSettingsValues(recycle_days=7, recycle_warn_days=8)


@pytest.mark.parametrize(
    "field,value",
    [
        ("recycle_days", 2),
        ("recycle_days", 31),
        ("recycle_warn_days", 0),
        ("daily_claim_limit", 0),
        ("holding_limit", 0),
        ("reclaim_cooldown_days", -1),
    ],
)
def test_pool_ranges(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        PoolSettingsUpdate(**{field: value})


def test_fixed_user_requires_exactly_one_member() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        AssignmentRuleCreate.model_validate(
            rule_payload(
                strategy="fixed_user",
                member_user_ids=[CONSULTANT_A1, CONSULTANT_A2],
            )
        )

    valid = AssignmentRuleCreate.model_validate(
        rule_payload(strategy="fixed_user", member_user_ids=[CONSULTANT_A1])
    )
    assert valid.strategy == "fixed_user"
    assert len(valid.member_user_ids) == 1


def test_non_fixed_strategy_requires_at_least_one_member() -> None:
    with pytest.raises(ValidationError):
        AssignmentRuleCreate.model_validate(
            rule_payload(strategy="round_robin", member_user_ids=[])
        )


def test_member_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        AssignmentRuleCreate.model_validate(
            rule_payload(member_user_ids=[CONSULTANT_A1, CONSULTANT_A1])
        )


def test_unknown_condition_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown condition field"):
        AssignmentRuleCreate.model_validate(
            rule_payload(conditions={"unknown_field": ["x"]})
        )


def test_invalid_condition_literal_is_rejected() -> None:
    with pytest.raises(ValidationError, match="invalid literal"):
        AssignmentRuleCreate.model_validate(
            rule_payload(conditions={"region": ["mars"]})
        )


def test_empty_condition_list_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one literal"):
        AssignmentRuleCreate.model_validate(rule_payload(conditions={"region": []}))


def test_work_window_start_must_be_before_end() -> None:
    with pytest.raises(ValidationError, match="start < end"):
        AssignmentRuleCreate.model_validate(
            rule_payload(
                work_hours=[{"weekday": 0, "start": "18:00", "end": "18:00"}]
            )
        )


def test_work_windows_must_not_overlap() -> None:
    with pytest.raises(ValidationError, match="overlap"):
        AssignmentRuleCreate.model_validate(
            rule_payload(
                work_hours=[
                    {"weekday": 1, "start": "09:00", "end": "12:00"},
                    {"weekday": 1, "start": "11:00", "end": "15:00"},
                ]
            )
        )


def test_adjacent_work_windows_are_allowed() -> None:
    valid = AssignmentRuleCreate.model_validate(
        rule_payload(
            work_hours=[
                {"weekday": 1, "start": "09:00", "end": "12:00"},
                {"weekday": 1, "start": "12:00", "end": "15:00"},
            ]
        )
    )
    assert len(valid.work_hours) == 2


def test_name_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        AssignmentRuleCreate.model_validate(rule_payload(name="   "))


def test_reorder_rejects_duplicate_ids() -> None:
    rule_id = "eeeeeeee-0000-4000-8000-000000000001"
    with pytest.raises(ValidationError, match="duplicate"):
        ReorderPayload.model_validate(
            {
                "items": [
                    {"id": rule_id, "priority": 1},
                    {"id": rule_id, "priority": 2},
                ]
            }
        )


def test_conditions_accept_all_documented_enums() -> None:
    valid = AssignmentRuleCreate.model_validate(
        rule_payload(
            conditions={
                "member_level": ["A", "B", "C"],
                "member_status": ["active", "renewing", "churned"],
                "industry": ["manufacturing", "trade", "service", "tech", "other"],
                "region": ["north", "east", "south", "west", "central", "overseas"],
                "source": ["referral", "event", "website", "mini_program", "manual"],
                "intent": ["high", "medium", "low"],
            }
        )
    )
    assert valid.conditions["region"]


def test_outsider_is_only_business_validation_not_shape_validation() -> None:
    """The outsider UUID is shape-valid; membership is checked against IAM."""

    valid = AssignmentRuleCreate.model_validate(
        rule_payload(strategy="fixed_user", member_user_ids=[OUTSIDER])
    )
    assert str(valid.member_user_ids[0]) == OUTSIDER
