# main.py

from fastapi import FastAPI, File, UploadFile, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
import context_manager  # <-- so you can use context_manager.log_message, etc
from routes import message_history, summarize, categorize, book, batch_book
from schemas.mcp import ModelContext, MessageItem, Memory
from schemas.tools import ToolDefinition
from tool_registry import tool_registry
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
import json
import base64
from routes.xero_auth import router as xero_auth_router
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables (OPENAI_API_KEY etc.)
load_dotenv()

# Create tables if they don’t exist
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Include custom routers
app.include_router(message_history.router)
app.include_router(xero_auth_router)
app.include_router(book.router)
app.include_router(batch_book.router)
app.include_router(summarize.router)
app.include_router(categorize.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/process-invoice/")
async def process_invoice(
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    client_id = request.headers.get("X-Client-ID", "default_client")

    raw_bytes = await file.read()
    file_b64 = base64.b64encode(raw_bytes).decode()  # Always valid padding

    # 1. Build the MCP context (memory + messages)
    try:
        model_ctx: ModelContext = context_manager.build_model_context(db, client_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Context build error: {e}")

    model_ctx.messages.append(
        MessageItem(
            role="user",
            content="Please parse my invoice PDF with the parse_invoice tool.",
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

    # 2. Tool selection by LLM: robust JSON parsing!
    client = OpenAI()

    system_prompt = {
        "role": "system",
        "content": json.dumps(model_ctx.dict(), default=str)
    }
    user_prompt = {
        "role": "user",
        "content": (
            "Respond with ONLY JSON: {\"tool\": \"parse_invoice\"}. "
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

    if tool_invocation.get("tool") != "parse_invoice":
        raise HTTPException(status_code=400, detail=f"GPT did not choose parse_invoice. Got: {tool_invocation}")

    # 3. Actually call your tool
    try:
        tool_result = tool_registry.call("parse_invoice", {"file_bytes": file_b64})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"parse_invoice tool error: {e}")

    # 4. Log, summarize, step, etc.
    raw_tool_output = json.dumps(tool_result)
    context_manager.log_message(db, client_id, "assistant", raw_tool_output)
    context_manager.auto_summarize_if_needed(db, client_id)

    invoice_number = tool_result.get("invoice_number")
    if invoice_number:
        inv = context_manager.add_invoice(db, client_id, invoice_number)
        inv.ocr_text = ""  # OCR is in the tool already
        inv.prompt_used = json.dumps(model_ctx.dict(), default=str)
        inv.llm_response_raw = raw_tool_output
        db.commit()

        context_manager.update_context_step(db, client_id, "invoice_processed")
        context_manager.update_last_message(db, client_id, f"Parsed invoice {invoice_number}")

    return {"structured_data": tool_result}
