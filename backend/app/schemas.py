from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

NodeType = Literal[
    "start",
    "end",
    "navigate",
    "click",
    "fill",
    "extract",
    "wait",
    "fuzzy_action",
    "vision_navigate",
    "vision_act",
    "vision_extract",
    "condition",
    "switch",
    "merge",
    "set",
    "filter",
    "sort",
    "limit",
    "aggregate",
    "split_out",
    "remove_duplicates",
    "rename_keys",
    "datetime",
    "http_request",
    "integration",
    "read_file",
    "write_file",
    "send_email",
    "parse_json",
    "parse_csv",
    "foreach",
    "subworkflow",
    "validation",
    "text_prompt",
    "while_loop",
    "print_page",
    "file_upload",
    "file_download",
    "goto_url",
    "approval",
    "login",
]


class ApprovalInputSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["string", "number", "boolean"]
    default: Optional[Any] = None
    required: bool = False
    label: Optional[str] = None


class ApprovalParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    inputs: list[ApprovalInputSpec] = Field(default_factory=list)
    approve_label: str = "同意"
    reject_label: str = "拒绝"


class LoginParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: str
    url: Optional[str] = None
    success_criteria: Optional[str] = None
    totp_identifier: Optional[str] = None
    totp_fallback_approval: bool = False


class HttpRequestParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"] = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Optional[Any] = None
    body_kind: Literal["json", "text", "form", "none"] = "json"
    timeout_ms: int = Field(default=15_000, ge=1, le=120_000)


class IntegrationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: str
    resource: str
    operation: str
    credential: Optional[str] = None
    fields: dict[str, Any] = Field(default_factory=dict)


class ReadFileParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    encoding: str = "utf-8"
    max_bytes: int = Field(default=1_048_576, ge=1, le=10_485_760)


class WriteFileParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    contents: str
    encoding: str = "utf-8"


class SendEmailParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    smtp_credential: str
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    body_kind: Literal["text", "html"] = "text"
    attachments: list[str] = Field(default_factory=list)


class ParseJsonParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: Any


class ParseCsvParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: Any
    has_header: bool = True
    delimiter: str = ","


class VisionNavigateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    max_steps: Optional[int] = Field(default=None, ge=1, le=50)
    success_criteria: Optional[str] = None


class VisionActParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str


class VisionExtractParams(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    instruction: str
    json_schema: Optional[dict[str, Any]] = Field(default=None, alias="schema")


class SubworkflowParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    version_id: Optional[str] = None
    input: dict[str, Any] = Field(default_factory=dict)


class ConditionPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: Any
    op: Literal[
        "==", "!=", ">", ">=", "<", "<=", "in", "not_in", "is_truthy", "is_falsy"
    ]
    right: Optional[Any] = None


class RetryPolicy(BaseModel):
    max_attempts: int = Field(ge=1, le=10)
    backoff_ms: int = Field(ge=0, le=60_000)


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
            "vision_navigate->{goal,max_steps?,success_criteria?}, "
            "vision_act->{instruction}, vision_extract->{instruction,schema?}, "
            "condition->{expr}."
        ),
    )
    retry: Optional[RetryPolicy] = None
    on_error: Literal["fail_run", "continue", "branch"] = "fail_run"

    @model_validator(mode="after")
    def _validate_params_by_type(self) -> Node:
        if self.type == "approval":
            ApprovalParams.model_validate(self.params or {})
        if self.type == "login":
            LoginParams.model_validate(self.params or {})
        return self


class Edge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    source: str
    target: str
    when: Literal["true", "false"] | None = Field(
        default=None,
        description="Set on edges leaving a `condition` node to select a branch.",
    )
    case: str | None = Field(
        default=None,
        description="Set on edges leaving a `switch` node to select a branch.",
    )
    kind: Literal["next", "on_error"] = "next"


ParameterType = Literal["string", "number", "boolean", "secret", "json", "file"]

_RESERVED_PARAMETER_NAMES = frozenset(
    {"nodes", "cred", "run", "trigger", "params", "item", "items", "input_items"}
)


class WorkflowParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    type: ParameterType
    label: Optional[str] = None
    required: bool = False
    default: Optional[Any] = None
    description: Optional[str] = None


class Workflow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nodes: list[Node]
    edges: list[Edge]
    start_id: str = Field(..., description="The id of the first node to execute.")
    parameters: list[WorkflowParameter] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_parameters(self) -> Workflow:
        seen: set[str] = set()
        for param in self.parameters:
            if param.name in _RESERVED_PARAMETER_NAMES:
                raise ValueError(
                    f"parameter name {param.name!r} shadows a reserved namespace"
                )
            if param.name in seen:
                raise ValueError(f"duplicate parameter name {param.name!r}")
            seen.add(param.name)
        return self


class ForeachParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Any
    body_workflow: Workflow
    max_iterations: int = Field(default=1000, ge=1, le=10_000)
    parallel: bool = False


class ConditionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicate: Optional[ConditionPredicate] = None
    expr: Optional[str] = None


class ValidationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicate: ConditionPredicate


class TextPromptParams(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    prompt: str
    system: Optional[str] = None
    json_schema: Optional[dict[str, Any]] = Field(default=None, alias="schema")


class WhileLoopParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicate: ConditionPredicate
    body_workflow: Workflow
    max_iterations: int = Field(default=100, ge=1, le=1000)


class GotoUrlParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = "load"


class PrintPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Optional[str] = None


class FileUploadParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    target: Optional[str] = None


class FileDownloadParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Optional[str] = None
    timeout_ms: int = Field(default=30_000, ge=1, le=120_000)


class GenerateWorkflowRequest(BaseModel):
    description: str


class WSStartFrame(BaseModel):
    type: Literal["start"]
    workflow: Workflow
