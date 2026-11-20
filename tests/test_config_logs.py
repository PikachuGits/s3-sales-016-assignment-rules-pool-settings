"""Configuration change-log tests (acceptance criterion 4)."""

from __future__ import annotations

from tests.factories import SUPERVISOR_A, headers, rule_payload, unique_name

RULES = "/api/sales/assignment-rules"
POOL = "/api/sales/pool-settings"
LOGS = "/api/sales/config-logs"

READ_HEADERS = headers(role="supervisor", user_id=SUPERVISOR_A)


def _create_rule(client, **overrides) -> dict:
    payload = rule_payload(**overrides)
    payload.setdefault("name", unique_name())
    response = client.post(RULES, json=payload, headers=headers())
    assert response.status_code == 201, response.text
    return response.json()


def _get_logs(client, **params) -> dict:
    response = client.get(LOGS, params=params, headers=READ_HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def test_create_writes_log_with_null_old_value(client):
    rule = _create_rule(client, name="审计-创建")

    page = _get_logs(client, entity_type="assignment_rule", entity_id=rule["id"])
    assert page["total"] == 1
    entry = page["items"][0]
    assert entry["action"] == "create"
    assert entry["entity_id"] == rule["id"]
    assert entry["old_value"] is None
    assert entry["new_value"]["name"] == "审计-创建"
    assert entry["new_value"]["priority"] == 10
    assert entry["operator_id"] == headers()["X-User-Id"]
    assert entry["created_at"]


def test_update_log_contains_old_and_new_values(client):
    rule = _create_rule(client, name="审计-旧名", priority=10)

    response = client.put(
        f"{RULES}/{rule['id']}",
        json={"name": "审计-新名", "priority": 77},
        headers=headers(),
    )
    assert response.status_code == 200

    page = _get_logs(client, entity_type="assignment_rule", entity_id=rule["id"])
    assert page["total"] == 2
    update_entry = page["items"][0]
    assert update_entry["action"] == "update"
    assert update_entry["old_value"]["name"] == "审计-旧名"
    assert update_entry["old_value"]["priority"] == 10
    assert update_entry["new_value"]["name"] == "审计-新名"
    assert update_entry["new_value"]["priority"] == 77


def test_toggle_log_contains_enabled_before_and_after(client):
    rule = _create_rule(client)

    client.post(f"{RULES}/{rule['id']}/toggle", headers=headers())

    page = _get_logs(client, entity_type="assignment_rule", entity_id=rule["id"])
    toggle_entry = page["items"][0]
    assert toggle_entry["action"] == "toggle"
    assert toggle_entry["old_value"]["enabled"] is True
    assert toggle_entry["new_value"]["enabled"] is False


def test_reorder_writes_one_log_per_changed_rule(client):
    first = _create_rule(client, name=unique_name("R1"), priority=1)
    second = _create_rule(client, name=unique_name("R2"), priority=2)

    response = client.post(
        f"{RULES}/reorder",
        json={
            "items": [
                {"id": first["id"], "priority": 20},
                {"id": second["id"], "priority": 10},
            ]
        },
        headers=headers(),
    )
    assert response.status_code == 200

    page = _get_logs(client, action="reorder")
    assert page["total"] == 2
    priorities = {
        entry["entity_id"]: (entry["old_value"]["priority"], entry["new_value"]["priority"])
        for entry in page["items"]
    }
    assert priorities[first["id"]] == (1, 20)
    assert priorities[second["id"]] == (2, 10)


def test_pool_settings_update_log_uses_defaults_as_old_value(client):
    response = client.put(POOL, json={"recycle_days": 10}, headers=headers())
    assert response.status_code == 200

    page = _get_logs(client, entity_type="pool_settings")
    assert page["total"] == 1
    entry = page["items"][0]
    assert entry["action"] == "pool_settings_update"
    assert entry["old_value"] == {
        "recycle_days": 7,
        "recycle_warn_days": 5,
        "daily_claim_limit": 10,
        "holding_limit": 150,
        "reclaim_cooldown_days": 15,
    }
    assert entry["new_value"]["recycle_days"] == 10
    assert entry["new_value"]["recycle_warn_days"] == 5
    assert entry["operator_id"] == headers()["X-User-Id"]


def test_second_pool_update_uses_first_update_as_old_value(client):
    client.put(POOL, json={"recycle_days": 10}, headers=headers())
    client.put(POOL, json={"recycle_warn_days": 9}, headers=headers())

    page = _get_logs(client, entity_type="pool_settings")
    assert page["total"] == 2
    latest = page["items"][0]
    assert latest["old_value"]["recycle_days"] == 10
    assert latest["old_value"]["recycle_warn_days"] == 5
    assert latest["new_value"]["recycle_warn_days"] == 9


def test_logs_are_paginated(client):
    for index in range(5):
        _create_rule(client, name=unique_name(f"分页-{index}"))

    first = _get_logs(client, page=1, page_size=2)
    second = _get_logs(client, page=2, page_size=2)
    third = _get_logs(client, page=3, page_size=2)

    assert first["total"] == 5
    assert first["page"] == 1 and first["page_size"] == 2
    assert len(first["items"]) == 2
    assert len(second["items"]) == 2
    assert len(third["items"]) == 1

    ids = {
        entry["id"]
        for page in (first, second, third)
        for entry in page["items"]
    }
    assert len(ids) == 5


def test_log_filter_by_entity_id(client):
    first = _create_rule(client, name=unique_name("过滤A"))
    _create_rule(client, name=unique_name("过滤B"))

    page = _get_logs(client, entity_id=first["id"])
    assert page["total"] == 1
    assert page["items"][0]["entity_id"] == first["id"]


def test_log_page_size_upper_bound_is_enforced(client):
    response = client.get(LOGS, params={"page_size": 101}, headers=READ_HEADERS)
    assert response.status_code == 422
