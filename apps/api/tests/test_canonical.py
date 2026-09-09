import uuid

from app.core.canonical import hash_external_action_payload


def _hash(**overrides):
    defaults = dict(
        safeops_agent_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        execution_id=None,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        objective="investigate",
    )
    defaults.update(overrides)
    return hash_external_action_payload(**defaults)


def test_same_logical_payload_hashes_identically_regardless_of_dict_order():
    a = hash_external_action_payload(
        safeops_agent_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        execution_id=None,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001", "note": "x"},
        objective="investigate",
    )
    b = hash_external_action_payload(
        safeops_agent_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        execution_id=None,
        tool_name="read_customer",
        arguments={"note": "x", "customer_id": "CUST-1001"},
        objective="investigate",
    )
    assert a == b


def test_different_arguments_hash_differently():
    assert _hash(arguments={"customer_id": "CUST-1001"}) != _hash(
        arguments={"customer_id": "CUST-9999"}
    )


def test_different_tool_name_hashes_differently():
    assert _hash(tool_name="read_customer") != _hash(tool_name="get_payments")


def test_different_agent_hashes_differently():
    assert _hash(safeops_agent_id=uuid.UUID("00000000-0000-0000-0000-000000000001")) != _hash(
        safeops_agent_id=uuid.UUID("00000000-0000-0000-0000-000000000002")
    )


def test_hash_is_a_hex_sha256_digest():
    h = _hash()
    assert len(h) == 64
    int(h, 16)  # must be valid hex
