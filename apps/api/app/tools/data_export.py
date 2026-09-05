"""Deliberately dangerous demo tools used to prove the Risk Engine blocks
bulk-data-export/external-communication actions before they execute. Neither
tool performs any real network call, shell execution, or file I/O -- each
just returns a fixed, deterministic local result so the gateway/tests can
observe whether execution happened at all.
"""

from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer
from app.tools.base import BaseTool


class ExportCustomerDataInput(BaseModel):
    scope: str = "all"


class ExportCustomerDataOutput(BaseModel):
    exported_records: int
    format: str
    destination: str
    exported_at: datetime


class ExportCustomerDataTool(BaseTool):
    name = "export_customer_data"
    description = "Export customer records to a local demo file (no real export occurs)."
    input_schema = ExportCustomerDataInput
    output_schema = ExportCustomerDataOutput

    def _run(self, input: ExportCustomerDataInput, db: Session) -> ExportCustomerDataOutput:
        record_count = db.scalar(select(func.count()).select_from(Customer)) or 0
        return ExportCustomerDataOutput(
            exported_records=record_count,
            format="csv",
            destination="local_demo_export",
            exported_at=datetime.now(UTC),
        )


class SendExternalEmailInput(BaseModel):
    to: str
    subject: str
    body: str


class SendExternalEmailOutput(BaseModel):
    to: str
    subject: str
    status: str
    sent_at: datetime


class SendExternalEmailTool(BaseTool):
    name = "send_external_email"
    description = "Simulate sending an email externally (no real network call occurs)."
    input_schema = SendExternalEmailInput
    output_schema = SendExternalEmailOutput

    def _run(self, input: SendExternalEmailInput, db: Session) -> SendExternalEmailOutput:
        return SendExternalEmailOutput(
            to=input.to,
            subject=input.subject,
            status="SENT_DEMO_ONLY",
            sent_at=datetime.now(UTC),
        )
