# routes/categorize.py

from fastapi import APIRouter, Depends, HTTPException, Request, Body
from sqlalchemy.orm import Session
from database import SessionLocal
from schemas.mcp import ModelContext, MessageItem, ToolDefinition
from tool_registry import tool_registry
from context_manager import build_model_context, log_message, auto_summarize_if_needed, get_or_create_context, update_context_step, update_last_message
from datetime import datetime
import json

router = APIRouter(tags=["Categorize Expense"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/categorize-expense/")
def categorize_expense(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    """
    Expects JSON body:
      {
        "client_id": "test_client",
        "invoice_number": "INV-001",
        "supplier": "Lakeside Business Center AG",
        "line_items": [
          { "description": "Office chairs", "amount": 200 },
          { "description": "Stationery", "amount": 50 }
        ]
      }

    Returns:
      {
        "categories": [
          { "description": "Office chairs", "category": "Office Furniture" },
          { "description": "Stationery", "category": "Office Supplies" }
        ]
      }
    """

    client_id = payload.get("client_id")
    invoice_number = payload.get("invoice_number")
    supplier = payload.get("supplier")
    line_items = payload.get("line_items", [])

    if not client_id or not invoice_number or not supplier or not isinstance(line_items, list):
        raise HTTPException(status_code=400, detail="Missing or invalid fields in request body")

    # 1) Build MCP context (memory + recent messages)
    try:
        model_ctx: ModelContext = build_model_context(db, client_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Context build error: {e}")

    # 2) Append a “user” message asking to categorize this invoice
    model_ctx.messages.append(
        MessageItem(
            role="user",
            content=(
                f"Please categorize invoice {invoice_number} from supplier {supplier}. "
                f"Line items: {json.dumps(line_items)}"
            ),
            timestamp=datetime.utcnow()
        )
    )

    # 3) Inject list of all registered tools into the context
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

    # 4) Ask GPT to choose "categorize_expense"
    system_prompt = {
        "role": "system",
        "content": json.dumps(model_ctx.dict(), default=str)
    }
    user_prompt = {
        "role": "user",
        "content": (
            "You have a tool called \"categorize_expense\".  "
            "Simply respond with JSON: {\"tool\": \"categorize_expense\"}  "
            "— do NOT attempt to supply any additional fields yourself."
        )
    }

    from openai import OpenAI
    client = OpenAI()

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[system_prompt, user_prompt],
            temperature=0
        )
        tool_invocation = json.loads(response.choices[0].message.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tool selection error: {e}")

    # 5) Verify the model asked for categorize_expense
    if tool_invocation.get("tool") != "categorize_expense":
        raise HTTPException(status_code=400, detail="GPT did not choose categorize_expense")

    # 6) Now call the tool ourselves with the real inputs
    inputs = {
        "client_id": client_id,
        "invoice_number": invoice_number,
        "supplier": supplier,
        "line_items": line_items
    }
    try:
        tool_result = tool_registry.call("categorize_expense", inputs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"categorize_expense tool error: {e}")

    # 7) Log the tool’s output as an “assistant” message
    raw_tool_output = json.dumps(tool_result)
    log_message(db, client_id, "assistant", raw_tool_output)
    auto_summarize_if_needed(db, client_id)

    # 8) Optionally, advance the client’s step (if you’re tracking a simple state)
    #    For example: after categorization, move from "invoice_parsed" → "invoice_categorized"
    try:
        ctx = get_or_create_context(db, client_id)
        if ctx.current_step == "invoice_parsed":
            update_context_step(db, client_id, "invoice_categorized")
            update_last_message(db, client_id, f"Categorized invoice {invoice_number}")
    except:
        pass  # ignore if no change

    # 9) Return the suggested categories to the caller
    return {"categories": tool_result.get("categories", [])}
