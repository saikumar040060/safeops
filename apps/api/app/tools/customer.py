from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Payment, SupportTicket
from app.tools.base import BaseTool, ToolExecutionError


class ReadCustomerInput(BaseModel):
    customer_id: str


class ReadCustomerOutput(BaseModel):
    customer_id: str
    name: str
    email: str
    created_at: datetime


class ReadCustomerTool(BaseTool):
    name = "read_customer"
    description = "Read a customer's profile and account details."
    input_schema = ReadCustomerInput
    output_schema = ReadCustomerOutput

    def _run(self, input: ReadCustomerInput, db: Session) -> ReadCustomerOutput:
        customer = db.scalar(select(Customer).where(Customer.customer_id == input.customer_id))
        if customer is None:
            raise ToolExecutionError("NOT_FOUND", f"Customer '{input.customer_id}' not found")
        return ReadCustomerOutput(
            customer_id=customer.customer_id,
            name=customer.name,
            email=customer.email,
            created_at=customer.created_at,
        )


class GetPaymentsInput(BaseModel):
    customer_id: str


class PaymentSummary(BaseModel):
    payment_id: str
    amount: Decimal
    status: str
    created_at: datetime


class GetPaymentsOutput(BaseModel):
    customer_id: str
    payments: list[PaymentSummary]


class GetPaymentsTool(BaseTool):
    name = "get_payments"
    description = "List a customer's payment history."
    input_schema = GetPaymentsInput
    output_schema = GetPaymentsOutput

    def _run(self, input: GetPaymentsInput, db: Session) -> GetPaymentsOutput:
        customer = db.scalar(select(Customer).where(Customer.customer_id == input.customer_id))
        if customer is None:
            raise ToolExecutionError("NOT_FOUND", f"Customer '{input.customer_id}' not found")

        payments = db.scalars(
            select(Payment)
            .where(Payment.customer_id == customer.id)
            .order_by(Payment.created_at.asc())
        ).all()

        return GetPaymentsOutput(
            customer_id=customer.customer_id,
            payments=[
                PaymentSummary(
                    payment_id=p.payment_id,
                    amount=p.amount,
                    status=p.status.value,
                    created_at=p.created_at,
                )
                for p in payments
            ],
        )


class GetSupportTicketInput(BaseModel):
    ticket_id: str


class GetSupportTicketOutput(BaseModel):
    ticket_id: str
    customer_id: str | None
    subject: str
    body: str
    created_at: datetime


class GetSupportTicketTool(BaseTool):
    name = "get_support_ticket"
    description = "Read a support ticket by id."
    input_schema = GetSupportTicketInput
    output_schema = GetSupportTicketOutput

    def _run(self, input: GetSupportTicketInput, db: Session) -> GetSupportTicketOutput:
        ticket = db.scalar(
            select(SupportTicket).where(SupportTicket.ticket_id == input.ticket_id)
        )
        if ticket is None:
            raise ToolExecutionError("NOT_FOUND", f"Support ticket '{input.ticket_id}' not found")

        customer_id = None
        if ticket.customer_id is not None:
            customer = db.get(Customer, ticket.customer_id)
            customer_id = customer.customer_id if customer else None

        return GetSupportTicketOutput(
            ticket_id=ticket.ticket_id,
            customer_id=customer_id,
            subject=ticket.subject,
            body=ticket.body,
            created_at=ticket.created_at,
        )
