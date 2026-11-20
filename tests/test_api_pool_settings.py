"""API tests for public-pool settings."""

from __future__ import annotations

from tests.factories import (
    CONSULTANT_A1,
    OWNER_B,
    SITE_B,
    SUPERVISOR_A,
    headers,
)

POOL = "/api/sales/pool-settings"


def test_defaults_are_returned_without_a_row(client):
    response = client.get(POOL, headers=headers())
    assert response.status_code == 200
    body = response.json()
    assert body["is_default"] is True
    assert body["id"] is None
    assert body["recycle_days"] == 7
    assert body["recycle_warn_days"] == 5
    assert body["daily_claim_limit"] == 10
    assert body["holding_limit"] == 150
    assert body["reclaim_cooldown_days"] == 15


def test_warn_days_equal_recycle_days_returns_422(client):
    """Acceptance criterion 1."""

    response = client.put(
        POOL,
        json={"recycle_days": 7, "recycle_warn_days": 7},
        headers=headers(),
    )
    assert response.status_code == 422


def test_warn_days_greater_than_recycle_days_returns_422(client):
    response = client.put(
        POOL,
        json={"recycle_days": 7, "recycle_warn_days": 8},
        headers=headers(),
    )
    assert response.status_code == 422


def test_recycle_days_out_of_range_returns_422(client):
    for value in (2, 31):
        response = client.put(
            POOL, json={"recycle_days": value}, headers=headers()
        )
        assert response.status_code == 422


def test_partial_update_keeps_other_defaults(client):
    response = client.put(
        POOL, json={"recycle_days": 10}, headers=headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recycle_days"] == 10
    assert body["recycle_warn_days"] == 5
    assert body["daily_claim_limit"] == 10
    assert body["is_default"] is False
    assert body["id"]

    follow_up = client.get(POOL, headers=headers()).json()
    assert follow_up["recycle_days"] == 10
    assert follow_up["is_default"] is False


def test_update_can_change_every_field(client):
    payload = {
        "recycle_days": 20,
        "recycle_warn_days": 15,
        "daily_claim_limit": 30,
        "holding_limit": 400,
        "reclaim_cooldown_days": 60,
    }
    response = client.put(POOL, json=payload, headers=headers())
    assert response.status_code == 200
    for key, value in payload.items():
        assert response.json()[key] == value


def test_settings_are_isolated_per_site(client):
    client.put(POOL, json={"recycle_days": 12}, headers=headers())

    response = client.get(POOL, headers=headers(site=SITE_B, user_id=OWNER_B))
    assert response.status_code == 200
    assert response.json()["recycle_days"] == 7
    assert response.json()["is_default"] is True


def test_supervisor_cannot_write_pool_settings(client):
    response = client.put(
        POOL,
        json={"daily_claim_limit": 20},
        headers=headers(role="supervisor", user_id=SUPERVISOR_A),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "role_not_allowed_for_write"


def test_supervisor_and_consultant_can_read_pool_settings(client):
    response = client.get(
        POOL, headers=headers(role="supervisor", user_id=SUPERVISOR_A)
    )
    assert response.status_code == 200

    response = client.get(
        POOL, headers=headers(role="consultant", user_id=CONSULTANT_A1)
    )
    assert response.status_code == 200


def test_pool_write_requires_identity(client):
    response = client.put(POOL, json={"recycle_days": 10})
    assert response.status_code == 401
