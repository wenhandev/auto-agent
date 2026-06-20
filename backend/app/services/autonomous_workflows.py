"""Helpers for autonomous task runs and hidden system workflows."""

from __future__ import annotations

from app.db.models import Run, Workflow

AUTONOMOUS_WORKFLOW_NAME = "__autonomous_tasks__"
SYNTHESIZED_WORKFLOW_MARKER = (
    "[autonomous-synthesized draft — review before scheduling]"
)


def is_hidden_workflow(workflow: Workflow) -> bool:
    """Workflows that should not appear in the workflow library UI."""
    if workflow.name == AUTONOMOUS_WORKFLOW_NAME:
        return True
    description = workflow.description or ""
    if SYNTHESIZED_WORKFLOW_MARKER in description:
        return True
    if workflow.name.startswith("Draft:"):
        return True
    return False


def run_list_label(run: Run, workflow_name: str) -> str:
    """Human-readable label for run history rows."""
    if getattr(run, "mode", "graph") == "autonomous":
        objective = (getattr(run, "objective", None) or "").strip()
        if objective:
            return objective
        return "Autonomous task"
    return workflow_name


__all__ = [
    "AUTONOMOUS_WORKFLOW_NAME",
    "SYNTHESIZED_WORKFLOW_MARKER",
    "is_hidden_workflow",
    "run_list_label",
]
