from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session


class ToolError(BaseModel):
    code: str
    message: str


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] | None = None
    error: ToolError | None = None

    @classmethod
    def ok(cls, data: BaseModel) -> "ToolResult":
        return cls(success=True, data=data.model_dump(mode="json"))

    @classmethod
    def fail(cls, code: str, message: str) -> "ToolResult":
        return cls(success=False, error=ToolError(code=code, message=message))


class ToolExecutionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class BaseTool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[type[BaseModel]]
    output_schema: ClassVar[type[BaseModel]]

    def execute(self, arguments: dict[str, Any], db: Session) -> ToolResult:
        try:
            validated_input = self.input_schema.model_validate(arguments)
        except ValidationError as exc:
            return ToolResult.fail("INVALID_ARGUMENTS", str(exc))

        try:
            output = self._run(validated_input, db)
        except ToolExecutionError as exc:
            return ToolResult.fail(exc.code, exc.message)

        return ToolResult.ok(output)

    @abstractmethod
    def _run(self, input: BaseModel, db: Session) -> BaseModel: ...
