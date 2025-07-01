# tool_registry.py

from typing import Dict, Any, Callable
from tools.describe_invoice import describe_invoice_tool

# A type alias: a “tool” is any function that takes a dict and returns a dict.
ToolFn = Callable[[Dict[str, Any]], Dict[str, Any]]

class ToolRegistry:
    def __init__(self):
        self._registry: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, fn: ToolFn, description: str, input_schema: Dict[str, Any]):
        if name in self._registry:
            raise KeyError(f"Tool '{name}' is already registered")
        self._registry[name] = {
            "fn": fn,
            "description": description,
            "input_schema": input_schema
        }

    def call(self, name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        entry = self._registry.get(name)
        if not entry:
            raise KeyError(f"Tool '{name}' not registered")
        return entry["fn"](inputs)

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "description": meta["description"],
                "input_schema": meta["input_schema"]
            }
            for name, meta in self._registry.items()
        }

# ─── Instantiate & register ────────────────────────────────────────────────────

tool_registry = ToolRegistry()

from tools.parse_invoice         import parse_invoice_tool
from tools.categorize_expense    import categorize_expense_tool
from tools.book_payable_invoice  import book_payable_invoice_tool

tool_registry.register(
    name="parse_invoice",
    fn=parse_invoice_tool,
    description="Given a base64-encoded PDF, return supplier, date, invoice_number, total, vat.",
    input_schema={"file_bytes": "base64 string of the PDF"}
)

tool_registry.register(
    name="categorize_expense",
    fn=categorize_expense_tool,
    description="Given client_id, invoice_number, supplier and line_items, suggest GL category per line. Uses allowed_accounts list (name+code).",
    input_schema={
        "client_id":      "string",
        "invoice_number": "string",
        "supplier":       "string",
        "line_items":     "List<{description:string,amount:number}>",
        "allowed_accounts": "List<{name:string,code:string}>"
    }
)

tool_registry.register(
    name="book_payable_invoice",
    fn=book_payable_invoice_tool,
    description="Create an A/P invoice in Xero from parsed data.",
    input_schema={
        "invoice_number": "string",
        "supplier":       "string",
        "date":           "YYYY-MM-DD",
        "due_date":       "YYYY-MM-DD",
        "line_items":     "List<{description:string,amount:number,account_code:string}>",
        "currency_code":  "string"
    }
)

tool_registry.register(
    "describe_invoice",
    describe_invoice_tool,
    "Generate a short, clear description of this invoice.",
    {
        "supplier": "Supplier name",
        "invoice_number": "Invoice number",
        "date": "Date",
        "total": "Total amount",
        "line_items": "List of line item descriptions/amounts"
    }
)


print("✅ Registered tools:", list(tool_registry.list_tools().keys()))
