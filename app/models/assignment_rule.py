"""Assignment rule table.

A rule is a site-scoped configuration object.  The assignment engine that
consumes it is explicitly out of scope for this work order; this module only
owns persistence and validation.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AssignmentRule(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A sales assignment rule (``sales_assignment_rule``)."""

    __tablename__ = "sales_assignment_rule"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    conditions: Mapped[dict[str, list[str]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    member_user_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
    )
    work_hours: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("100")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    __table_args__ = (
        UniqueConstraint(
            "org_id", "site_id", "name", name="uq_sales_assignment_rule_site_name"
        ),
        CheckConstraint(
            "strategy IN ('round_robin', 'least_holding', 'fixed_user')",
            name="ck_sales_assignment_rule_strategy",
        ),
        CheckConstraint(
            "priority >= 0", name="ck_sales_assignment_rule_priority"
        ),
        CheckConstraint(
            "array_length(member_user_ids, 1) >= 1",
            name="ck_sales_assignment_rule_members",
        ),
        CheckConstraint(
            "jsonb_typeof(conditions) = 'object'",
            name="ck_sales_assignment_rule_conditions",
        ),
        CheckConstraint(
            "jsonb_typeof(work_hours) = 'array'",
            name="ck_sales_assignment_rule_work_hours",
        ),
        Index(
            "ix_sales_assignment_rule_site_order",
            "org_id",
            "site_id",
            "enabled",
            "priority",
        ),
    )
