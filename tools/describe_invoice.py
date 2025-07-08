# tools/describe_invoice.py

from openai import OpenAI

client = OpenAI()

def describe_invoice_tool(inputs: dict) -> dict:
    """
    Generates a short, human-friendly summary of an invoice focused on line item contents.
    Falls back gracefully if no descriptions are provided.
    """
    supplier = inputs.get("supplier", "")
    invoice_num = inputs.get("invoice_number", "")
    total = inputs.get("total", "")
    date = inputs.get("date", "")
    items = inputs.get("line_items", [])

    # Check for described line items
    described_items = [
        f"- {item.get('quantity', 1)} x {item.get('description', '').strip()} for {item.get('amount', '')}"
        for item in items if item.get('description', '').strip()
    ]

    if described_items:
        formatted_items = "\n".join(described_items)
        prompt = (
            f"You are an AI accountant. Write a concise one-sentence summary of what this invoice is about, focusing on the line items.\n\n"
            f"Line Items:\n{formatted_items}\n\n"
            f"Do not include supplier, date, or invoice number. Only describe what was purchased or delivered."
        )
    else:
        prompt = (
            f"You are an AI accountant. Write a concise one-sentence description of this invoice's likely content based on the supplier and context.\n\n"
            f"Supplier: {supplier}\n"
            f"Total: {total}\n"
            f"Date: {date}\n"
            f"Invoice Number: {invoice_num}\n\n"
            f"No specific line item descriptions were provided. Guess what this invoice could be about in a natural way."
        )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=60,
    )

    summary = response.choices[0].message.content.strip()
    return {"description": summary}
