"""HTTP routes for assignment rules, pool settings and configuration logs."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.enums import ChangeAction, ChangeEntityType, SalesRole
from app.iam import Principal, get_consultant_directory, get_principal
from app.models import AssignmentRule, SalesConfigChangeLog, SalesPoolSettings
from app.schemas.sales import (
    AssignmentRuleCreate,
    AssignmentRuleList,
    AssignmentRuleOut,
    AssignmentRuleUpdate,
    ConfigLogOut,
    ConfigLogPage,
    PoolSettingsOut,
    PoolSettingsUpdate,
    PoolSettingsValues,
    ReorderPayload,
    RuleToggle,
)

router = APIRouter(prefix="/api/sales", tags=["sales-assignment"])

_WRITE_ROLES = frozenset({SalesRole.SYS_ADMIN, SalesRole.CLUB_OWNER})
_RULE_READ_ROLES = frozenset(
    {SalesRole.SYS_ADMIN, SalesRole.CLUB_OWNER, SalesRole.SUPERVISOR}
)

_FORBIDDEN = {403: {"description": "The caller's role is not allowed for this operation."}}
_CONFLICT = {409: {"description": "A rule with this name already exists in the site."}}


def require_write(principal: Principal = Depends(get_principal)) -> Principal:
    """Only the club owner and sys_admin may mutate configuration."""

    if principal.role not in _WRITE_ROLES:
        raise HTTPException(status_code=403, detail="role_not_allowed_for_write")
    return principal


def require_rule_read(principal: Principal = Depends(get_principal)) -> Principal:
    """Consultants must not read assignment-rule details or audit snapshots."""

    if principal.role not in _RULE_READ_ROLES:
        raise HTTPException(status_code=403, detail="role_not_allowed_for_rule_read")
    return principal


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def _rule_snapshot(rule: AssignmentRule) -> dict[str, object]:
    """Full rule state used as the before/after value of an audit row."""

    return {
        "name": rule.name,
        "strategy": rule.strategy,
        "conditions": rule.conditions,
        "member_user_ids": [str(item) for item in rule.member_user_ids],
        "work_hours": rule.work_hours,
        "priority": rule.priority,
        "enabled": rule.enabled,
    }


def _rule_core(rule: AssignmentRule) -> dict[str, object]:
    """Current rule values in the shape accepted by ``AssignmentRuleCreate``."""

    return {
        "name": rule.name,
        "strategy": rule.strategy,
        "conditions": rule.conditions,
        "member_user_ids": list(rule.member_user_ids),
        "work_hours": rule.work_hours,
        "priority": rule.priority,
        "enabled": rule.enabled,
    }


def _pool_values_dict(row: SalesPoolSettings) -> dict[str, int]:
    return {
        "recycle_days": row.recycle_days,
        "recycle_warn_days": row.recycle_warn_days,
        "daily_claim_limit": row.daily_claim_limit,
        "holding_limit": row.holding_limit,
        "reclaim_cooldown_days": row.reclaim_cooldown_days,
    }


def _write_log(
    session: Session,
    principal: Principal,
    entity_type: ChangeEntityType,
    entity_id: UUID,
    action: ChangeAction,
    old_value: dict[str, object] | None,
    new_value: dict[str, object] | None,
) -> None:
    """Append one audit row to the current transaction."""

    now = datetime.now(timezone.utc)
    session.add(
        SalesConfigChangeLog(
            org_id=principal.org_id,
            site_id=principal.site_id,
            entity_type=entity_type.value,
            entity_id=entity_id,
            action=action.value,
            old_value=old_value,
            new_value=new_value,
            operator_id=principal.user_id,
            created_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
    )


def _ensure_name_available(
    session: Session,
    principal: Principal,
    name: str,
    exclude_id: UUID | None = None,
) -> None:
    stmt = select(AssignmentRule.id).where(
        AssignmentRule.org_id == principal.org_id,
        AssignmentRule.site_id == principal.site_id,
        AssignmentRule.name == name,
        AssignmentRule.deleted_at.is_(None),
    )
    if exclude_id is not None:
        stmt = stmt.where(AssignmentRule.id != exclude_id)
    if session.execute(stmt).first() is not None:
        raise HTTPException(
            status_code=409, detail="assignment_rule_name_conflict"
        )


def _validate_members(
    principal: Principal,
    member_user_ids: list[UUID],
    directory,
) -> None:
    missing = [
        str(user_id)
        for user_id in member_user_ids
        if not directory.is_consultant(principal.org_id, principal.site_id, user_id)
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "member_not_consultant",
                "member_user_ids": missing,
            },
        )


def _get_rule_or_404(
    session: Session, principal: Principal, rule_id: UUID
) -> AssignmentRule:
    rule = session.execute(
        select(AssignmentRule).where(
            AssignmentRule.id == rule_id,
            AssignmentRule.org_id == principal.org_id,
            AssignmentRule.site_id == principal.site_id,
            AssignmentRule.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="assignment_rule_not_found")
    return rule


def _validation_422(exc: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=jsonable_encoder(exc.errors()))


# ---------------------------------------------------------------------------
# Assignment rules
# ---------------------------------------------------------------------------


@router.get(
    "/assignment-rules",
    response_model=AssignmentRuleList,
    summary="List assignment rules",
    description=(
        "Returns rules of the caller's site ordered by priority. Disabled rules "
        "are hidden unless include_disabled=true. Consultants are not allowed "
        "to read rule details."
    ),
    responses={**_FORBIDDEN},
)
def list_assignment_rules(
    include_disabled: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_rule_read),
    session: Session = Depends(get_session),
) -> AssignmentRuleList:
    filters = [
        AssignmentRule.org_id == principal.org_id,
        AssignmentRule.site_id == principal.site_id,
        AssignmentRule.deleted_at.is_(None),
    ]
    if not include_disabled:
        filters.append(AssignmentRule.enabled.is_(True))

    total = session.execute(
        select(func.count()).select_from(AssignmentRule).where(*filters)
    ).scalar_one()
    rules = (
        session.execute(
            select(AssignmentRule)
            .where(*filters)
            .order_by(
                AssignmentRule.priority.asc(),
                AssignmentRule.created_at.asc(),
                AssignmentRule.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return AssignmentRuleList(
        items=[AssignmentRuleOut.model_validate(rule) for rule in rules],
        total=total,
    )


@router.post(
    "/assignment-rules",
    response_model=AssignmentRuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an assignment rule",
    responses={**_FORBIDDEN, **_CONFLICT, 422: {"description": "Validation error."}},
)
def create_assignment_rule(
    payload: AssignmentRuleCreate,
    principal: Principal = Depends(require_write),
    session: Session = Depends(get_session),
    directory=Depends(get_consultant_directory),
) -> AssignmentRuleOut:
    _ensure_name_available(session, principal, payload.name)
    _validate_members(principal, payload.member_user_ids, directory)

    rule = AssignmentRule(
        org_id=principal.org_id,
        site_id=principal.site_id,
        created_by=principal.user_id,
        name=payload.name,
        strategy=payload.strategy,
        conditions=payload.conditions,
        member_user_ids=payload.member_user_ids,
        work_hours=[window.model_dump() for window in payload.work_hours],
        priority=payload.priority,
        enabled=payload.enabled,
    )
    try:
        session.add(rule)
        session.flush()
        _write_log(
            session,
            principal,
            ChangeEntityType.ASSIGNMENT_RULE,
            rule.id,
            ChangeAction.CREATE,
            None,
            _rule_snapshot(rule),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="assignment_rule_name_conflict"
        ) from exc
    session.refresh(rule)
    return AssignmentRuleOut.model_validate(rule)


@router.put(
    "/assignment-rules/{rule_id}",
    response_model=AssignmentRuleOut,
    summary="Update an assignment rule",
    description=(
        "Partial update. The patch is merged with the stored rule and the full "
        "create-time validation is re-run, so strategy/member invariants cannot "
        "be bypassed by patching a single field."
    ),
    responses={**_FORBIDDEN, **_CONFLICT, 404: {"description": "Rule not found."}, 422: {"description": "Validation error."}},
)
def update_assignment_rule(
    rule_id: UUID,
    payload: AssignmentRuleUpdate,
    principal: Principal = Depends(require_write),
    session: Session = Depends(get_session),
    directory=Depends(get_consultant_directory),
) -> AssignmentRuleOut:
    rule = _get_rule_or_404(session, principal, rule_id)

    merged = _rule_core(rule)
    merged.update(payload.model_dump(exclude_unset=True))
    try:
        validated = AssignmentRuleCreate.model_validate(merged)
    except ValidationError as exc:
        raise _validation_422(exc) from exc

    _ensure_name_available(session, principal, validated.name, exclude_id=rule.id)
    _validate_members(principal, validated.member_user_ids, directory)

    old_value = _rule_snapshot(rule)
    rule.name = validated.name
    rule.strategy = validated.strategy
    rule.conditions = validated.conditions
    rule.member_user_ids = validated.member_user_ids
    rule.work_hours = [window.model_dump() for window in validated.work_hours]
    rule.priority = validated.priority
    rule.enabled = validated.enabled
    rule.updated_at = datetime.now(timezone.utc)

    try:
        session.flush()
        _write_log(
            session,
            principal,
            ChangeEntityType.ASSIGNMENT_RULE,
            rule.id,
            ChangeAction.UPDATE,
            old_value,
            _rule_snapshot(rule),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="assignment_rule_name_conflict"
        ) from exc
    session.refresh(rule)
    return AssignmentRuleOut.model_validate(rule)


@router.post(
    "/assignment-rules/{rule_id}/toggle",
    response_model=AssignmentRuleOut,
    summary="Enable or disable an assignment rule",
    description="Omit the body to flip the current state, or send {\"enabled\": false} to force it.",
    responses={**_FORBIDDEN, 404: {"description": "Rule not found."}},
)
def toggle_assignment_rule(
    rule_id: UUID,
    payload: RuleToggle | None = None,
    principal: Principal = Depends(require_write),
    session: Session = Depends(get_session),
) -> AssignmentRuleOut:
    rule = _get_rule_or_404(session, principal, rule_id)
    old_value = _rule_snapshot(rule)

    if payload is not None and payload.enabled is not None:
        new_enabled = payload.enabled
    else:
        new_enabled = not rule.enabled

    rule.enabled = new_enabled
    rule.updated_at = datetime.now(timezone.utc)
    session.flush()
    _write_log(
        session,
        principal,
        ChangeEntityType.ASSIGNMENT_RULE,
        rule.id,
        ChangeAction.TOGGLE,
        old_value,
        _rule_snapshot(rule),
    )
    session.commit()
    session.refresh(rule)
    return AssignmentRuleOut.model_validate(rule)


@router.post(
    "/assignment-rules/reorder",
    response_model=AssignmentRuleList,
    summary="Batch adjust rule priorities",
    description=(
        "Applies priority changes in one transaction and writes one audit row "
        "per rule whose priority actually changed."
    ),
    responses={**_FORBIDDEN, 404: {"description": "One or more rules were not found."}, 422: {"description": "Validation error."}},
)
def reorder_assignment_rules(
    payload: ReorderPayload,
    principal: Principal = Depends(require_write),
    session: Session = Depends(get_session),
) -> AssignmentRuleList:
    rule_ids = [item.id for item in payload.items]
    rules = (
        session.execute(
            select(AssignmentRule).where(
                AssignmentRule.id.in_(rule_ids),
                AssignmentRule.org_id == principal.org_id,
                AssignmentRule.site_id == principal.site_id,
                AssignmentRule.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    by_id = {rule.id: rule for rule in rules}
    missing = [str(rule_id) for rule_id in rule_ids if rule_id not in by_id]
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"code": "assignment_rule_not_found", "rule_ids": missing},
        )

    now = datetime.now(timezone.utc)
    for item in payload.items:
        rule = by_id[item.id]
        if rule.priority == item.priority:
            continue
        old_value = _rule_snapshot(rule)
        rule.priority = item.priority
        rule.updated_at = now
        _write_log(
            session,
            principal,
            ChangeEntityType.ASSIGNMENT_RULE,
            rule.id,
            ChangeAction.REORDER,
            old_value,
            _rule_snapshot(rule),
        )

    session.commit()
    ordered = (
        session.execute(
            select(AssignmentRule)
            .where(
                AssignmentRule.id.in_(rule_ids),
                AssignmentRule.org_id == principal.org_id,
                AssignmentRule.site_id == principal.site_id,
                AssignmentRule.deleted_at.is_(None),
            )
            .order_by(
                AssignmentRule.priority.asc(),
                AssignmentRule.created_at.asc(),
                AssignmentRule.id.asc(),
            )
        )
        .scalars()
        .all()
    )
    return AssignmentRuleList(
        items=[AssignmentRuleOut.model_validate(rule) for rule in ordered],
        total=len(ordered),
    )


# ---------------------------------------------------------------------------
# Public-pool settings
# ---------------------------------------------------------------------------


@router.get(
    "/pool-settings",
    response_model=PoolSettingsOut,
    summary="Read public-pool settings",
    description=(
        "Returns the site's explicit settings, or the documented defaults "
        "(7 / 5 / 10 / 150 / 15) when no row exists yet."
    ),
)
def get_pool_settings(
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> PoolSettingsOut:
    row = session.execute(
        select(SalesPoolSettings).where(
            SalesPoolSettings.org_id == principal.org_id,
            SalesPoolSettings.site_id == principal.site_id,
            SalesPoolSettings.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        return PoolSettingsOut(
            org_id=principal.org_id, site_id=principal.site_id, is_default=True
        )
    return PoolSettingsOut.model_validate(row)


@router.put(
    "/pool-settings",
    response_model=PoolSettingsOut,
    summary="Create or update public-pool settings",
    description=(
        "Partial upsert: omitted fields keep the stored value, or the default "
        "when the site has no row yet. recycle_warn_days must be strictly "
        "smaller than recycle_days; otherwise the request returns 422."
    ),
    responses={**_FORBIDDEN, 422: {"description": "Validation error."}},
)
def update_pool_settings(
    payload: PoolSettingsUpdate,
    principal: Principal = Depends(require_write),
    session: Session = Depends(get_session),
) -> PoolSettingsOut:
    row = session.execute(
        select(SalesPoolSettings).where(
            SalesPoolSettings.org_id == principal.org_id,
            SalesPoolSettings.site_id == principal.site_id,
            SalesPoolSettings.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    base = (
        PoolSettingsValues.model_validate(_pool_values_dict(row))
        if row is not None
        else PoolSettingsValues()
    )
    merged = base.model_dump()
    merged.update(payload.model_dump(exclude_unset=True))
    try:
        values = PoolSettingsValues.model_validate(merged)
    except ValidationError as exc:
        raise _validation_422(exc) from exc

    old_value = base.model_dump()
    new_value = values.model_dump()
    now = datetime.now(timezone.utc)

    if row is None:
        row = SalesPoolSettings(
            org_id=principal.org_id,
            site_id=principal.site_id,
            created_by=principal.user_id,
            **new_value,
        )
        session.add(row)
        session.flush()
        _write_log(
            session,
            principal,
            ChangeEntityType.POOL_SETTINGS,
            row.id,
            ChangeAction.POOL_SETTINGS_UPDATE,
            old_value,
            new_value,
        )
        session.commit()
        session.refresh(row)
        return PoolSettingsOut.model_validate(row)

    row.recycle_days = values.recycle_days
    row.recycle_warn_days = values.recycle_warn_days
    row.daily_claim_limit = values.daily_claim_limit
    row.holding_limit = values.holding_limit
    row.reclaim_cooldown_days = values.reclaim_cooldown_days
    row.updated_at = now
    session.flush()
    _write_log(
        session,
        principal,
        ChangeEntityType.POOL_SETTINGS,
        row.id,
        ChangeAction.POOL_SETTINGS_UPDATE,
        old_value,
        new_value,
    )
    session.commit()
    session.refresh(row)
    return PoolSettingsOut.model_validate(row)


# ---------------------------------------------------------------------------
# Configuration change log
# ---------------------------------------------------------------------------


@router.get(
    "/config-logs",
    response_model=ConfigLogPage,
    summary="Page through configuration change logs",
    description=(
        "Newest first. Every mutation writes a row with the full old and new "
        "value, the operator and the timestamp. Consultants cannot read these "
        "snapshots because they contain rule details."
    ),
    responses={**_FORBIDDEN},
)
def list_config_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    entity_type: ChangeEntityType | None = Query(default=None),
    entity_id: UUID | None = Query(default=None),
    action: ChangeAction | None = Query(default=None),
    principal: Principal = Depends(require_rule_read),
    session: Session = Depends(get_session),
) -> ConfigLogPage:
    filters = [
        SalesConfigChangeLog.org_id == principal.org_id,
        SalesConfigChangeLog.site_id == principal.site_id,
        SalesConfigChangeLog.deleted_at.is_(None),
    ]
    if entity_type is not None:
        filters.append(SalesConfigChangeLog.entity_type == entity_type.value)
    if entity_id is not None:
        filters.append(SalesConfigChangeLog.entity_id == entity_id)
    if action is not None:
        filters.append(SalesConfigChangeLog.action == action.value)

    total = session.execute(
        select(func.count()).select_from(SalesConfigChangeLog).where(*filters)
    ).scalar_one()
    offset = (page - 1) * page_size
    rows = (
        session.execute(
            select(SalesConfigChangeLog)
            .where(*filters)
            .order_by(
                SalesConfigChangeLog.created_at.desc(),
                SalesConfigChangeLog.id.desc(),
            )
            .limit(page_size)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return ConfigLogPage(
        items=[ConfigLogOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
