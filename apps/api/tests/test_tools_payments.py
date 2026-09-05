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
