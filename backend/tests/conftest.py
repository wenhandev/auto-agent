from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db.migrations import (
    add_credential_type_column,
    add_parent_run_id_on_first_run,
    bootstrap_orgs_on_startup,
    ensure_org_columns,
    ensure_oauth_domain_rule_table,
    ensure_user_platform_admin_column,
    ensure_workflow_visibility_column,
    ensure_run_browser_profile_column,
    ensure_run_browser_session_column,
    ensure_browser_session_memory_column,
    ensure_browser_session_provider_columns,
    ensure_run_browser_provider_columns,
    ensure_run_mode_and_task_columns,
    ensure_run_parameters_json_column,
    ensure_run_cost_columns,
    ensure_selector_cache_column,
    ensure_run_totp_identifier_column,
    ensure_run_record_video_column,
    ensure_run_trigger_columns,
    ensure_trigger_parameters_json_column,
    ensure_trigger_poll_app_columns,
    ensure_trigger_scheduling_columns,
    ensure_workflow_status_column,
    ensure_workflow_version_parameters_column,
)
from app.db.session import init_db
from app.main import app


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """HTTP client with app lifespan started (registers dispatcher main loop)."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_db_schema():
    init_db()
    ensure_org_columns()
    ensure_workflow_visibility_column()
    ensure_user_platform_admin_column()
    ensure_oauth_domain_rule_table()
    bootstrap_orgs_on_startup()
    add_credential_type_column()
    ensure_run_trigger_columns()
    add_parent_run_id_on_first_run()
    ensure_trigger_poll_app_columns()
    ensure_run_mode_and_task_columns()
    ensure_run_browser_profile_column()
    ensure_run_browser_session_column()
    ensure_browser_session_memory_column()
    ensure_browser_session_provider_columns()
    ensure_run_browser_provider_columns()
    ensure_workflow_status_column()
    ensure_workflow_version_parameters_column()
    ensure_run_parameters_json_column()
    ensure_run_totp_identifier_column()
    ensure_run_record_video_column()
    ensure_run_cost_columns()
    ensure_selector_cache_column()
    ensure_trigger_parameters_json_column()
    ensure_trigger_scheduling_columns()


@pytest.fixture(autouse=True)
def _scope_orphan_org_rows():
    from app.services.orgs import scope_orphan_rows_to_default_org

    scope_orphan_rows_to_default_org()
