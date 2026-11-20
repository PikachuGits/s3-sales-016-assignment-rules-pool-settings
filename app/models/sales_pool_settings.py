"""Public-pool settings table.

Exactly one row per site.  The database defaults mirror the work order
(7 / 5 / 10 / 150 / 15) so a site without an explicit row behaves identically
to a site whose row was created with defaults.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SalesPoolSettings(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Per-site public pool parameters (``sales_pool_settings``)."""

    __tablename__ = "sales_pool_settings"

    recycle_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("7")
    )
    recycle_warn_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("5")
    )
    daily_claim_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("10")
    )
    holding_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("150")
    )
    reclaim_cooldown_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("15")
    )

    __table_args__ = (
        UniqueConstraint("org_id", "site_id", name="uq_sales_pool_settings_site"),
        CheckConstraint(
            "recycle_days BETWEEN 3 AND 30",
            name="ck_sales_pool_settings_recycle_days",
        ),
        CheckConstraint(
            "recycle_warn_days >= 1 AND recycle_warn_days < recycle_days",
            name="ck_sales_pool_settings_warn_days",
        ),
        CheckConstraint(
            "daily_claim_limit >= 1",
            name="ck_sales_pool_settings_daily_claim_limit",
        ),
        CheckConstraint(
            "holding_limit >= 1",
            name="ck_sales_pool_settings_holding_limit",
        ),
        CheckConstraint(
            "reclaim_cooldown_days >= 0",
            name="ck_sales_pool_settings_reclaim_cooldown_days",
        ),
    )
