"""Database-level constraint tests, independent of the HTTP layer."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import AssignmentRule, SalesPoolSettings


def _rule(**overrides) -> AssignmentRule:
    values = {
        "org_id": uuid.uuid4(),
        "site_id": uuid.uuid4(),
        "name": f"约束-{uuid.uuid4().hex[:8]}",
        "strategy": "round_robin",
        "conditions": {},
        "member_user_ids": [uuid.uuid4()],
        "work_hours": [{"weekday": 0, "start": "09:00", "end": "18:00"}],
        "priority": 1,
        "enabled": True,
    }
    values.update(overrides)
    return AssignmentRule(**values)


def test_invalid_strategy_is_rejected_by_the_database(db_session):
    rule = _rule(strategy="random")
    db_session.add(rule)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_invalid_pool_warn_days_is_rejected_by_the_database(db_session):
    row = SalesPoolSettings(
        org_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        recycle_days=7,
        recycle_warn_days=7,
        daily_claim_limit=10,
        holding_limit=150,
        reclaim_cooldown_days=15,
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_rule_name_is_rejected_by_the_database(db_session):
    org_id = uuid.uuid4()
    site_id = uuid.uuid4()
    first = _rule(org_id=org_id, site_id=site_id, name="重复规则")
    second = _rule(org_id=org_id, site_id=site_id, name="重复规则")
    db_session.add_all([first, second])
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_conditions_must_be_a_json_object(db_session):
    rule = _rule(conditions=["not", "an", "object"])
    db_session.add(rule)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_work_hours_must_be_a_json_array(db_session):
    rule = _rule(work_hours={"weekday": 0})
    db_session.add(rule)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_uuid_primary_key_is_generated_by_the_database(db_session):
    rule = _rule()
    db_session.add(rule)
    db_session.flush()
    assert rule.id is not None
    assert rule.created_at is not None
    db_session.rollback()


def test_pool_settings_is_unique_per_site(db_session):
    org_id = uuid.uuid4()
    site_id = uuid.uuid4()
    first = SalesPoolSettings(org_id=org_id, site_id=site_id)
    second = SalesPoolSettings(org_id=org_id, site_id=site_id)
    db_session.add_all([first, second])
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
