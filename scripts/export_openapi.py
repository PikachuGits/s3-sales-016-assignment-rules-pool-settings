#!/usr/bin/env python
"""Export the FastAPI OpenAPI document to ``docs/openapi.json``.

    .venv/bin/python scripts/export_openapi.py

No database connection is needed: the schema is generated from the app's
Pydantic models and route declarations.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.main import create_app  # noqa: E402


def main() -> None:
    schema = create_app().openapi()
    output = BASE_DIR / "docs" / "openapi.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output.relative_to(BASE_DIR)} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
