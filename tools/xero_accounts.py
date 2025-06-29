import asyncio
import httpx
import re
from rapidfuzz import fuzz
from .xero_utils import _get_headers, XeroToolError

# In-memory cache (per process)
_category_account_map = {}
_code_set = set()
_cache_lock = asyncio.Lock()

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

async def get_all_expense_accounts():
    """
    Fetches all EXPENSE accounts from Xero (name/code).
    """
    accounts = await _fetch_accounts()
    return [
        {"name": acc["Name"], "code": acc["Code"]}
        for acc in accounts
        if acc.get("Type") == "EXPENSE"
    ]

async def ensure_account_for_category_existing_only(category: str) -> str:
    """
    Returns the code for an existing EXPENSE account matching category name (case-insensitive, ignoring punctuation).
    Fails if not found. Does NOT create, fallback, or fuzzy match.
    """
    async with _cache_lock:
        # Populate cache if empty
        if not _category_account_map:
            for acc in await _fetch_accounts():
                if acc.get("Type") == "EXPENSE":
                    _category_account_map[normalize(acc["Name"])] = acc["Code"]
                    _code_set.add(str(acc["Code"]))

        norm = normalize(category)
        if norm in _category_account_map:
            return str(_category_account_map[norm])

        # Not found? Fail, don't create or fuzzy match
        raise XeroToolError(
            f"No existing Xero expense account named '{category}'. "
            f"Allowed: {list(_category_account_map.keys())}"
        )
