# schemas/tools.py

from pydantic import BaseModel
from typing import Dict, Any, List, Optional


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]


class ToolInvocation(BaseModel):
    invoice_number: str
    supplier:       str
    date:           str             # e.g. "2024-03-25"
    due_date:       Optional[str] = None
    line_items:     List[Dict[str, Any]]
    currency_code:  Optional[str] = "USD"
    total:          float           # gross total including VAT
    vat_rate:       float           # VAT percentage, e.g. 8.10


class ToolResult(BaseModel):
    class Config:
        extra = "allow"
