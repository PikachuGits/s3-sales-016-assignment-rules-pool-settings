"""create sales assignment configuration tables

Revision ID: 0001_sales_assignment_config
Revises:
Create Date: 2026-11-20 12:00:00

Tables: sales_assignment_rule, sales_pool_settings,
sales_config_change_log.

The literal enum sets are repeated here instead of importing
``app.enums`` because migrations must remain runnable without the current
application code.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_sales_assignment_config"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sales_assignment_rule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("strategy", sa.String(length=16), nullable=False),
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "member_user_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column(
            "work_hours",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "priority", sa.Integer(), server_default=sa.text("100"), nullable=False
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "strategy IN ('round_robin', 'least_holding', 'fixed_user')",
            name="ck_sales_assignment_rule_strategy",
        ),
        sa.CheckConstraint(
            "priority >= 0", name="ck_sales_assignment_rule_priority"
        ),
        sa.CheckConstraint(
            "array_length(member_user_ids, 1) >= 1",
            name="ck_sales_assignment_rule_members",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(conditions) = 'object'",
            name="ck_sales_assignment_rule_conditions",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(work_hours) = 'array'",
            name="ck_sales_assignment_rule_work_hours",
        ),
        sa.UniqueConstraint(
            "org_id", "site_id", "name", name="uq_sales_assignment_rule_site_name"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sales_assignment_rule_site_order",
        "sales_assignment_rule",
        ["org_id", "site_id", "enabled", "priority"],
        unique=False,
    )

    op.create_table(
        "sales_pool_settings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "recycle_days",
            sa.Integer(),
            server_default=sa.text("7"),
            nullable=False,
        ),
        sa.Column(
            "recycle_warn_days",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.Column(
            "daily_claim_limit",
            sa.Integer(),
            server_default=sa.text("10"),
            nullable=False,
        ),
        sa.Column(
            "holding_limit",
            sa.Integer(),
            server_default=sa.text("150"),
            nullable=False,
        ),
        sa.Column(
            "reclaim_cooldown_days",
            sa.Integer(),
            server_default=sa.text("15"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "recycle_days BETWEEN 3 AND 30",
            name="ck_sales_pool_settings_recycle_days",
        ),
        sa.CheckConstraint(
            "recycle_warn_days >= 1 AND recycle_warn_days < recycle_days",
            name="ck_sales_pool_settings_warn_days",
        ),
        sa.CheckConstraint(
            "daily_claim_limit >= 1",
            name="ck_sales_pool_settings_daily_claim_limit",
        ),
        sa.CheckConstraint(
            "holding_limit >= 1",
            name="ck_sales_pool_settings_holding_limit",
        ),
        sa.CheckConstraint(
            "reclaim_cooldown_days >= 0",
            name="ck_sales_pool_settings_reclaim_cooldown_days",
        ),
        sa.UniqueConstraint(
            "org_id", "site_id", name="uq_sales_pool_settings_site"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sales_config_change_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "old_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "new_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "entity_type IN ('assignment_rule', 'pool_settings')",
            name="ck_sales_config_change_log_entity_type",
        ),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'toggle', 'reorder', 'pool_settings_update')",
            name="ck_sales_config_change_log_action",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sales_config_change_log_site_time",
        "sales_config_change_log",
        ["org_id", "site_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_sales_config_change_log_entity",
        "sales_config_change_log",
        ["entity_type", "entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sales_config_change_log_entity",
        table_name="sales_config_change_log",
    )
    op.drop_index(
        "ix_sales_config_change_log_site_time",
        table_name="sales_config_change_log",
    )
    op.drop_table("sales_config_change_log")
    op.drop_table("sales_pool_settings")
    op.drop_index(
        "ix_sales_assignment_rule_site_order",
        table_name="sales_assignment_rule",
    )
    op.drop_table("sales_assignment_rule")
