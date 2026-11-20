"""Fictional identifiers and payload builders shared by the API tests."""

from __future__ import annotations

from uuid import uuid4

ORG = "11111111-1111-4111-8111-111111111111"
SITE_A = "22222222-2222-4222-8222-222222222222"
SITE_B = "33333333-3333-4333-8333-333333333333"

OWNER_A = "aaaaaaaa-0000-4000-8000-000000000001"
SUPERVISOR_A = "aaaaaaaa-0000-4000-8000-000000000002"
CONSULTANT_A1 = "aaaaaaaa-0000-4000-8000-000000000003"
CONSULTANT_A2 = "aaaaaaaa-0000-4000-8000-000000000004"
CONSULTANT_A3 = "aaaaaaaa-0000-4000-8000-000000000005"
OWNER_B = "bbbbbbbb-0000-4000-8000-000000000001"
CONSULTANT_B1 = "bbbbbbbb-0000-4000-8000-000000000002"
SYS_ADMIN = "cccccccc-0000-4000-8000-000000000001"
OUTSIDER = "dddddddd-0000-4000-8000-000000000001"


def headers(
    *,
    role: str = "club_owner",
    user_id: str = OWNER_A,
    org: str = ORG,
    site: str = SITE_A,
) -> dict[str, str]:
    return {
        "X-User-Id": user_id,
        "X-Org-Id": org,
        "X-Site-Id": site,
        "X-Role": role,
    }


def rule_payload(**overrides) -> dict:
    payload = {
        "name": "华东制造业轮询",
        "strategy": "round_robin",
        "conditions": {"region": ["east"], "industry": ["manufacturing"]},
        "member_user_ids": [CONSULTANT_A1, CONSULTANT_A2],
        "work_hours": [
            {"weekday": 0, "start": "09:00", "end": "12:00"},
            {"weekday": 0, "start": "13:00", "end": "18:00"},
            {"weekday": 2, "start": "09:30", "end": "17:30"},
        ],
        "priority": 10,
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def unique_name(prefix: str = "规则") -> str:
    return f"{prefix}-{uuid4().hex[:10]}"
