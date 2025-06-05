# schemas/mcp.py

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class MessageItem(BaseModel):
    role: str               # “user” / “assistant” / “system” / “summary”
    content: str
    timestamp: datetime

class Memory(BaseModel):
    last_summary: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = {}  # e.g., {"current_step": "...", "last_message": "..."}

class ModelContext(BaseModel):
    memory: Memory
    messages: List[MessageItem]
    tool_inputs: Optional[Dict[str, Any]] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
