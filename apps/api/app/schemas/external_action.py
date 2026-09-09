import json
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ExternalActionStatus, IntegrationType

# Bounded input per Milestone 11 section 4/27: none of these are arbitrary
# -- they mirror existing column sizes where one already exists
# (Execution.objective is String(4000), a Source.content ticket-body-sized
# field is bounded generously but not unbounded) and are otherwise chosen
# conservatively to keep a single request small enough that Risk Engine /
# audit storage never has to deal with an unbounded payload.
MAX_OBJECTIVE_LENGTH = 4000
MAX_SOURCE_CONTENT_LENGTH = 20_000
MAX_SOURCE_TYPE_LENGTH = 100
MAX_SOURCES = 10
MAX_ARGUMENTS_JSON_BYTES = 32_768
MAX_ARGUMENT_NESTING_DEPTH = 6
MAX_EXTERNAL_REQUEST_ID_LENGTH = 255
MAX_EXTERNAL_AGENT_ID_LENGTH = 255
MAX_TOOL_NAME_LENGTH = 255


def _json_depth(value: Any, current: int = 0) -> int:
    if current > MAX_ARGUMENT_NESTING_DEPTH:
        return current
    if isinstance(value, dict):
        if not value:
            return current
        return max(_json_depth(v, current + 1) for v in value.values())
    if isinstance(value, list):
        if not value:
            return current
        return max(_json_depth(v, current + 1) for v in value)
    return current


class SourceInput(BaseModel):
    """Untrusted external context. `trust` is intentionally NOT settable
    to TRUSTED by a bare request field -- ExternalActionService defaults
    every externally supplied source to UNTRUSTED and only ever upgrades
    it if the integration's own configuration explicitly allows that
    specific source type to be trusted (see section 16). Accepting a
    caller-declared TRUSTED here would let any external agent falsely mark
    its own injected content as safe, defeating the Risk Engine's
    prompt-injection detection entirely.
    """

    type: str = Field(min_length=1, max_length=MAX_SOURCE_TYPE_LENGTH)
    content: str = Field(max_length=MAX_SOURCE_CONTENT_LENGTH)


class SubmitActionRequest(BaseModel):
    integration_type: IntegrationType = IntegrationType.GENERIC
    external_request_id: str = Field(min_length=1, max_length=MAX_EXTERNAL_REQUEST_ID_LENGTH)
    external_agent_id: str | None = Field(default=None, max_length=MAX_EXTERNAL_AGENT_ID_LENGTH)
    safeops_agent_id: uuid.UUID
    execution_id: uuid.UUID | None = None
    tool_name: str = Field(min_length=1, max_length=MAX_TOOL_NAME_LENGTH)
    arguments: dict[str, Any] = Field(default_factory=dict)
    objective: str | None = Field(default=None, max_length=MAX_OBJECTIVE_LENGTH)
    sources: list[SourceInput] = Field(default_factory=list, max_length=MAX_SOURCES)

    @field_validator("tool_name")
    @classmethod
    def _tool_name_shape(cls, value: str) -> str:
        if not value.replace("_", "").isalnum():
            raise ValueError("tool_name must be alphanumeric/underscore only")
        return value

    @field_validator("arguments")
    @classmethod
    def _bounded_arguments(cls, value: dict[str, Any]) -> dict[str, Any]:
        serialized = json.dumps(value, default=str)
        if len(serialized.encode("utf-8")) > MAX_ARGUMENTS_JSON_BYTES:
            raise ValueError(
                f"arguments payload exceeds {MAX_ARGUMENTS_JSON_BYTES} bytes when serialized"
            )
        if _json_depth(value) > MAX_ARGUMENT_NESTING_DEPTH:
            raise ValueError(f"arguments nesting exceeds {MAX_ARGUMENT_NESTING_DEPTH} levels")
        return value


class ActionResponse(BaseModel):
    status: Literal["EXECUTED", "REQUIRES_APPROVAL", "BLOCKED", "FAILED", "PROCESSING"]
    code: str | None = None
    message: str
    external_request_id: str
    execution_id: uuid.UUID
    approval_request_id: uuid.UUID | None = None
    result: dict[str, Any] | None = None


class ActionStatusResponse(BaseModel):
    external_request_id: str
    status: ExternalActionStatus
    execution_id: uuid.UUID
    approval_request_id: uuid.UUID | None = None
    tool_name: str
    result: dict[str, Any] | None = None
    error_code: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ToolDescriptor(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
