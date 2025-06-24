# tools/xero_utils.py

import os
import json
import logging

# These files should match what your OAuth logic writes!
TOKEN_FILE  = "/app/xero_token.json"
TENANT_FILE = "/app/xero_tenant_id.txt"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class XeroToolError(Exception):
    def __init__(self, message, xero_response=None):
        self.xero_response = xero_response
        super().__init__(message)

def _load_tokens():
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise XeroToolError("Authentication required - no token found")
    except json.JSONDecodeError:
        raise XeroToolError("Corrupted token file - please reauthenticate")

def _get_headers() -> dict:
    tokens = _load_tokens()
    with open(TENANT_FILE, "r") as f:
        tenant_id = f.read().strip()
    return {
        "Authorization":   f"Bearer {tokens['access_token']}",
        "Xero-tenant-id":  tenant_id,
        "Content-Type":    "application/json",
        "Accept":          "application/json"
    }
