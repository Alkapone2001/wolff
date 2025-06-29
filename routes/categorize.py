# routes/categorize.py

from fastapi import APIRouter, Depends, HTTPException, Request, Body
from sqlalchemy.orm import Session
from database import SessionLocal
from schemas.mcp import ModelContext, MessageItem, ToolDefinition
from tool_registry import tool_registry
from context_manager import build_model_context, log_message, auto_summarize_if_needed, get_or_create_context, update_context_step, update_last_message
from datetime import datetime
import json
import logging

router = APIRouter(tags=["Categorize Expense"])
logger = logging.getLogger("routes.categorize")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/categorize-expense/")
async def categorize_expense(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    client_id = payload.get("client_id")
    invoice_number = payload.get("invoice_number")
    supplier = payload.get("supplier")
    line_items = payload.get("line_items", [])

    if not client_id or not invoice_number or not supplier or not isinstance(line_items, list):
        raise HTTPException(status_code=400, detail="Missing or invalid fields in request body")

    try:
        model_ctx: ModelContext = build_model_context(db, client_id)
    except Exception:
        get_or_create_context(db, client_id)
        try:
            model_ctx: ModelContext = build_model_context(db, client_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Context build error (after create): {e}")

    model_ctx.messages.append(
        MessageItem(
            role="user",
            content=f"Please categorize invoice {invoice_number} from supplier {supplier}. Line items: {json.dumps(line_items)}",
            timestamp=datetime.utcnow()
        )
    )

    all_tools = []
    for name, info in tool_registry.list_tools().items():
        all_tools.append(
            ToolDefinition(
                name=name,
                description=info["description"],
                input_schema=info["input_schema"]
            )
        )
    model_ctx.tools = all_tools

    # Get allowed categories from Xero
    from tools.xero_accounts import get_all_expense_accounts
    allowed_accounts = await get_all_expense_accounts()
    allowed_categories = [a["name"] for a in allowed_accounts]

    # 2) Tool selection by GPT (unchanged)
    from openai import OpenAI
    client = OpenAI()

    system_prompt = {
        "role": "system",
        "content": json.dumps(model_ctx.dict(), default=str)
    }
    user_prompt = {
        "role": "user",
        "content": (
            "Respond with ONLY JSON: {\"tool\": \"categorize_expense\"}. "
            "Do not write anything else. Do not add notes."
        )
    }

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[system_prompt, user_prompt],
            temperature=0
        )
        raw = response.choices[0].message.content
        logger.info(f"OpenAI tool select raw: {repr(raw)}")
        if not raw or not raw.strip():
            raise HTTPException(status_code=500, detail="LLM response was empty. (Check OpenAI API or prompt!)")
        try:
            tool_invocation = json.loads(raw)
        except Exception as e:
            logger.error(f"Failed to parse LLM output: {repr(raw)}")
            raise HTTPException(status_code=500, detail=f"Tool selection error: {e}. Raw output: {repr(raw)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tool selection error: {e}")

    if tool_invocation.get("tool") != "categorize_expense":
        raise HTTPException(status_code=400, detail=f"GPT did not choose categorize_expense. Got: {tool_invocation}")

    # 3) Now call the tool registry, passing allowed_categories
    inputs = {
        "client_id": client_id,
        "invoice_number": invoice_number,
        "supplier": supplier,
        "line_items": line_items,
        "allowed_categories": allowed_categories
    }
    try:
        tool_result = tool_registry.call("categorize_expense", inputs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"categorize_expense tool error: {e}")

    # 4) Log, step, return (unchanged)
    raw_tool_output = json.dumps(tool_result)
    log_message(db, client_id, "assistant", raw_tool_output)
    auto_summarize_if_needed(db, client_id)
    try:
        ctx = get_or_create_context(db, client_id)
        if ctx.current_step == "invoice_parsed":
            update_context_step(db, client_id, "invoice_categorized")
            update_last_message(db, client_id, f"Categorized invoice {invoice_number}")
    except Exception:
        pass

    return {"categories": tool_result.get("categories", [])}
