"""Enum values fixed by the S3-SALES-016 work order.

The same literal sets are repeated inside the Alembic migration because
migrations must not import application modules.  The condition vocabulary is
an explicit interface stub: S1-DD-005 (线索字段字典) is still in progress, so
this delivery ships a documented v1 vocabulary instead of pretending the
customer's dictionary is already frozen.  Replacing ``CONDITION_ENUMS`` with
the merged dictionary is a one-file change.
"""

from __future__ import annotations

from enum import StrEnum


class AssignmentStrategy(StrEnum):
    """Strategy used by the assignment engine (the engine itself is out of scope)."""

    ROUND_ROBIN = "round_robin"
    LEAST_HOLDING = "least_holding"
    FIXED_USER = "fixed_user"


class SalesRole(StrEnum):
    """Roles referenced by the S2-IAM contract (mockable in this delivery)."""

    SYS_ADMIN = "sys_admin"
    CLUB_OWNER = "club_owner"
    SUPERVISOR = "supervisor"
    CONSULTANT = "consultant"


class ChangeEntityType(StrEnum):
    """Configuration object types covered by the change log."""

    ASSIGNMENT_RULE = "assignment_rule"
    POOL_SETTINGS = "pool_settings"


class ChangeAction(StrEnum):
    """Audit actions written for every configuration mutation."""

    CREATE = "create"
    UPDATE = "update"
    TOGGLE = "toggle"
    REORDER = "reorder"
    POOL_SETTINGS_UPDATE = "pool_settings_update"


# ---------------------------------------------------------------------------
# Condition vocabulary (v1 interface stub, pending S1-DD-005)
# ---------------------------------------------------------------------------
# ``conditions`` is a JSON object whose keys are condition fields and whose
# values are non-empty arrays of allowed enum literals.  Every key and every
# literal is validated; unknown keys are rejected so a typo cannot silently
# create a rule that never matches.
CONDITION_ENUMS: dict[str, tuple[str, ...]] = {
    "member_level": ("A", "B", "C"),
    "member_status": ("active", "renewing", "churned"),
    "industry": ("manufacturing", "trade", "service", "tech", "other"),
    "region": ("north", "east", "south", "west", "central", "overseas"),
    "source": ("referral", "event", "website", "mini_program", "manual"),
    "intent": ("high", "medium", "low"),
}
