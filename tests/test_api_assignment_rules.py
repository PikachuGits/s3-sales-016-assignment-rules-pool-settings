"""API tests for assignment rules."""

from __future__ import annotations

from tests.factories import (
    CONSULTANT_A1,
    CONSULTANT_A2,
    CONSULTANT_A3,
    CONSULTANT_B1,
    OUTSIDER,
    OWNER_B,
    SITE_B,
    headers,
    rule_payload,
    unique_name,
)

RULES = "/api/sales/assignment-rules"


def create_rule(client, **overrides):
    payload = rule_payload(**overrides)
    response = client.post(RULES, json=payload, headers=headers())
    assert response.status_code == 201, response.text
    return response.json()


def test_create_rule_returns_full_contract(client):
    body = create_rule(client)

    assert body["name"] == "华东制造业轮询"
    assert body["strategy"] == "round_robin"
    assert body["priority"] == 10
    assert body["enabled"] is True
    assert body["member_user_ids"] == [CONSULTANT_A1, CONSULTANT_A2]
    assert body["conditions"] == {"region": ["east"], "industry": ["manufacturing"]}
    assert len(body["work_hours"]) == 3
    assert body["created_by"] == headers()["X-User-Id"]
    assert body["id"] and body["org_id"] and body["site_id"]


def test_list_orders_by_priority_and_hides_disabled(client):
    create_rule(client, name=unique_name("P-30"), priority=30)
    create_rule(client, name=unique_name("P-10"), priority=10)
    create_rule(client, name=unique_name("P-20"), priority=20)
    disabled = create_rule(client, name=unique_name("P-5"), priority=5)
    client.post(
        f"{RULES}/{disabled['id']}/toggle",
        json={"enabled": False},
        headers=headers(),
    )

    response = client.get(RULES, headers=headers())
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["priority"] for item in items] == [10, 20, 30]
    assert response.json()["total"] == 3

    response = client.get(f"{RULES}?include_disabled=true", headers=headers())
    assert response.json()["total"] == 4
    assert response.json()["items"][0]["priority"] == 5


def test_duplicate_name_returns_409(client):
    create_rule(client, name="同名规则")

    response = client.post(
        RULES, json=rule_payload(name="同名规则"), headers=headers()
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "assignment_rule_name_conflict"


def test_update_rule_revalidates_strategy_and_members(client):
    rule = create_rule(client, strategy="fixed_user", member_user_ids=[CONSULTANT_A1])

    response = client.put(
        f"{RULES}/{rule['id']}",
        json={"member_user_ids": [CONSULTANT_A1, CONSULTANT_A2]},
        headers=headers(),
    )
    assert response.status_code == 422
    assert "member_user_ids" in response.text or "422" in response.text

    response = client.put(
        f"{RULES}/{rule['id']}",
        json={"priority": 42, "name": unique_name("改后")},
        headers=headers(),
    )
    assert response.status_code == 200
    assert response.json()["priority"] == 42
    assert response.json()["member_user_ids"] == [CONSULTANT_A1]


def test_update_name_conflict_returns_409(client):
    first = create_rule(client, name="规则A")
    second = create_rule(client, name="规则B")

    response = client.put(
        f"{RULES}/{second['id']}", json={"name": first["name"]}, headers=headers()
    )
    assert response.status_code == 409


def test_toggle_flips_and_forces_state(client):
    rule = create_rule(client)

    response = client.post(f"{RULES}/{rule['id']}/toggle", headers=headers())
    assert response.status_code == 200
    assert response.json()["enabled"] is False

    response = client.post(
        f"{RULES}/{rule['id']}/toggle",
        json={"enabled": True},
        headers=headers(),
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is True


def test_reorder_batch_updates_priorities(client):
    first = create_rule(client, name=unique_name("A"), priority=1)
    second = create_rule(client, name=unique_name("B"), priority=2)
    third = create_rule(client, name=unique_name("C"), priority=3)

    response = client.post(
        f"{RULES}/reorder",
        json={
            "items": [
                {"id": first["id"], "priority": 30},
                {"id": second["id"], "priority": 20},
                {"id": third["id"], "priority": 10},
            ]
        },
        headers=headers(),
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        third["id"],
        second["id"],
        first["id"],
    ]

    listing = client.get(RULES, headers=headers()).json()["items"]
    assert [item["priority"] for item in listing] == [10, 20, 30]


def test_reorder_unknown_rule_returns_404(client):
    rule = create_rule(client)
    response = client.post(
        f"{RULES}/reorder",
        json={
            "items": [
                {"id": rule["id"], "priority": 1},
                {"id": "eeeeeeee-0000-4000-8000-000000000001", "priority": 2},
            ]
        },
        headers=headers(),
    )
    assert response.status_code == 404


def test_fixed_user_two_members_returns_422(client):
    response = client.post(
        RULES,
        json=rule_payload(
            strategy="fixed_user",
            member_user_ids=[CONSULTANT_A1, CONSULTANT_A2],
        ),
        headers=headers(),
    )
    assert response.status_code == 422


def test_non_consultant_member_returns_422(client):
    response = client.post(
        RULES,
        json=rule_payload(
            strategy="fixed_user", member_user_ids=[OUTSIDER]
        ),
        headers=headers(),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "member_not_consultant"


def test_member_from_another_site_returns_422(client):
    response = client.post(
        RULES,
        json=rule_payload(
            strategy="fixed_user", member_user_ids=[CONSULTANT_B1]
        ),
        headers=headers(),
    )
    assert response.status_code == 422


def test_rule_is_scoped_to_org_and_site(client):
    create_rule(client, name="本站规则")

    response = client.get(
        RULES, headers=headers(site=SITE_B, user_id=OWNER_B)
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_invalid_strategy_returns_422(client):
    response = client.post(
        RULES, json=rule_payload(strategy="random"), headers=headers()
    )
    assert response.status_code == 422


def test_invalid_condition_enum_returns_422(client):
    response = client.post(
        RULES,
        json=rule_payload(conditions={"region": ["mars"]}),
        headers=headers(),
    )
    assert response.status_code == 422


def test_invalid_work_hours_returns_422(client):
    response = client.post(
        RULES,
        json=rule_payload(
            work_hours=[{"weekday": 1, "start": "18:00", "end": "09:00"}]
        ),
        headers=headers(),
    )
    assert response.status_code == 422


def test_work_hours_overlap_returns_422(client):
    response = client.post(
        RULES,
        json=rule_payload(
            work_hours=[
                {"weekday": 1, "start": "09:00", "end": "12:00"},
                {"weekday": 1, "start": "11:00", "end": "16:00"},
            ]
        ),
        headers=headers(),
    )
    assert response.status_code == 422


def test_missing_identity_returns_401(client):
    response = client.get(RULES)
    assert response.status_code == 401


def test_three_members_allowed_for_round_robin(client):
    rule = create_rule(
        client,
        name=unique_name("三人轮询"),
        strategy="round_robin",
        member_user_ids=[CONSULTANT_A1, CONSULTANT_A2, CONSULTANT_A3],
    )
    assert len(rule["member_user_ids"]) == 3
