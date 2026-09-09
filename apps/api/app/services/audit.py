import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditEvent


def commit_chunk(
    db: Session, execution_id: uuid.UUID, build_rows: Callable[[int], list[Any]]
) -> None:
    """Commit a batch of rows (including AuditEvents starting at the next free
    sequence number) atomically, retrying only on a sequence-number collision
    from a concurrent writer on the same execution."""
    for attempt in range(5):
        base_seq = (
            db.scalar(
                select(func.max(AuditEvent.sequence)).where(AuditEvent.execution_id == execution_id)
            )
            or 0
        ) + 1
        for row in build_rows(base_seq):
            db.add(row)
        try:
            db.commit()
            return
        except IntegrityError as exc:
            db.rollback()
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name != "uq_audit_events_execution_sequence":
                raise
            if attempt == 4:
                raise
