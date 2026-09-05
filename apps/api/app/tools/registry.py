from app.tools.base import BaseTool


class ToolNotFoundError(LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(f"No tool registered with name '{name}'")
        self.name = name


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(name) from None

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())
