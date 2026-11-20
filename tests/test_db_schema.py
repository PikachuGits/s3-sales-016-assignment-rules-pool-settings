"""Schema-level checks against the migrated PostgreSQL database."""

from __future__ import annotations

from sqlalchemy import inspect


def test_three_tables_and_columns_exist(engine):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "sales_assignment_rule",
        "sales_pool_settings",
        "sales_config_change_log",
    }.issubset(tables)

    common = {
        "id",
        "org_id",
        "site_id",
        "created_at",
        "created_by",
        "updated_at",
        "deleted_at",
    }
    for table in (
        "sales_assignment_rule",
        "sales_pool_settings",
        "sales_config_change_log",
    ):
        columns = {column["name"] for column in inspector.get_columns(table)}
        assert common.issubset(columns)

    rule_columns = {
        column["name"] for column in inspector.get_columns("sales_assignment_rule")
    }
    assert {
        "name",
        "strategy",
        "conditions",
        "member_user_ids",
        "work_hours",
        "priority",
        "enabled",
    }.issubset(rule_columns)

    pool_columns = {
        column["name"] for column in inspector.get_columns("sales_pool_settings")
    }
    assert {
        "recycle_days",
        "recycle_warn_days",
        "daily_claim_limit",
        "holding_limit",
        "reclaim_cooldown_days",
    }.issubset(pool_columns)


def test_unique_constraints_are_installed(engine):
    inspector = inspect(engine)

    rule_uniques = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("sales_assignment_rule")
    }
    assert "uq_sales_assignment_rule_site_name" in rule_uniques

    pool_uniques = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("sales_pool_settings")
    }
    assert "uq_sales_pool_settings_site" in pool_uniques


def test_indexes_are_installed(engine):
    inspector = inspect(engine)
    rule_indexes = {
        index["name"] for index in inspector.get_indexes("sales_assignment_rule")
    }
    assert "ix_sales_assignment_rule_site_order" in rule_indexes

    log_indexes = {
        index["name"]
        for index in inspector.get_indexes("sales_config_change_log")
    }
    assert {
        "ix_sales_config_change_log_site_time",
        "ix_sales_config_change_log_entity",
    }.issubset(log_indexes)


def test_required_columns_are_not_nullable(engine):
    inspector = inspect(engine)
    for table in (
        "sales_assignment_rule",
        "sales_pool_settings",
        "sales_config_change_log",
    ):
        columns = {
            column["name"]: column for column in inspector.get_columns(table)
        }
        for required in ("id", "org_id", "site_id", "created_at", "updated_at"):
            assert columns[required]["nullable"] is False, (table, required)
