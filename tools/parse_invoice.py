# tools/parse_invoice.py

import base64
import json
import re
from pdf2image import convert_from_bytes
import pytesseract
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def parse_invoice_tool(inputs: dict) -> dict:
    """
    inputs: { "file_bytes": "<base64-encoded PDF>" }
    Returns: { supplier, date, invoice_number, total, vat }
    """

    # 1. Decode the Base64 PDF into raw bytes
    raw_bytes = base64.b64decode(inputs["file_bytes"])

    # 2. Convert PDF pages to images
    pages = convert_from_bytes(raw_bytes, dpi=300)
    ocr_text = "\n".join([pytesseract.image_to_string(page) for page in pages])

    # 3. Build a prompt asking the LLM to extract fields as JSON
    prompt = f"""
You are an accounting assistant.  Extract these fields from the invoice text below as JSON:
supplier, date, invoice_number, total, vat.

Invoice Text:
\"\"\"
{ocr_text}
\"\"\"
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    raw = response.choices[0].message.content

    # 4. Clean up the LLM output into valid JSON
    def clean_json(text: str):
        t = text.strip()
        t = re.sub(r"^```(?:json)?", "", t)
        t = re.sub(r"```$", "", t)
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            return {}

    return clean_json(raw)
