from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Payment, Refund
from app.models.enums import PaymentStatus
from app.tools.base import BaseTool, ToolExecutionError


class RefundPaymentInput(BaseModel):
    payment_id: str
    amount: Decimal = Field(gt=0)
    reason: str
    idempotency_key: str


class RefundPaymentOutput(BaseModel):
    payment_id: str
    refund_amount: Decimal
    reason: str
    status: str
    created_at: datetime
    idempotent_replay: bool


class RefundPaymentTool(BaseTool):
    name = "refund_payment"
    description = "Issue a refund for a payment."
    input_schema = RefundPaymentInput
    output_schema = RefundPaymentOutput

    def _run(self, input: RefundPaymentInput, db: Session) -> RefundPaymentOutput:
        existing_refund = db.scalar(
            select(Refund).where(Refund.idempotency_key == input.idempotency_key)
        )
        if existing_refund is not None:
            payment = db.get(Payment, existing_refund.payment_id)
            return RefundPaymentOutput(
                payment_id=payment.payment_id if payment else input.payment_id,
                refund_amount=existing_refund.amount,
                reason=existing_refund.reason,
                status=PaymentStatus.REFUNDED.value,
                created_at=existing_refund.created_at,
                idempotent_replay=True,
            )

        payment = db.scalar(select(Payment).where(Payment.payment_id == input.payment_id))
        if payment is None:
            raise ToolExecutionError("NOT_FOUND", f"Payment '{input.payment_id}' not found")

        if payment.status == PaymentStatus.REFUNDED:
            raise ToolExecutionError(
                "ALREADY_REFUNDED", f"Payment '{input.payment_id}' has already been refunded"
            )

        if input.amount > payment.amount:
            raise ToolExecutionError(
                "INVALID_AMOUNT",
                f"Refund amount {input.amount} exceeds original payment amount {payment.amount}",
            )

        refund = Refund(
            payment_id=payment.id,
            amount=input.amount,
            reason=input.reason,
            idempotency_key=input.idempotency_key,
        )
        payment.status = PaymentStatus.REFUNDED
        db.add(refund)
        db.commit()
        db.refresh(refund)

        return RefundPaymentOutput(
            payment_id=payment.payment_id,
            refund_amount=refund.amount,
            reason=refund.reason,
            status=payment.status.value,
            created_at=refund.created_at,
            idempotent_replay=False,
        )
