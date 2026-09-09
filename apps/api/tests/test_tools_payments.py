from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.tools import tool_registry


def test_refund_payment_creates_refund(seeded_db):
    tool = tool_registry.get("refund_payment")
    result = tool.execute(
        {
            "payment_id": "PAY-9003",
            "amount": "750.00",
            "reason": "Duplicate transaction detected",
            "idempotency_key": "refund-pay-9003-v1",
        },
        seeded_db,
    )

    assert result.success is True
    assert result.data["payment_id"] == "PAY-9003"
    assert result.data["status"] == "REFUNDED"
    assert result.data["idempotent_replay"] is False


def test_refund_payment_is_idempotent(seeded_db):
    tool = tool_registry.get("refund_payment")
    args = {
        "payment_id": "PAY-9003",
        "amount": "750.00",
        "reason": "Duplicate transaction detected",
        "idempotency_key": "refund-pay-9003-v1",
    }

    first = tool.execute(args, seeded_db)
    second = tool.execute(args, seeded_db)

    assert first.success is True
    assert second.success is True
    assert second.data["idempotent_replay"] is True

    from app.models import Refund

    assert seeded_db.query(Refund).filter_by(idempotency_key="refund-pay-9003-v1").count() == 1


def test_concurrent_duplicate_refund_is_idempotent(seeded_db, db_engine):
    tool = tool_registry.get("refund_payment")
    args = {
        "payment_id": "PAY-9003",
        "amount": "750.00",
        "reason": "Duplicate transaction detected",
        "idempotency_key": "refund-pay-9003-concurrent",
    }

    from threading import Barrier, Lock

    refund_select_barrier = Barrier(2)
    payment_select_barrier = Barrier(2)
    read_counts = {"refund": 0, "payment": 0}
    read_counts_lock = Lock()

    def synchronize_reads(conn, cursor, statement, parameters, context, executemany):
        normalized = statement.lower()
        if "from refunds" in normalized and "idempotency_key" in normalized:
            with read_counts_lock:
                read_counts["refund"] += 1
                should_wait = read_counts["refund"] <= 2
            if should_wait:
                refund_select_barrier.wait(timeout=5)
        elif "from payments" in normalized and "payment_id" in normalized:
            with read_counts_lock:
                read_counts["payment"] += 1
                should_wait = read_counts["payment"] <= 2
            if should_wait:
                payment_select_barrier.wait(timeout=5)

    event.listen(db_engine, "after_cursor_execute", synchronize_reads)
    try:

        def execute_refund():
            with Session(db_engine) as session:
                return tool.execute(args, session)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: execute_refund(), range(2)))
    finally:
        event.remove(db_engine, "after_cursor_execute", synchronize_reads)

    assert all(result.success for result in results)
    assert sorted(result.data["idempotent_replay"] for result in results) == [False, True]

    from app.models import Refund

    assert seeded_db.query(Refund).filter_by(idempotency_key=args["idempotency_key"]).count() == 1


def test_refund_payment_rejects_distinct_key_after_refund(seeded_db):
    tool = tool_registry.get("refund_payment")
    original = {
        "payment_id": "PAY-9003",
        "amount": "750.00",
        "reason": "Duplicate transaction detected",
        "idempotency_key": "refund-pay-9003-original",
    }
    assert tool.execute(original, seeded_db).success is True

    result = tool.execute({**original, "idempotency_key": "refund-pay-9003-distinct"}, seeded_db)

    assert result.success is False
    assert result.error.code == "ALREADY_REFUNDED"


def test_refund_payment_rejects_amount_exceeding_original(seeded_db):
    tool = tool_registry.get("refund_payment")
    result = tool.execute(
        {
            "payment_id": "PAY-9001",
            "amount": "999.00",
            "reason": "Too much",
            "idempotency_key": "refund-pay-9001-toomuch",
        },
        seeded_db,
    )

    assert result.success is False
    assert result.error.code == "INVALID_AMOUNT"


def test_refund_payment_rejects_non_positive_amount(seeded_db):
    tool = tool_registry.get("refund_payment")
    result = tool.execute(
        {
            "payment_id": "PAY-9001",
            "amount": "0",
            "reason": "Bad amount",
            "idempotency_key": "refund-pay-9001-zero",
        },
        seeded_db,
    )

    assert result.success is False
    assert result.error.code == "INVALID_ARGUMENTS"


def test_refund_payment_not_found(seeded_db):
    tool = tool_registry.get("refund_payment")
    result = tool.execute(
        {
            "payment_id": "PAY-0000",
            "amount": "10.00",
            "reason": "n/a",
            "idempotency_key": "refund-missing",
        },
        seeded_db,
    )

    assert result.success is False
    assert result.error.code == "NOT_FOUND"
