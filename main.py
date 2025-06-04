from fastapi import FastAPI, File, UploadFile, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from PIL import Image
import pytesseract
import io
import json
import traceback
from dotenv import load_dotenv
from openai import OpenAI
from pdf2image import convert_from_bytes
import re

from database import SessionLocal, engine
import models
import context_manager

# Load env vars
load_dotenv()

# Create DB tables if they don't exist
models.Base.metadata.create_all(bind=engine)

# Initialize OpenAI client
client = OpenAI()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # adjust frontend URL if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def clean_gpt_json_response(text):
    """
    Removes markdown formatting and attempts to parse JSON block from GPT response.
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

    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    contents = await file.read()

    # OCR from PDF
    try:
        pages = convert_from_bytes(contents, dpi=300)
        ocr_text = "\n".join([pytesseract.image_to_string(page) for page in pages])
    except Exception as e:
        print("🔥 OCR EXCEPTION:")
        print(traceback.format_exc())
        raise HTTPException(status_code=400, detail=f"Error processing PDF: {e}")

    # Build context summary for GPT
    try:
        context = context_manager.get_or_create_context(db, client_id)
        context_summary = f"Current step: {context.current_step}. Uploaded invoices: {[inv.invoice_number for inv in context.invoices]}"

        prompt = f"""
You are an AI accounting assistant.

Client context:
{context_summary}

Extract these fields from the invoice text below as JSON with keys:
supplier, date, invoice_number, total, vat.

⚠️ Output only valid JSON — no explanations, no markdown, no extra text.

Invoice Text:
\"\"\"
{ocr_text}
\"\"\"
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        raw_response = response.choices[0].message.content
        print("🧠 GPT RAW OUTPUT:", raw_response)
        data = clean_gpt_json_response(raw_response)

        # Normalize numeric fields
        if isinstance(data, dict):
            for key in ["total", "vat"]:
                if key in data and isinstance(data[key], str):
                    try:
                        data[key] = float(data[key].replace(",", "."))
                    except ValueError:
                        pass  # Ignore if invalid

    except Exception as e:
        print("🔥 GPT EXCEPTION:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {e}")

    # Register invoice
    invoice_number = data.get("invoice_number") if isinstance(data, dict) else None
    if invoice_number:
        context_manager.add_invoice(db, client_id, invoice_number)
        context_manager.update_context_step(db, client_id, "invoice_processed")
        context_manager.update_last_message(db, client_id, f"Processed invoice {invoice_number}")

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
