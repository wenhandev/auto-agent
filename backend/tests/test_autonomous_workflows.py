"""Tests for hidden autonomous workflows."""

from app.db.models import Workflow
from app.services.autonomous_workflows import (
    AUTONOMOUS_WORKFLOW_NAME,
    SYNTHESIZED_WORKFLOW_MARKER,
    is_hidden_workflow,
    run_list_label,
)


def test_hidden_system_workflow() -> None:
    wf = Workflow(name=AUTONOMOUS_WORKFLOW_NAME)
    assert is_hidden_workflow(wf)


def test_hidden_synthesized_workflow() -> None:
    wf = Workflow(
        name="Draft: find price",
        description=f"{SYNTHESIZED_WORKFLOW_MARKER}\n\nObjective: x",
    )
    assert is_hidden_workflow(wf)


def test_visible_user_workflow() -> None:
    wf = Workflow(name="My workflow", description="user created")
    assert not is_hidden_workflow(wf)


def test_run_list_label_uses_objective() -> None:
    from app.db.models import Run

    run = Run(
        workflow_id="wf",
        workflow_version_id="v",
        status="completed",
        mode="autonomous",
        objective="找到最贵的 iPhone",
    )
    assert run_list_label(run, AUTONOMOUS_WORKFLOW_NAME) == "找到最贵的 iPhone"
