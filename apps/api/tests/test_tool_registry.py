import pytest

from app.tools import ToolNotFoundError, tool_registry

EXPECTED_TOOL_NAMES = {
    "read_customer",
    "get_payments",
    "get_support_ticket",
    "refund_payment",
    "read_logs",
    "get_deployment",
    "deploy_staging",
    "deploy_production",
    "export_customer_data",
    "send_external_email",
    "wasmer_analyze",
}


def test_registry_resolves_all_expected_tools():
    names = {tool.name for tool in tool_registry.all()}
    assert names == EXPECTED_TOOL_NAMES

    for name in EXPECTED_TOOL_NAMES:
        assert tool_registry.get(name).name == name


def test_unknown_tool_lookup_raises():
    with pytest.raises(ToolNotFoundError):
        tool_registry.get("does_not_exist")


def test_invalid_tool_arguments_return_structured_error(seeded_db):
    result = tool_registry.get("read_customer").execute({}, seeded_db)

    assert result.success is False
    assert result.error.code == "INVALID_ARGUMENTS"
