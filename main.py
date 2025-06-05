# main.py

from fastapi import FastAPI, File, UploadFile, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pdf2image import convert_from_bytes
import pytesseract
import traceback
import json
import re
from datetime import datetime

from database import SessionLocal, engine
import models
import context_manager
from routes import message_history, summarize
from schemas.mcp import ModelContext
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables (OPENAI_API_KEY etc.)
load_dotenv()

# Create tables if they don’t exist
models.Base.metadata.create_all(bind=engine)

# Initialize OpenAI client (v1+ API)
client = OpenAI()

app = FastAPI()

# Include custom routers
app.include_router(message_history.router)

app.include_router(summarize.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # adjust if needed
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

def clean_gpt_json_response(text: str):
    """
    Strips Markdown fences and attempts to parse JSON.
    Returns a dict or an error dict.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text)
    text = re.sub(r"```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return {"error": "Failed to parse extracted JSON", "raw_response": text}
        return {"error": "Failed to parse GPT output", "raw_response": text}

@app.post("/process-invoice/")
async def process_invoice(
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    client_id = request.headers.get("X-Client-ID", "default_client")

    # 1. Validate that the upload is a PDF
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    contents = await file.read()

    # 2. OCR the PDF into plain text
    try:
        pages = convert_from_bytes(contents, dpi=300)
        ocr_text = "\n".join([pytesseract.image_to_string(page) for page in pages])
    except Exception as e:
        print("🔥 OCR EXCEPTION:\n", traceback.format_exc())
        raise HTTPException(status_code=400, detail=f"Error processing PDF: {e}")

    # 3. Build MCP context (memory + recent messages + client state)
    try:
        model_ctx: ModelContext = context_manager.build_model_context(db, client_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Context build error: {e}")

    # 4. Append the new user message (invoice OCR text) to the context
    model_ctx.messages.append(
        {
            "role": "user",
            "content": f"Here is the invoice OCR text:\n'''{ocr_text}'''",
            "timestamp": datetime.utcnow()
        }
    )

    # 5. Serialize the entire ModelContext as JSON in a single "system" message
    payload = {
        "model": "gpt-4o-mini",  # or whichever GPT model you’re using
        "messages": [
            {"role": "system", "content": json.dumps(model_ctx.dict(), default=str)}
        ],
        "temperature": 0,
    }

    # 6. Call the LLM
    try:
        response = client.chat.completions.create(**payload)
        raw_response = response.choices[0].message.content
        data = clean_gpt_json_response(raw_response)
    except Exception as e:
        print("🔥 GPT EXCEPTION:\n", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {e}")

    # 7. Log the user’s final OCR message and the assistant’s reply
    context_manager.log_message(db, client_id, "user", ocr_text)
    context_manager.log_message(db, client_id, "assistant", raw_response)

    # 8. If extraction succeeded (has invoice_number), store it
    invoice_number = data.get("invoice_number") if isinstance(data, dict) else None
    if invoice_number:
        invoice = context_manager.add_invoice(db, client_id, invoice_number)
        invoice.ocr_text = ocr_text
        invoice.prompt_used = json.dumps(model_ctx.dict(), default=str)
        invoice.llm_response_raw = raw_response
        db.commit()

        context_manager.update_context_step(db, client_id, "invoice_processed")
        context_manager.update_last_message(db, client_id, f"Processed invoice {invoice_number}")

    # 9. Fetch updated ClientContext to return to the frontend
    context = context_manager.get_context(db, client_id)

    return {
        "extracted_text": ocr_text,
        "structured_data": data,
        "context": {
            "client_id": context.client_id,
            "current_step": context.current_step,
            "last_message": context.last_message,
            "uploaded_invoices": [
                {
                    "invoice_number": inv.invoice_number,
                    "status": inv.status,
                    "date_uploaded": inv.date_uploaded.isoformat(),
                }
                for inv in context.invoices
            ],
        },
    }
