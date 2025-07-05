# routes/batch_book.py

from fastapi import APIRouter, Body
from typing import List
from tools.book_payable_invoice import book_payable_invoice_tool
from tools.categorize_expense import categorize_expense_tool_async  # Make sure this is async!

router = APIRouter()

@router.post("/batch/book-invoices/")
async def batch_book_invoices(payload: List[dict] = Body(...)):
    """
    Accepts a list of invoice dicts, each may contain 'pdf_bytes'.
    For each, AI-categorizes line items (if missing), then books to Xero (with PDF attachment).
    """
    results = []
    for inv in payload:
        # AI categorize if any line item is missing a category
        needs_category = any(not li.get("category") for li in inv.get("line_items", []))
        if needs_category:
            # Forward allowed_categories if present, else all
            allowed_categories = inv.get("allowed_categories")
            cat_input = {
                "invoice_number": inv.get("invoice_number"),
                "supplier": inv.get("supplier"),
                "line_items": inv.get("line_items", [])
            }
            if allowed_categories is not None:
                cat_input["allowed_categories"] = allowed_categories
            cat_result = await categorize_expense_tool_async(cat_input)
            desc2cat = {x["description"]: x["category"] for x in cat_result.get("categories", [])}
            for li in inv["line_items"]:
                if not li.get("category"):
                    li["category"] = desc2cat.get(li["description"], "generalexpenses")
        # Book invoice (with PDF bytes if present)
        try:
            res = await book_payable_invoice_tool(inv)
            results.append(res)
        except Exception as e:
            results.append({"error": str(e)})
    return results
