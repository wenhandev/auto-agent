from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NodeType = Literal[
    "start",
    "end",
    "navigate",
    "click",
    "fill",
    "extract",
    "wait",
    "fuzzy_action",
    "condition",
]


class Node(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Stable node identifier shared with the canvas")
    type: NodeType = Field(..., description="One of the allowed NodeType values")
    label: str = Field(
        ...,
        description=(
            "Human-readable text shown on the flowchart, written in the user's "
            "own vocabulary (Chinese or English)."
        ),
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Type-specific parameters. Examples: "
            "navigate->{url}, click->{selector}, fill->{selector,value}, "
            "wait->{ms}, extract->{instruction}, fuzzy_action->{instruction}, "
            "condition->{expr}."
        ),
    )


class Edge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    source: str
    target: str
    when: Literal["true", "false"] | None = Field(
        default=None,
        description="Set on edges leaving a `condition` node to select a branch.",
    )


class Workflow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nodes: list[Node]
    edges: list[Edge]
    start_id: str = Field(..., description="The id of the first node to execute.")


class GenerateWorkflowRequest(BaseModel):
    description: str


class WSStartFrame(BaseModel):
    type: Literal["start"]
    workflow: Workflow
