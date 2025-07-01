# routes/describe.py

from fastapi import APIRouter, Body
from tools.describe_invoice import describe_invoice_tool

router = APIRouter(tags=["Describe"])

@router.post("/describe-invoice/")
async def describe_invoice(payload: dict = Body(...)):
    return describe_invoice_tool(payload)
