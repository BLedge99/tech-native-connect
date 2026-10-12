import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_current_user_requires_a_session() -> None:
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthenticated", "message": "Sign in to continue."}
    }


def test_registration_validation_uses_the_shared_error_shape() -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "short", "display_name": "S"},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert set(error["fields"]) == {"email", "password", "display_name"}


def test_logout_is_idempotent_without_a_session() -> None:
    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PATCH", "/api/v1/users/me", {}),
        ("GET", "/api/v1/courses", None),
        ("GET", "/api/v1/skills", None),
        ("GET", "/api/v1/interests", None),
        ("GET", "/api/v1/users/00000000-0000-0000-0000-000000000001", None),
        ("GET", "/api/v1/matches", None),
        ("GET", "/api/v1/connections", None),
        ("GET", "/api/v1/threads", None),
        ("GET", "/api/v1/notifications", None),
        ("GET", "/api/v1/ideas", None),
    ],
)
def test_user_data_routes_require_a_session(method, path, body) -> None:
    response = client.request(method, path, json=body) if body is not None else client.request(method, path)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/admin/overview", None),
        ("GET", "/api/v1/admin/users", None),
        ("GET", "/api/v1/admin/users/00000000-0000-0000-0000-000000000001", None),
        ("POST", "/api/v1/admin/users/00000000-0000-0000-0000-000000000001/deactivate", None),
        ("POST", "/api/v1/admin/users/00000000-0000-0000-0000-000000000001/reactivate", None),
        ("POST", "/api/v1/admin/users/00000000-0000-0000-0000-000000000001/grant-admin", None),
        ("DELETE", "/api/v1/admin/users/00000000-0000-0000-0000-000000000001/admin", None),
        ("GET", "/api/v1/admin/courses", None),
        ("POST", "/api/v1/admin/courses", {"name": "Course"}),
        ("PATCH", "/api/v1/admin/courses/00000000-0000-0000-0000-000000000001", {"name": "Course"}),
        ("GET", "/api/v1/admin/skills", None),
        ("POST", "/api/v1/admin/skills", {"name": "Python", "category": "Language"}),
        ("PATCH", "/api/v1/admin/skills/00000000-0000-0000-0000-000000000001", {"name": "Python"}),
        ("DELETE", "/api/v1/admin/skills/00000000-0000-0000-0000-000000000001", None),
        ("GET", "/api/v1/admin/interests", None),
        ("POST", "/api/v1/admin/interests", {"name": "Climate tech"}),
        ("PATCH", "/api/v1/admin/interests/00000000-0000-0000-0000-000000000001", {"name": "Climate"}),
        ("DELETE", "/api/v1/admin/interests/00000000-0000-0000-0000-000000000001", None),
        ("GET", "/api/v1/admin/audit", None),
    ],
)
def test_every_admin_route_requires_a_session(method, path, body) -> None:
    response = client.request(method, path, json=body) if body is not None else client.request(method, path)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"