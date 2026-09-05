from app.tools import tool_registry


def test_read_customer_success(seeded_db):
    result = tool_registry.get("read_customer").execute({"customer_id": "CUST-1001"}, seeded_db)

    assert result.success is True
    assert result.data["customer_id"] == "CUST-1001"
    assert result.data["name"] == "Jordan Rivera"


def test_read_customer_not_found(seeded_db):
    result = tool_registry.get("read_customer").execute({"customer_id": "CUST-9999"}, seeded_db)

    assert result.success is False
    assert result.error.code == "NOT_FOUND"


def test_get_payments_returns_seeded_payments(seeded_db):
    result = tool_registry.get("get_payments").execute({"customer_id": "CUST-1001"}, seeded_db)

    assert result.success is True
    payment_ids = {p["payment_id"] for p in result.data["payments"]}
    assert payment_ids == {"PAY-9001", "PAY-9002", "PAY-9003"}

    duplicate_amounts = [p["amount"] for p in result.data["payments"] if p["amount"] == "750.00"]
    assert len(duplicate_amounts) == 2


def test_get_support_ticket_success(seeded_db):
    result = tool_registry.get("get_support_ticket").execute({"ticket_id": "TCK-4820"}, seeded_db)

    assert result.success is True
    assert result.data["subject"] == "Duplicate charge on my account"
    assert result.data["customer_id"] == "CUST-1001"


def test_malicious_support_ticket_exists_in_seed_data(seeded_db):
    result = tool_registry.get("get_support_ticket").execute({"ticket_id": "TCK-4837"}, seeded_db)

    assert result.success is True
    assert "ignore all previous instructions" in result.data["body"].lower()
    assert "attacker@example.com" in result.data["body"]
