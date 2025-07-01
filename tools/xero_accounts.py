import asyncio
import httpx
import re
from rapidfuzz import fuzz
from .xero_utils import _get_headers, XeroToolError

# In-memory cache (per process)
_category_account_map = {}
_code_set = set()
_cache_lock = asyncio.Lock()

GENERAL_EXPENSES_CODE = "400"  # Change if your catch-all is different

def normalize(s: str) -> str:
    """Lowercase and strip all non-word characters."""
    return re.sub(r"\W+", "", (s or "")).lower()

async def _fetch_accounts() -> list:
    """Fetch all accounts from Xero and cache them."""
    headers = _get_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://api.xero.com/api.xro/2.0/Accounts", headers=headers)
        resp.raise_for_status()
        return resp.json().get("Accounts", [])

async def ensure_account_for_category_async(category: str) -> str:
    """
    1. If exact match exists, use it.
    2. Else, create new account in Xero with that name.
    3. If creation fails, fuzzy match to existing account.
    4. Fallback: General Expenses.
    Returns the Xero Account Code as a string.
    """
    async with _cache_lock:
        # Populate cache if empty
        if not _category_account_map:
            for acc in await _fetch_accounts():
                if acc.get("Type") == "EXPENSE":
                    _category_account_map[acc["Name"]] = acc["Code"]
                    _code_set.add(str(acc["Code"]))

        norm = normalize(category)

        # 1. Try exact name match (normalized)
        for name, code in _category_account_map.items():
            if normalize(name) == norm:
                return str(code)

        # 2. Try to create a new EXPENSE account with that name
        code = 4000
        while str(code) in _code_set or str(code) == GENERAL_EXPENSES_CODE:
            code += 1
        payload = {
            "Accounts": [{
                "Name": category,
                "Type": "EXPENSE",
                "Code": str(code)
            }]
        }
        headers = _get_headers()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.xero.com/api.xro/2.0/Accounts",
                    headers=headers,
                    json=payload
                )
                resp.raise_for_status()
                new = resp.json()["Accounts"][0]
                _category_account_map[new["Name"]] = new["Code"]
                _code_set.add(str(new["Code"]))
                return str(new["Code"])
        except Exception as err:
            # Xero may return error, e.g., if code or name exists, or API quota/validation
            pass  # Continue to fallback

        # 3. Fuzzy match: pick best match by similarity (if any)
        if _category_account_map:
            best = max(
                _category_account_map.items(),
                key=lambda kv: fuzz.token_sort_ratio(category, kv[0])
            )
            if fuzz.token_sort_ratio(category, best[0]) > 65:
                return str(best[1])

        # 4. As last resort, use GENERAL_EXPENSES_CODE
        return GENERAL_EXPENSES_CODE

async def ensure_account_for_category_existing_only(category: str) -> str:
    """
    Like ensure_account_for_category_async, but ONLY returns an existing code,
    or falls back to GENERAL_EXPENSES_CODE. Never creates new accounts.
    """
    async with _cache_lock:
        if not _category_account_map:
            for acc in await _fetch_accounts():
                if acc.get("Type") == "EXPENSE":
                    _category_account_map[acc["Name"]] = acc["Code"]
                    _code_set.add(str(acc["Code"]))

        norm = normalize(category)
        for name, code in _category_account_map.items():
            if normalize(name) == norm:
                return str(code)

        # Fuzzy fallback
        if _category_account_map:
            best = max(
                _category_account_map.items(),
                key=lambda kv: fuzz.token_sort_ratio(category, kv[0])
            )
            if fuzz.token_sort_ratio(category, best[0]) > 65:
                return str(best[1])

        return GENERAL_EXPENSES_CODE

async def get_all_expense_accounts() -> list:
    """
    Returns a list of dicts with all expense accounts from Xero.
    Each dict has at least 'name' and 'code'.
    """
    async with _cache_lock:
        # Refresh the cache if empty
        if not _category_account_map:
            for acc in await _fetch_accounts():
                if acc.get("Type") == "EXPENSE":
                    _category_account_map[acc["Name"]] = acc["Code"]
                    _code_set.add(str(acc["Code"]))
        return [
            {"name": name, "code": code}
            for name, code in _category_account_map.items()
        ]
