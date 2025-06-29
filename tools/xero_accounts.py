import asyncio
import httpx
import re
from rapidfuzz import fuzz
from .xero_utils import _get_headers, XeroToolError

# In-memory cache (per process)
_category_account_map = {}
_code_set = set()
_cache_lock = asyncio.Lock()

KNOWN_GOOD_EXPENSE_CODE = "400"  # Make sure in Xero this code is valid for your VAT

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
    Returns an EXPENSE account code for this category.
    Never assigns '400' dynamically, but falls back to it if needed.
    """
    async with _cache_lock:
        # Populate cache if empty
        if not _category_account_map:
            for acc in await _fetch_accounts():
                if acc.get("Type") == "EXPENSE":
                    _category_account_map[acc["Name"]] = acc["Code"]
                    _code_set.add(str(acc["Code"]))

        norm = normalize(category)
        # 1. Try exact name match
        for name, code in _category_account_map.items():
            if normalize(name) == norm:
                return str(code)

        # 2. Dynamically create a new EXPENSE account (skipping '400')
        code = 4000
        while str(code) in _code_set or str(code) == "400":
            code += 1
        payload = {
            "Accounts": [{
                "Name": category,
                "Type": "EXPENSE",
                "Code": str(code)
            }]
        }
        headers = _get_headers()
        async with httpx.AsyncClient(timeout=15) as client:
            try:
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
            except httpx.HTTPStatusError as err:
                # 3. Fuzzy fallback: pick best match by similarity
                if _category_account_map:
                    best = max(
                        _category_account_map.items(),
                        key=lambda kv: fuzz.token_sort_ratio(category, kv[0])
                    )[1]
                    return str(best)
                # 4. As last resort, use KNOWN_GOOD_EXPENSE_CODE (usually "400")
                return KNOWN_GOOD_EXPENSE_CODE
