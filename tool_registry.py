# tool_registry.py

from typing import Dict, Any, Callable

# A type alias: a “tool” is any function that takes a dict and returns a dict.
ToolFn = Callable[[Dict[str, Any]], Dict[str, Any]]

class ToolRegistry:
    def __init__(self):
        self._registry: Dict[str, Dict] = {}

    def register(self, name: str, fn: ToolFn, description: str, input_schema: Dict[str, Any]):
        """
        Add a new tool under the given name.
        `input_schema` is just a JSON‐like description of the expected inputs.
        """
        self._registry[name] = {
            "fn": fn,
            "description": description,
            "input_schema": input_schema
        }

    def get_definition(self, name: str) -> Dict[str, Any]:
        entry = self._registry.get(name)
        if not entry:
            raise KeyError(f"Tool {name!r} not registered")
        return {
            "name": name,
            "description": entry["description"],
            "input_schema": entry["input_schema"]
        }

    def call(self, name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        entry = self._registry.get(name)
        if not entry:
            raise KeyError(f"Tool {name!r} not registered")
        return entry["fn"](inputs)

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "description": entry["description"],
                "input_schema": entry["input_schema"]
            }
            for name, entry in self._registry.items()
        }

# Export a single global registry instance:
tool_registry = ToolRegistry()
