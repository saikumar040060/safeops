from app.tools.customer import GetPaymentsTool, GetSupportTicketTool, ReadCustomerTool
from app.tools.data_export import ExportCustomerDataTool, SendExternalEmailTool
from app.tools.devops import (
    DeployProductionTool,
    DeployStagingTool,
    GetDeploymentTool,
    ReadLogsTool,
)
from app.tools.payments import RefundPaymentTool
from app.tools.registry import ToolNotFoundError, ToolRegistry
from app.tools.wasmer_analysis import WasmerAnalysisTool

tool_registry = ToolRegistry()
for tool_cls in (
    ReadCustomerTool,
    GetPaymentsTool,
    GetSupportTicketTool,
    RefundPaymentTool,
    ReadLogsTool,
    GetDeploymentTool,
    DeployStagingTool,
    DeployProductionTool,
    ExportCustomerDataTool,
    SendExternalEmailTool,
    WasmerAnalysisTool,
):
    tool_registry.register(tool_cls())

__all__ = ["ToolNotFoundError", "ToolRegistry", "tool_registry"]
