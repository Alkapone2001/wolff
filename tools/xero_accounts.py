import threading
import requests
import re
from .xero_utils import _get_headers, XeroToolError

_category_account_map = {}
_code_set = set()
_account_map_lock = threading.Lock()

def normalize(s):
    """Lowercase, strip spaces and non-alphanumerics."""
    return re.sub(r'\W+', '', s or '').lower()

def tokenize(s):
    """Returns a set of lowercase words."""
    return set(re.findall(r'\w+', s.lower()))

def get_all_accounts():
    headers = _get_headers()
    resp = requests.get("https://api.xero.com/api.xro/2.0/Accounts", headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("Accounts", [])

def best_match_account(category, account_map):
    cat_tokens = tokenize(category)
    best_score = 0
    best_code = None
    for name, code in account_map.items():
        acc_tokens = tokenize(name)
        score = len(cat_tokens & acc_tokens)
        if score > best_score:
            best_score = score
            best_code = code
    return best_code

def ensure_account_for_category(category: str) -> str:
    """
    Returns a valid Xero EXPENSE account code for the category.
    If not present, tries to create. If creation fails, finds the most similar existing EXPENSE account by words.
    """
    with _account_map_lock:
        orig_category = category
        if not _category_account_map:
            for acc in get_all_accounts():
                if acc.get("Type") == "EXPENSE":
                    _category_account_map[acc["Name"]] = acc["Code"]
                    _code_set.add(acc["Code"])
        cat_norm = normalize(category)
        # 1. Exact match first
        for name in _category_account_map:
            if normalize(name) == cat_norm:
                return _category_account_map[name]

        # 2. Try to create new account
        code = 4000
        while str(code) in _code_set:
            code += 1
        _code_set.add(str(code))

        payload = {
            "Accounts": [{
                "Name": category,
                "Type": "EXPENSE",
                "Code": str(code)
            }]
        }
        headers = _get_headers()
        try:
            resp = requests.post("https://api.xero.com/api.xro/2.0/Accounts", headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            new_acc = resp.json()["Accounts"][0]
            _category_account_map[new_acc["Name"]] = new_acc["Code"]
            return new_acc["Code"]
        except requests.HTTPError as e:
            print(f"❌ Xero Accounts API error with '{category}':", getattr(e.response, "text", str(e)))
            # 3. Fallback: Use best-matching existing expense account
            match_code = best_match_account(category, _category_account_map)
            if match_code:
                print(f"⚠️  Using most similar existing account for '{category}': {match_code}")
                return match_code
            # As last resort, use any existing EXPENSE account
            if _category_account_map:
                print("⚠️  Using first available EXPENSE account as last resort.")
                return next(iter(_category_account_map.values()))
            raise XeroToolError(
                f"Failed to create or fallback for account category '{orig_category}': {getattr(e, 'response', e)}"
            )
