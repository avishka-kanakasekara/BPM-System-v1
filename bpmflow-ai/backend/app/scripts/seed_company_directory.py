"""Explicit local seed for BPMFlow Demo Company directory.

Usage (development only):
  python -m app.scripts.seed_company_directory
"""

from __future__ import annotations

from app.company_directory.seed import BPMFLOW_DEMO_COMPANY_NAME, seed_bpmflow_demo_company
from app.company_directory.service import get_company_directory, reset_company_directory
from app.core.config import settings


def main() -> None:
    env = (settings.ENV or "").strip().lower()
    if env in {"production", "prod"} and not settings.DEBUG:
        raise SystemExit("Refusing to seed demo company directory in production")
    reset_company_directory()
    tenant_id = seed_bpmflow_demo_company(get_company_directory())
    print(f"Seeded {BPMFLOW_DEMO_COMPANY_NAME} tenant_id={tenant_id}")


if __name__ == "__main__":
    main()
