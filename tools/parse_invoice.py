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
    Returns exactly these fields:

      supplier         # vendor name
      date             # invoice date string
      invoice_number   # invoice # string

      total            # gross total including VAT, e.g. 2600.00
      vat_rate         # VAT percentage as printed, e.g. 8.10

      taxable_base     # “von Y” amount on which VAT is applied, e.g. 2717.35
      discount_total   # any 0%-VAT adjustment (negative discounts), e.g. -337.45

      vat_amount       # = round(taxable_base * vat_rate/100, 2) → 220.11
      net_subtotal     # = total − vat_amount, e.g. 2379.89
    """

    # 1) OCR the PDF to plain text
    raw_bytes = base64.b64decode(inputs["file_bytes"])
    pages     = convert_from_bytes(raw_bytes, dpi=300)
    ocr_text  = "\n".join(pytesseract.image_to_string(p) for p in pages)

    # 2) Prompt the LLM for core fields
    prompt = f"""
You are an accounting assistant.  Extract exactly this JSON from the invoice text below:

  • supplier         (vendor name)
  • date             (invoice date)
  • invoice_number   (invoice #)
  • total            (gross total including VAT)
  • vat_rate         (VAT % as printed, without “%”)

Invoice Text:
\"\"\"
{ocr_text}
\"\"\"
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0
    )
    raw = resp.choices[0].message.content

    # 3) Clean and parse JSON
    def clean_json(text: str) -> dict:
        t = text.strip()
        t = re.sub(r"^```(?:json)?", "", t)
        t = re.sub(r"```$", "", t)
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            return {}

    data = clean_json(raw)

    # 4) Number parser (handles apostrophes, spaces, commas)
    def parse_num(val):
        s = str(val or "")
        s = s.replace("'", "").replace(" ", "")
        s = s.replace(",", ".")
        s = re.sub(r"[^\d\.-]", "", s)
        try:
            return float(s)
        except ValueError:
            return 0.0

    total    = parse_num(data.get("total"))
    vat_rate = parse_num(data.get("vat_rate"))

    # 5) Regex–extract “MWST X% von Y” taxable base,
    #    allow spaces/apostrophes in Y
    m_base = re.search(
        r"(?:MWST|VAT)[^\d\n\r]*(\d{1,3}(?:[.,]\d+)?)\s*%\s*von\s*([0-9'.,\s]+)",
        ocr_text,
        re.IGNORECASE
    )
    if m_base:
        vat_rate     = parse_num(m_base.group(1))
        taxable_base = parse_num(m_base.group(2))
    else:
        taxable_base = None

    # 6) Regex–extract any “0% von Z” discount line, allow spaces/apostrophes
    m_disc = re.search(
        r"(?:MWST|VAT)[^\d\n\r]*0(?:[.,]0)?%\s*von\s*([-\d'.,\s]+)",
        ocr_text,
        re.IGNORECASE
    )
    discount_total = parse_num(m_disc.group(1)) if m_disc else 0.0

    # 7) Compute VAT amount from taxable_base × rate
    if taxable_base and vat_rate:
        vat_amount = round(taxable_base * vat_rate / 100, 2)
    else:
        # fallback if no explicit base
        net_guess  = total / (1 + vat_rate/100) if vat_rate else total
        vat_amount = round(total - net_guess, 2)

    # 8) Compute net subtotal
    net_subtotal = round(total - vat_amount, 2)

    # 9) Round all
    total          = round(total,          2)
    vat_rate       = round(vat_rate,       2)
    if taxable_base is not None:
        taxable_base = round(taxable_base, 2)
    discount_total = round(discount_total, 2)

    # 10) Return structured result
    return {
        "supplier":       data.get("supplier",        ""),
        "date":           data.get("date",            ""),
        "invoice_number": data.get("invoice_number",  ""),
        "total":          total,
        "vat_rate":       vat_rate,
        "taxable_base":   taxable_base or 0.0,
        "discount_total": discount_total,
        "vat_amount":     vat_amount,
        "net_subtotal":   net_subtotal
    }
