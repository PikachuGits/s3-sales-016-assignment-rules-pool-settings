"""S2-IAM integration stub.

The work order allows S2-IAM (identity, role and data scope) to be mocked.
This module is the single integration point:

* ``get_principal`` reads the authenticated principal from trusted headers.
  In production this function is replaced by an S2-IAM token introspection /
  gateway call; nothing else in the code base needs to change.
* ``ConsultantDirectory`` answers "is this user a sales consultant of this
  site?".  The default implementation reads a JSON file so tests and reviewers
  can run without S2-IAM.  Production calls
  ``GET /internal/iam/sites/{site_id}/sales-consultants``.

Only the five headers below are trusted, and only behind the gateway.  Do not
expose this app directly to the internet without replacing the dependency.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import Header, HTTPException

from app.enums import SalesRole

_DEFAULT_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "fixtures" / "iam_consultants.json"
)


@dataclass(frozen=True)
class Principal:
    """Authenticated caller plus the data scope resolved by S2-IAM."""

    user_id: UUID
    org_id: UUID
    site_id: UUID
    role: SalesRole


def get_principal(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    x_site_id: str | None = Header(default=None, alias="X-Site-Id"),
    x_role: str | None = Header(default=None, alias="X-Role"),
) -> Principal:
    """Resolve the caller; missing or malformed identity headers yield 401."""

    if not all((x_user_id, x_org_id, x_site_id, x_role)):
        raise HTTPException(status_code=401, detail="missing_identity_headers")
    try:
        role = SalesRole(x_role)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=401, detail="invalid_role") from exc
    try:
        return Principal(
            user_id=UUID(x_user_id),
            org_id=UUID(x_org_id),
            site_id=UUID(x_site_id),
            role=role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid_identity_headers") from exc


class JsonConsultantDirectory:
    """Read-only consultant roster keyed by ``org_id:site_id``.

    The file format is::

        {"sites": {"<org_uuid>:<site_uuid>": ["<user_uuid>", ...]}}

    The file is read on every call so a test can point
    ``IAM_CONSULTANTS_FILE`` at a temporary file without cache invalidation.
    """

    def __init__(self, path: Path | None = None) -> None:
        override = os.environ.get("IAM_CONSULTANTS_FILE")
        self.path = Path(override) if override else (path or _DEFAULT_DIRECTORY)

    def _load(self) -> dict[str, list[str]]:
        if not self.path.exists():
            raise RuntimeError(
                f"IAM consultant stub not found: {self.path}. "
                "Set IAM_CONSULTANTS_FILE or restore fixtures/iam_consultants.json."
            )
        data = json.loads(self.path.read_text(encoding="utf-8"))
        sites = data.get("sites", {})
        if not isinstance(sites, dict):  # pragma: no cover - defensive
            raise RuntimeError("IAM consultant stub must contain a 'sites' object")
        return {str(key): [str(item).lower() for item in value] for key, value in sites.items()}

    def is_consultant(self, org_id: UUID, site_id: UUID, user_id: UUID) -> bool:
        roster = self._load()
        return str(user_id).lower() in roster.get(f"{org_id}:{site_id}", [])


def get_consultant_directory() -> JsonConsultantDirectory:
    """FastAPI dependency; override it in tests or replace it with S2-IAM."""

    return JsonConsultantDirectory()
