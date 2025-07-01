# tools/parse_invoice.py

import base64
import json
import re
import anyio
from pdf2image import convert_from_bytes
import pytesseract
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()


def parse_invoice_tool(inputs: dict) -> dict:
    """
    OCRs a PDF and extracts invoice fields using GPT.
    inputs: { "file_bytes": "<base64-encoded PDF>" }
    Returns:
      supplier, date, invoice_number, total, vat_rate,
      taxable_base, discount_total, vat_amount, net_subtotal
    """
    # 1️⃣ OCR PDF to text
    raw_bytes = base64.b64decode(inputs["file_bytes"])
    pages = convert_from_bytes(raw_bytes, dpi=300)
    ocr_text = "\n".join(pytesseract.image_to_string(p) for p in pages)

    # 2️⃣ Prompt OpenAI for structured fields
    prompt = f"""
You are an accounting assistant. Extract exactly this JSON:
  • supplier
  • date
  • invoice_number
  • total
  • vat_rate

Invoice Text:
""" + ocr_text

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    raw = resp.choices[0].message.content

    def clean(text: str) -> dict:
        t = text.strip()
        t = re.sub(r"^```(?:json)?", "", t)
        t = re.sub(r"```$", "", t)
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            return {}
    data = clean(raw)

    def parse_num(val):
        s = str(val or "").replace("'", "").replace(" ", "").replace(",", ".")
        s = re.sub(r"[^\d\.-]", "", s)
        try:
            return float(s)
        except ValueError:
            return 0.0

    total    = parse_num(data.get("total"))
    vat_rate = parse_num(data.get("vat_rate"))

    # 5️⃣ Try to extract "MWST X% von Y" taxable base
    m_base = re.search(
        r"(?:MWST|VAT)[^\d\n\r]*(\d{1,3}(?:[.,]\d+)?)\s*%\s*von\s*([0-9'.,\s]+)",
        ocr_text,
        re.IGNORECASE
    )
    taxable_base = round(parse_num(m_base.group(2)), 2) if m_base else 0.0

    # 6️⃣ Extract any "0% von Z" discount line
    m_disc = re.search(
        r"(?:MWST|VAT)[^\d\n\r]*0(?:[.,]0)?%\s*von\s*([-0-9'.,\s]+)",
        ocr_text,
        re.IGNORECASE
    )
    discount_total = round(parse_num(m_disc.group(1)), 2) if m_disc else 0.0

    # 7️⃣ Compute VAT amount from taxable_base × rate
    if taxable_base and vat_rate:
        vat_amount = round(taxable_base * vat_rate / 100, 2)
    else:
        net_guess  = total / (1 + vat_rate / 100) if vat_rate else total
        vat_amount = round(total - net_guess, 2)

    # 8️⃣ Net subtotal (total - vat)
    net_subtotal = round(total - vat_amount, 2)

    # 9️⃣ Round fields
    total          = round(total,          2)
    vat_rate       = round(vat_rate,       2)
    taxable_base   = round(taxable_base,   2)
    discount_total = round(discount_total, 2)

    # 🔟 Return structured result
    return {
        "supplier":      data.get("supplier", ""),
        "date":          data.get("date", ""),
        "invoice_number":data.get("invoice_number", ""),
        "total":         total,
        "vat_rate":      vat_rate,
        "taxable_base":  taxable_base,
        "discount_total":discount_total,
        "vat_amount":    vat_amount,
        "net_subtotal":  net_subtotal
    }

async def parse_invoice_tool_async(inputs: dict) -> dict:
    """
    Async wrapper: offloads OCR+parsing to a worker thread.
    """
    return await anyio.to_thread.run_sync(parse_invoice_tool, inputs)
