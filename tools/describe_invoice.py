# tools/describe_invoice.py

from openai import OpenAI

client = OpenAI()

def describe_invoice_tool(inputs: dict) -> dict:
    """
    Given parsed invoice fields, return a short, human-readable description.
    """
    supplier = inputs.get("supplier", "")
    items = inputs.get("line_items", [])
    invoice_num = inputs.get("invoice_number", "")
    total = inputs.get("total", "")
    date = inputs.get("date", "")
    prompt = (
        f"You are an assistant for accounting. Write a 1-sentence human-friendly summary of an invoice "
        f"from {supplier} dated {date}, invoice number {invoice_num}, for total {total}. "
        f"Line items: {items} "
        f"Do NOT start with 'Invoice for...'. Instead, describe the contents clearly but concisely."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=40,
    )
    summary = response.choices[0].message.content.strip()
    return {"description": summary}
