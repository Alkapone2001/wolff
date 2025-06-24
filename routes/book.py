from fastapi import APIRouter, Depends, HTTPException
from tool_registry import tool_registry
from sqlalchemy.orm import Session
from database import SessionLocal
from schemas.tools import ToolDefinition, ToolInvocation, ToolResult

router = APIRouter(tags=["booking"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/book-invoice/", response_model=ToolResult)
def book_invoice(payload: ToolInvocation, db: Session = Depends(get_db)):
    # 1. Run categorization if not already categorized
    line_items = payload.line_items
    if not all("category" in li for li in line_items):
        cat_result = tool_registry.call("categorize_expense", {
            "client_id": getattr(payload, "client_id", "default_client"),
            "invoice_number": payload.invoice_number,
            "supplier": payload.supplier,
            "line_items": line_items
        })
        categorized = cat_result["categories"]
        for i, li in enumerate(line_items):
            li["category"] = categorized[i]["category"]

    # 2. Book invoice (now uses dynamic account code per category)
    try:
        result = tool_registry.call("book_payable_invoice", payload.dict())
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Tool error: {e}")
    return result

# (Optional) Expose mapping for admin/debug
@router.get("/accounts/mapping/")
def account_mapping():
    from tools.xero_accounts import _category_account_map
    return _category_account_map
