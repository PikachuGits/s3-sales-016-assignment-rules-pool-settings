"""Role-based permission tests (acceptance criterion 3)."""

from __future__ import annotations

from tests.factories import (
    CONSULTANT_A1,
    OUTSIDER,
    SYS_ADMIN,
    SUPERVISOR_A,
    headers,
    rule_payload,
    unique_name,
)

RULES = "/api/sales/assignment-rules"
POOL = "/api/sales/pool-settings"
LOGS = "/api/sales/config-logs"


def _create_rule(client) -> dict:
    response = client.post(
        RULES, json=rule_payload(name=unique_name()), headers=headers()
    )
    assert response.status_code == 201
    return response.json()


def test_supervisor_reads_rules_but_cannot_write(client):
    """Acceptance criterion 3: supervisor GET 200, write 403."""

    rule = _create_rule(client)
    supervisor_headers = headers(role="supervisor", user_id=SUPERVISOR_A)

    assert client.get(RULES, headers=supervisor_headers).status_code == 200

    write_attempts = [
        client.post(RULES, json=rule_payload(name=unique_name()), headers=supervisor_headers),
        client.put(f"{RULES}/{rule['id']}", json={"priority": 9}, headers=supervisor_headers),
        client.post(f"{RULES}/{rule['id']}/toggle", headers=supervisor_headers),
        client.post(
            f"{RULES}/reorder",
            json={"items": [{"id": rule["id"], "priority": 2}]},
            headers=supervisor_headers,
        ),
        client.put(POOL, json={"daily_claim_limit": 20}, headers=supervisor_headers),
    ]
    for response in write_attempts:
        assert response.status_code == 403, response.text


def test_consultant_cannot_read_rule_details(client):
    _create_rule(client)
    consultant_headers = headers(role="consultant", user_id=CONSULTANT_A1)

    response = client.get(RULES, headers=consultant_headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "role_not_allowed_for_rule_read"

    response = client.get(LOGS, headers=consultant_headers)
    assert response.status_code == 403


def test_consultant_can_read_pool_settings(client):
    response = client.get(
        POOL, headers=headers(role="consultant", user_id=CONSULTANT_A1)
    )
    assert response.status_code == 200


def test_club_owner_can_write(client):
    response = client.post(
        RULES, json=rule_payload(name=unique_name()), headers=headers(role="club_owner")
    )
    assert response.status_code == 201


def test_sys_admin_can_write(client):
    response = client.post(
        RULES,
        json=rule_payload(name=unique_name()),
        headers=headers(role="sys_admin", user_id=SYS_ADMIN),
    )
    assert response.status_code == 201


def test_unknown_role_returns_401(client):
    response = client.get(RULES, headers=headers(role="intern"))
    assert response.status_code == 401


def test_outsider_role_is_authenticated_but_unauthorized(client):
    """A valid role that is not allowed to read rules gets 403, not 401."""

    response = client.get(
        RULES, headers=headers(role="consultant", user_id=OUTSIDER)
    )
    assert response.status_code == 403
