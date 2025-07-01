# tools/categorize_expense.py

import json
from rapidfuzz import process, fuzz

def categorize_expense_tool(inputs: dict) -> dict:
    """
    inputs:
      - allowed_accounts: List[{"name": str, "code": str}]
      - line_items: List[{"description": str, "amount": number}]
    Returns:
      { "categories": [
          {
            "description": ...,
            "category": <matched account name>,
            "account_name": <matched account name>,
            "account_code": <matched account code>
          },
          ...
       ] }
    """
    allowed_accounts = inputs.get("allowed_accounts", [])
    items = inputs.get("line_items", [])

    # Prepare list of just the names for matching
    allowed_names = [acc["name"] for acc in allowed_accounts]

    results = []
    for item in items:
        desc = item.get("description", "") or ""
        # Fuzzy match description → one of the allowed account names
        match_name, score, idx = process.extractOne(
            desc,
            allowed_names,
            scorer=fuzz.partial_ratio
        )
        if score >= 60:
            account = allowed_accounts[idx]
        else:
            # fallback to General Expenses
            account = next(
                (a for a in allowed_accounts if a["name"].lower().startswith("general")),
                allowed_accounts[0] if allowed_accounts else {"name": "General Expenses", "code": "400"}
            )

        results.append({
            "description": desc,
            "category": account["name"],
            "account_name": account["name"],
            "account_code": account["code"]
        })

    return {"categories": results}


async def categorize_expense_tool_async(inputs: dict) -> dict:
    import anyio
    return await anyio.to_thread.run_sync(categorize_expense_tool, inputs)
