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

# Export the singleton registry
tool_registry = ToolRegistry()


# -------------------------------------------------------------------------------
# === Register existing tools here: ===
# -------------------------------------------------------------------------------
from tools.parse_invoice import parse_invoice_tool
tool_registry.register(
    name="parse_invoice",
    fn=parse_invoice_tool,
    description="Given a base64‐encoded PDF, return supplier, date, invoice_number, total, vat.",
    input_schema={
        "file_bytes": "base64 string of the PDF"
    }
)

# <<-- ADD THE NEW CATEGORIZE_EXPENSE REGISTRATION BELOW: -->>
from tools.categorize_expense import categorize_expense_tool
tool_registry.register(
    name="categorize_expense",
    fn=categorize_expense_tool,
    description="Given invoice_number, supplier, and line_items, return a suggested GL category for each line.",
    input_schema={
        "client_id": "string",
        "invoice_number": "string",
        "supplier": "string",
        "line_items": "List of { description: string, amount: number }"
    }
)
