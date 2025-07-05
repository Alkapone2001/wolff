# routes/xero_auth.py
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, PlainTextResponse
import os, json, requests, asyncio

router = APIRouter()

CLIENT_ID     = os.getenv("XERO_CLIENT_ID")
CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("XERO_REDIRECT_URI")

# MAKE SURE THIS INCLUDES ALL SCOPES YOU NEED!
XERO_SCOPES = [
    "openid", "profile", "email", "offline_access",
    "accounting.transactions", "accounting.settings",
    "accounting.attachments"   # <-- THIS IS THE ONE THAT ENABLES ATTACHMENT UPLOADS!
]

@router.get("/xero/connect")
def connect():
    scopes_str = "%20".join(XERO_SCOPES)
    url = (
        "https://login.xero.com/identity/connect/authorize"
        f"?response_type=code&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={scopes_str}"
    )
    return RedirectResponse(url)

@router.get("/xero/callback")
async def callback(request: Request):
    code = request.query_params["code"]
    # Exchange code for tokens (sync HTTP ok here)
    resp = requests.post(
        "https://identity.xero.com/connect/token",
        data={
          "grant_type":"authorization_code",
          "code":code,
          "redirect_uri":REDIRECT_URI,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
    )
    tokens = resp.json()
    # Save tokens (async, in thread pool)
    def _write_tokens(tokens):
        with open("/app/xero_token.json", "w") as f:
            json.dump(tokens, f)
    await asyncio.to_thread(_write_tokens, tokens)

    # Grab the first tenant (your org)
    tenant_id = requests.get(
      "https://api.xero.com/connections",
      headers={"Authorization":f"Bearer {tokens['access_token']}"}
    ).json()[0]["tenantId"]
    await asyncio.to_thread(lambda: open("/app/xero_tenant_id.txt", "w").write(tenant_id))
    return PlainTextResponse("✔️ Xero tokens saved.")
