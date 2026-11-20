"""FastAPI application factory for the S3-SALES-016 delivery."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.sales import router

DESCRIPTION = """
Assignment-rule and public-pool configuration APIs for the membership-space
platform (Stage iii · sales workspace v1).

**Out of scope:** the assignment engine itself, lead/customer ingestion and
front-end screens. This service only owns configuration persistence, validation
and the configuration change log.

**Authentication:** S2-IAM is stubbed. The gateway must inject `X-User-Id`,
`X-Org-Id`, `X-Site-Id` and `X-Role` (`sys_admin` / `club_owner` /
`supervisor` / `consultant`). Replace `app.iam.get_principal` with the real
IAM introspection call in production.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sales assignment & pool settings API",
        version="1.0.0",
        description=DESCRIPTION,
        openapi_tags=[
            {
                "name": "sales-assignment",
                "description": (
                    "Assignment rules, public-pool settings and configuration "
                    "change log."
                ),
            }
        ],
    )
    app.include_router(router)
    return app


app = create_app()
