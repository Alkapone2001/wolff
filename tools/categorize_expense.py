# tools/categorize_expense.py

import json
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def categorize_expense_tool(inputs: dict) -> dict:
    """
    inputs: {
      "client_id": "test_client",
      "invoice_number": "INV-001",
      "supplier": "Lakeside Business Center AG",
      "line_items": [
         { "description": "Office chairs", "amount": 200 },
         { "description": "Stationery", "amount": 50 }
      ]
    }

    Returns: {
      "invoice_number": "INV-001",
      "categories": [
        { "description": "Office chairs", "category": "Office Furniture" },
        { "description": "Stationery", "category": "Office Supplies" }
      ]
    }
    """

    invoice_number = inputs.get("invoice_number", "")
    supplier = inputs.get("supplier", "")
    line_items = inputs.get("line_items", [])

    # 1. Convert line_items to JSON string
    items_json = json.dumps(line_items)

    # 2. Build a prompt asking the LLM to suggest categories
    prompt = f"""
You are an accounting assistant.  Given an invoice with its supplier and line items, 
suggest an account/category for each line.  Return EXACTLY valid JSON in this format:

{{
  "invoice_number": "{invoice_number}",
  "categories": [
    {{ "description": "<desc1>", "category": "<GL account category1>" }},
    {{ "description": "<desc2>", "category": "<GL account category2>" }},
    …
  ]
}}

Invoice Number: {invoice_number}
Supplier: {supplier}
Line Items: {items_json}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You categorize invoice line items."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content

    # 3. Strip markdown fences & parse JSON
    def clean_json(text: str):
        t = text.strip()
        t = re.sub(r"^```(?:json)?", "", t)
        t = re.sub(r"```$", "", t)
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            return {}

    return clean_json(raw)
