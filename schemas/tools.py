# schemas/tools.py

from pydantic import BaseModel
from typing import Dict, Any, List, Optional


class ToolDefinition(BaseModel):
    name: str                      # e.g. "parse_invoice"
    description: str               # what the tool does
    input_schema: Dict[str, Any]   # expected inputs

class ToolInvocation(BaseModel):
    invoice_number: str
    supplier:       str
    date:           str            # YYYY-MM-DD
    due_date:       str            # YYYY-MM-DD
    line_items:     List[Dict[str, Any]]
    currency_code: Optional[str] = "USD"

class ToolResult(BaseModel):
    # allow any extra fields so you can return whatever your tool produces
    class Config:
        extra = 'allow'
