"""Opt-in Wasmer tool. Only fixed guest programs, never host-side eval/shell."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.tools.base import BaseTool, ToolExecutionError


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["summary", "containment_probe"] = "summary"
    csv_data: str = Field(default="amount\n12.50\n7.50\n", max_length=16000)


class AnalysisOutput(BaseModel):
    runtime: str
    package: str
    input_sha256: str
    result: dict


class WasmerAnalysisTool(BaseTool):
    name = "wasmer_analyze"
    description = "Analyze a small CSV or verify containment in a no-network Wasmer sandbox."
    input_schema = AnalysisInput
    output_schema = AnalysisOutput

    def _run(self, input: AnalysisInput, db: Session) -> AnalysisOutput:
        worker = Path(__file__).with_name("wasmer_worker.py")
        # A separate host process puts a wall-clock bound around native compilation/execution.
        # It does NOT itself provide isolation; Wasmer is the guest security boundary.
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "SYSTEMROOT")}
        env["SAFEOPS_WASMER_CACHE"] = os.environ.get(
            "SAFEOPS_WASMER_CACHE", str(Path.cwd() / ".wasmer")
        )
        try:
            output = subprocess.run(
                [sys.executable, str(worker)],
                input=input.model_dump_json(),
                text=True,
                capture_output=True,
                timeout=180,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolExecutionError(
                "SANDBOX_TIMEOUT", "Wasmer worker exceeded 180 seconds"
            ) from exc
        if output.returncode:
            raise ToolExecutionError("SANDBOX_FAILED", "Wasmer worker failed; no host fallback")
        try:
            result = json.loads(output.stdout)
        except (ValueError, TypeError) as exc:
            raise ToolExecutionError("SANDBOX_PROTOCOL", "Invalid sandbox response") from exc
        return AnalysisOutput(
            runtime="wasmer-sdk",
            package="python/python@=3.13.18",
            input_sha256=hashlib.sha256(input.model_dump_json().encode()).hexdigest(),
            result=result,
        )
