# routes/batch_book.py

from fastapi import APIRouter, Body
from typing import List
from tools.book_payable_invoice import book_payable_invoice_tool
from tools.categorize_expense import categorize_expense_tool_async
import anyio

router = APIRouter()

@router.post("/batch/book-invoices/")
async def batch_book_invoices(payload: List[dict] = Body(...)):
    """
    Accepts a list of invoice dicts.
    For each, AI-categorizes line items (if missing), then books to Xero.
    """
    results = []
    for inv in payload:
        # AI categorize if any line item is missing a category
        needs_category = any(not li.get("category") for li in inv.get("line_items", []))
        if needs_category:
            cat_result = await categorize_expense_tool_async({
                "invoice_number": inv.get("invoice_number"),
                "supplier": inv.get("supplier"),
                "line_items": inv.get("line_items", [])
            })
            desc2cat = {x["description"]: x["category"] for x in cat_result.get("categories", [])}
            # Patch categories
            for li in inv["line_items"]:
                if not li.get("category"):
                    li["category"] = desc2cat.get(li["description"], "General Expenses")
        # Book invoice
        try:
            res = await book_payable_invoice_tool(inv)
            results.append(res)
        except Exception as e:
            results.append({"error": str(e)})
    return results
