from fastapi import APIRouter, Depends, HTTPException
from tool_registry import tool_registry
from sqlalchemy.orm import Session
from database import SessionLocal
from schemas.tools import ToolDefinition, ToolInvocation, ToolResult# ← now resolves

router = APIRouter(tags=["booking"])   # <— you need this

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/book-invoice/", response_model=ToolResult)
def book_invoice(payload: ToolInvocation, db: Session = Depends(get_db)):
    try:
        result = tool_registry.call("book_payable_invoice", payload.dict())
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Tool error: {e}")
    return result

