"""Configuration change log.

Every successful mutation of an assignment rule or the pool settings writes
one row containing the full before/after snapshots, the operator and the
timestamp.  The row is written in the same transaction as the mutation, so an
audit entry can never describe a change that was rolled back.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SalesConfigChangeLog(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Audit row for a configuration mutation (``sales_config_change_log``)."""

    __tablename__ = "sales_config_change_log"

    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    old_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    operator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('assignment_rule', 'pool_settings')",
            name="ck_sales_config_change_log_entity_type",
        ),
        CheckConstraint(
            "action IN ('create', 'update', 'toggle', 'reorder', 'pool_settings_update')",
            name="ck_sales_config_change_log_action",
        ),
        Index(
            "ix_sales_config_change_log_site_time",
            "org_id",
            "site_id",
            "created_at",
        ),
        Index(
            "ix_sales_config_change_log_entity",
            "entity_type",
            "entity_id",
        ),
    )
