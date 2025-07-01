from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from schemas.tools import ToolInvocation, ToolResult
from tools.book_payable_invoice import book_payable_invoice_tool  # NEW: this is now async!
from tools.categorize_expense import categorize_expense_tool_async
from tools.xero_accounts import get_all_expense_accounts

router = APIRouter(tags=["booking"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/book-invoice/", response_model=ToolResult)
async def book_invoice(payload: ToolInvocation, db: Session = Depends(get_db)):
    # 1. Run categorization if not already categorized
    line_items = payload.line_items
    if not all("category" in li for li in line_items):
        cat_result = await categorize_expense_tool_async({
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
        result = await book_payable_invoice_tool(payload.dict())
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Tool error: {e}")
    return result

# (Optional) Expose mapping for admin/debug
@router.get("/accounts/mapping/")
def account_mapping():
    from tools.xero_accounts import _category_account_map
    return _category_account_map

@router.get("/accounts/expense/")
async def get_expense_accounts():
    """
    Returns all Xero EXPENSE accounts (name and code) as a list.
    """
    return await get_all_expense_accounts()

