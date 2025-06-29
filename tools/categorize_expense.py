# tools/categorize_expense.py

import json
import re
import anyio
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def categorize_expense_tool(inputs: dict) -> dict:
    """
    Synchronously calls OpenAI to categorize line items.
    """
    invoice = inputs.get("invoice_number", "")
    supplier = inputs.get("supplier", "")
    items = inputs.get("line_items", [])
    prompt = f"""
You are an accounting assistant. Given the supplier and line items, categorize each.

Return exactly JSON:
{{
  "invoice_number": "{invoice}",
  "categories": [
    {{ "description": "<desc>", "category": "<category name>" }},
    ...
  ]
}}

Supplier: {supplier}
Line Items: {json.dumps(items)}
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Categorize expenses."},
            {"role": "user", "content": prompt}
        ],
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
    return clean(raw)

async def categorize_expense_tool_async(inputs: dict) -> dict:
    """
    Async wrapper: runs categorize_expense_tool in a threadpool for event-loop safety.
    """
    return await anyio.to_thread.run_sync(categorize_expense_tool, inputs)
