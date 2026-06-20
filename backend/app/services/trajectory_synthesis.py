"""Synthesize a draft workflow graph from an autonomous trajectory."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlmodel import Session, select

from app.db.models import Workflow
from app.db.session import engine
from app.services import workflows as workflow_svc
from app.services.autonomous_workflows import SYNTHESIZED_WORKFLOW_MARKER

if TYPE_CHECKING:
    from app.agents.autonomous import TrajectoryStep

_SYNTH_MARKER = SYNTHESIZED_WORKFLOW_MARKER


def _node_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def trajectory_to_graph(
    objective: str,
    steps: list["TrajectoryStep"],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "start",
            "type": "start",
            "label": "开始",
            "params": {},
        }
    ]
    edges: list[dict[str, Any]] = []
    prev_id = "start"

    for step in steps:
        if isinstance(step.result, dict) and step.result.get("error"):
            continue

        node_id = _node_id(step.tool)
        if step.tool == "navigate":
            url = step.args.get("url") or step.url
            if not step.stable:
                nodes.append({
                    "id": node_id,
                    "type": "vision_navigate",
                    "label": f"Navigate to {url}",
                    "params": {"goal": f"Navigate to {url}"},
                })
            else:
                nodes.append({
                    "id": node_id,
                    "type": "navigate",
                    "label": f"Navigate {url}",
                    "params": {"url": url},
                })
        elif step.tool in ("click_element", "type_text", "select_option"):
            if step.stable:
                nodes.append({
                    "id": node_id,
                    "type": "vision_act",
                    "label": step.thought or step.tool,
                    "params": {
                        "instruction": step.thought or f"{step.tool} index {step.args.get('index')}",
                    },
                })
            else:
                nodes.append({
                    "id": node_id,
                    "type": "vision_act",
                    "label": step.thought or step.tool,
                    "params": {
                        "instruction": step.thought or f"Perform {step.tool}",
                    },
                })
        elif step.tool == "extract":
            nodes.append({
                "id": node_id,
                "type": "vision_extract",
                "label": "Extract data",
                "params": {"instruction": objective},
            })
        elif step.tool == "http_request":
            nodes.append({
                "id": node_id,
                "type": "http_request",
                "label": f"HTTP {step.args.get('method', 'GET')}",
                "params": {
                    "method": step.args.get("method", "GET"),
                    "url": step.args.get("url", ""),
                    "headers": step.args.get("headers") or {},
                    "body": step.args.get("body"),
                },
            })
        elif step.tool in (
            "set", "filter", "sort", "limit", "aggregate",
            "split_out", "remove_duplicates", "rename_keys", "datetime",
        ):
            nodes.append({
                "id": node_id,
                "type": step.tool,
                "label": step.tool,
                "params": step.args.get("params") or step.args,
            })
        else:
            nodes.append({
                "id": node_id,
                "type": "vision_act",
                "label": step.tool,
                "params": {"instruction": step.thought or step.tool},
            })

        edges.append({
            "id": f"e_{prev_id}_{node_id}",
            "source": prev_id,
            "target": node_id,
        })
        prev_id = node_id

    end_id = "end"
    nodes.append({"id": end_id, "type": "end", "label": "结束", "params": {}})
    edges.append({
        "id": f"e_{prev_id}_{end_id}",
        "source": prev_id,
        "target": end_id,
    })

    return {"nodes": nodes, "edges": edges, "start_id": "start"}


def synthesize_workflow(
    objective: str,
    steps: list["TrajectoryStep"],
) -> str:
    """Persist a draft workflow approximating the trajectory; return workflow id."""
    graph = trajectory_to_graph(objective, steps)
    name = f"Draft: {objective[:60]}"
    description = f"{_SYNTH_MARKER}\n\nObjective: {objective}"

    with Session(engine) as session:
        workflow = workflow_svc.create_workflow(
            name=name,
            session=session,
            description=description,
            initial_workflow_json=graph,
            authored_by="planner",
        )
        row = session.get(Workflow, workflow.id)
        if row is not None:
            row.status = "archived"
            session.add(row)
            session.commit()
        return workflow.id


__all__ = ["trajectory_to_graph", "synthesize_workflow", "_SYNTH_MARKER"]
