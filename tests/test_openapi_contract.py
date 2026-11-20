"""OpenAPI contract tests: every required endpoint is documented."""

from __future__ import annotations

from app.main import create_app


def test_required_paths_and_methods_are_present():
    schema = create_app().openapi()

    expected = {
        "/api/sales/assignment-rules": {"get", "post"},
        "/api/sales/assignment-rules/{rule_id}": {"put"},
        "/api/sales/assignment-rules/{rule_id}/toggle": {"post"},
        "/api/sales/assignment-rules/reorder": {"post"},
        "/api/sales/pool-settings": {"get", "put"},
        "/api/sales/config-logs": {"get"},
    }
    for path, methods in expected.items():
        assert path in schema["paths"], path
        for method in methods:
            assert method in schema["paths"][path], (path, method)


def test_create_documents_201_and_conflict():
    operation = create_app().openapi()["paths"]["/api/sales/assignment-rules"]["post"]
    assert "201" in operation["responses"]
    assert "409" in operation["responses"]
    assert "403" in operation["responses"]


def test_pool_update_documents_422():
    operation = create_app().openapi()["paths"]["/api/sales/pool-settings"]["put"]
    assert "422" in operation["responses"]


def test_schemas_are_exported():
    components = create_app().openapi()["components"]["schemas"]
    for name in (
        "AssignmentRuleCreate",
        "AssignmentRuleUpdate",
        "AssignmentRuleOut",
        "PoolSettingsOut",
        "PoolSettingsUpdate",
        "ConfigLogOut",
    ):
        assert name in components


def test_openapi_endpoint_is_served(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["version"] == "1.0.0"
