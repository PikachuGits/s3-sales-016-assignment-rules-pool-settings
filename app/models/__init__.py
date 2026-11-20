"""Model registry: importing this module registers all three tables."""

from app.models.assignment_rule import AssignmentRule  # noqa: F401
from app.models.config_change_log import SalesConfigChangeLog  # noqa: F401
from app.models.sales_pool_settings import SalesPoolSettings  # noqa: F401

__all__ = ["AssignmentRule", "SalesConfigChangeLog", "SalesPoolSettings"]
