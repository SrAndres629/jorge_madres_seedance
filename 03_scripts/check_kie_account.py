#!/usr/bin/env python3
"""
check_kie_account.py

Verifies API key validity and credit balance WITHOUT calling createTask.
Does NOT spend credits. Does NOT create tasks. Does NOT generate video.

Reads KIE_CREDIT_URL from .env, makes a GET request with Bearer auth,
and produces kie_account_health_report.json.

Also scans previous kie_responses for daily limit blocks.
"""

import json
import os
import sys
import http.client
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(os.environ.get("PROJECT_ROOT", os.getcwd()))
VALIDATION_DIR = BASE / "04_logs/validation"
RESPONSES_DIR = BASE / "04_logs/kie_responses"
VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

# ─── Load .env ───────────────────────────────────────────────────────────────
try:
    import dotenv

    dotenv.load_dotenv(BASE / ".env")
except ImportError:
    pass  # Try OS env vars directly

API_KEY = os.environ.get("KIE_API_KEY", "")
CREDIT_URL = os.environ.get("KIE_CREDIT_URL", "https://api.kie.ai/api/v1/chat/credit")
MIN_CREDITS = int(os.environ.get("MIN_REQUIRED_CREDITS", "800"))

if not API_KEY:
    print("FATAL: KIE_API_KEY not set in .env or environment")
    sys.exit(1)

# ─── Scan previous responses for daily limit blocks ──────────────────────────
daily_limit_known = False
daily_limit_msg = ""

if RESPONSES_DIR.exists():
    for f in sorted(RESPONSES_DIR.glob("*_create_response.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            body = data.get("body", {})
            msg = body.get("msg", "")
            if (
                "daily limit" in msg.lower()
                or "exceeded the daily limit" in msg.lower()
            ):
                daily_limit_known = True
                daily_limit_msg = msg
                break
        except Exception:
            pass


# ─── Call credit endpoint ───────────────────────────────────────────────────
def http_get(url_str, headers=None, timeout=30):
    if headers is None:
        headers = {}
    parsed = urllib.parse.urlparse(url_str)
    conn = http.client.HTTPSConnection(
        parsed.hostname, parsed.port or 443, timeout=timeout
    )
    path_q = parsed.path + ("?" + parsed.query if parsed.query else "")
    conn.request("GET", path_q, headers=headers)
    res = conn.getresponse()
    data = res.read().decode("utf-8")
    conn.close()
    try:
        return res.status, json.loads(data)
    except json.JSONDecodeError:
        return res.status, {"raw": data}


print(f"Checking: {CREDIT_URL}")

http_status, body = http_get(CREDIT_URL, {"Authorization": f"Bearer {API_KEY}"})

api_code = body.get("code", http_status)
api_msg = body.get("msg", "")

# Detect daily limit in current response
if not daily_limit_known and (
    "daily limit" in api_msg.lower() or "exceeded the daily limit" in api_msg.lower()
):
    daily_limit_known = True
    daily_limit_msg = api_msg

api_key_valid = http_status == 200 and api_code == 200

if api_key_valid:
    credit_data = body.get("data", 0)
    if isinstance(credit_data, dict):
        credit_balance = credit_data.get("balance", credit_data.get("credits", 0))
    else:
        credit_balance = int(credit_data) if credit_data else 0
else:
    credit_balance = 0

has_enough = credit_balance >= MIN_CREDITS
safe = api_key_valid and has_enough and not daily_limit_known

report = {
    "checkedAt": datetime.now(timezone.utc).isoformat(),
    "creditUrl": CREDIT_URL,
    "httpStatus": http_status,
    "code": api_code,
    "msg": api_msg,
    "apiKeyValid": api_key_valid,
    "creditBalance": credit_balance,
    "minRequiredCredits": MIN_CREDITS,
    "hasEnoughCredits": has_enough,
    "dailyLimitKnownBlocked": daily_limit_known,
    "dailyLimitMessageFromPreviousRun": daily_limit_msg,
    "safeToGenerate": safe,
    "noCreateTaskCalled": True,
    "creditsSpent": 0,
}

report_path = VALIDATION_DIR / "kie_account_health_report.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"\nAccount Health Check: {'PASSED' if safe else 'FAILED'}")
print(f"  API Key valid: {api_key_valid}")
print(f"  Credit balance: {credit_balance}")
print(f"  Min required: {MIN_CREDITS}")
print(f"  Enough credits: {has_enough}")
print(f"  Daily limit blocked: {daily_limit_known}")
print(f"  Safe to generate: {safe}")
if daily_limit_msg:
    print(f"  Daily limit message: {daily_limit_msg}")

print(f"\nReport: {report_path}")

if not safe:
    sys.exit(1)
