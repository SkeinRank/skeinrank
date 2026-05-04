from __future__ import annotations

from fastapi import FastAPI
from skeinrank_governance_api import GovernanceApiConfig, create_app


def test_public_api_exports_app_factory(tmp_path):
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
        )
    )

    assert isinstance(app, FastAPI)
