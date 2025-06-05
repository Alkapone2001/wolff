# schemas/tools.py

from pydantic import BaseModel
from typing import Dict, Any

class ToolDefinition(BaseModel):
    name: str                # e.g. "parse_invoice"
    description: str         # brief explanation of what this tool does
    input_schema: Dict[str, Any]   # keys + types needed by the tool
    # (You could later expand to include output_schema if desired)
