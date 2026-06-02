#!/usr/bin/env python3
"""
generate_seedance_final.py

Safe Kie.ai / Seedance 2.0 generation script.
Defaults to dry-run mode. Requires --execute + confirmation phrase for real calls.

IMPORTANT:
- Run without --execute first to generate preflight report.
- Only proceed to --execute after preflight passes ALL checks.
"""

import json
import os
import sys
import time
import http.client
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

# ─── Setup ───────────────────────────────────────────────────────────────────
BASE = Path(os.environ.get("PROJECT_ROOT", os.getcwd()))
CONFIG_PATH = BASE / "00_config/campaign_config.json"
PREFLIGHT_PATH = BASE / "04_logs/validation/preflight_report.json"
ALIGNMENT_PATH = BASE / "04_logs/validation/prompt_reference_alignment_report.json"
AUDIT_PATH = BASE / "04_logs/validation/final_prompt_content_audit.json"
PAYLOADS_DIR = BASE / "04_logs/dry_run_payloads"
REQUESTS_DIR = BASE / "04_logs/kie_requests"
RESPONSES_DIR = BASE / "04_logs/kie_responses"
STATUS_DIR = BASE / "04_logs/kie_status"
RAW_OUTPUT = BASE / "05_outputs/raw"
VALIDATION_DIR = BASE / "04_logs/validation"
TASKS_FILE = BASE / "04_logs/kie_tasks.json"

REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
STATUS_DIR.mkdir(parents=True, exist_ok=True)
RAW_OUTPUT.mkdir(parents=True, exist_ok=True)
VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

# ─── CLI args ────────────────────────────────────────────────────────────────
DRY_RUN = "--execute" not in sys.argv
CONFIRMATION_PHRASE = "GENERAR_7_CLIPS_JORGE"


# ─── Load config ─────────────────────────────────────────────────────────────
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_url(url, timeout=10):
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path_url = parsed.path
        if parsed.query:
            path_url += "?" + parsed.query
        conn = (
            http.client.HTTPSConnection
            if parsed.scheme == "https"
            else http.client.HTTPConnection
        )(host, port, timeout=timeout)
        conn.request("HEAD", path_url)
        res = conn.getresponse()
        status = res.status
        conn.close()
        return {"url": url, "statusCode": status, "ok": status == 200}
    except Exception as e:
        return {"url": url, "statusCode": 0, "ok": False, "error": str(e)}


# ─── STEP 1: Load and validate all reports ────────────────────────────────────
preflight_errors = []

try:
    config = load_json(CONFIG_PATH)
except Exception as e:
    print(f"FATAL: Cannot load campaign_config.json: {e}")
    sys.exit(1)

try:
    preflight = load_json(PREFLIGHT_PATH)
except Exception as e:
    print(
        f"FATAL: Cannot load preflight_report.json: {e}. Run prepare_seedance_payloads.py first."
    )
    sys.exit(1)

try:
    alignment = load_json(ALIGNMENT_PATH)
except Exception as e:
    print(
        f"FATAL: Cannot load alignment report: {e}. Run validate_prompt_reference_alignment.py first."
    )
    sys.exit(1)

try:
    audit = load_json(AUDIT_PATH)
except Exception as e:
    print(
        f"FATAL: Cannot load audit report: {e}. Run final_prompt_content_audit.py first."
    )
    sys.exit(1)

if not preflight.get("overallOk"):
    preflight_errors.append("preflight_report.json overallOk is false")
if not alignment.get("overallOk"):
    preflight_errors.append("prompt_reference_alignment_report.json overallOk is false")
if not audit.get("summary", {}).get("overallOk"):
    preflight_errors.append("final_prompt_content_audit.json overallOk is false")

# Load payloads
payload_files = sorted(PAYLOADS_DIR.glob("payload_*.json"))
if len(payload_files) != 7:
    preflight_errors.append(f"Expected 7 payloads, found {len(payload_files)}")

payloads = []
for pf in payload_files:
    p = load_json(pf)
    inp = p.get("input", {})
    payloads.append({"file": pf, "data": p})

# Validate payloads deeply
for entry in payloads:
    pf = entry["file"]
    inp = entry["data"]["input"]

    sid = pf.stem.replace("payload_", "")
    prompt = inp.get("prompt", "")

    if not prompt.strip():
        preflight_errors.append(f"{pf.name}: prompt is empty")
    if inp.get("generate_audio") is not True:
        preflight_errors.append(f"{pf.name}: generate_audio must be true")
    if inp.get("aspect_ratio") != "9:16":
        preflight_errors.append(f"{pf.name}: aspect_ratio must be 9:16")
    if inp.get("resolution") != "720p":
        preflight_errors.append(f"{pf.name}: resolution must be 720p")

    expected_dur = 5 if sid.startswith(("06", "07")) else 4
    if inp.get("duration") != expected_dur:
        preflight_errors.append(
            f"{pf.name}: duration must be {expected_dur}, got {inp.get('duration')}"
        )

    for forbidden in ["reference_audio_urls", "first_frame_url", "last_frame_url"]:
        if forbidden in inp:
            preflight_errors.append(f"{pf.name}: {forbidden} must not be present")

# HTTP 200 check
url_failures = []
for entry in payloads:
    for url in entry["data"]["input"].get("reference_image_urls", []):
        result = check_url(url)
        if not result["ok"]:
            url_failures.append(result)
            preflight_errors.append(f"URL not 200: {url}")

# ─── STEP 2: Write generation preflight report ────────────────────────────────
gen_preflight = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "dryRun": DRY_RUN,
    "reportsValid": len(preflight_errors) == 0,
    "validationErrors": preflight_errors,
    "payloadsFound": len(payloads),
    "urlChecks": {
        "total": len(url_failures)
        + sum(
            1
            for e in payloads
            for _ in e["data"]["input"].get("reference_image_urls", [])
        ),
        "failed": len(url_failures),
        "failures": url_failures[:5],
    },
    "ready": len(preflight_errors) == 0,
}

gen_preflight_path = VALIDATION_DIR / "final_generation_preflight_report.json"
with open(gen_preflight_path, "w", encoding="utf-8") as f:
    json.dump(gen_preflight, f, indent=2, ensure_ascii=False)

print("=" * 60)
print("GENERATION PREFLIGHT")
print("=" * 60)
print(f"Mode: {'DRY-RUN' if DRY_RUN else 'EXECUTE (real)'}")
print(f"Reports valid: {gen_preflight['reportsValid']}")
print(f"Payloads: {gen_preflight['payloadsFound']}")
print(f"Validation errors: {len(preflight_errors)}")
print(f"URLs failed: {gen_preflight['urlChecks']['failed']}")
print(f"Ready for generation: {gen_preflight['ready']}")

if preflight_errors:
    for e in preflight_errors:
        print(f"  ERROR: {e}")
    print("\nPreflight FAILED. Fix errors before retrying.")
    sys.exit(1)

print(f"\nReport: {gen_preflight_path}")

# ─── STEP 3: Dry-run exit ────────────────────────────────────────────────────
if DRY_RUN:
    print("\nDRY-RUN mode. No Kie API calls made.")
    print("To execute real generation, run with --execute flag.")
    sys.exit(0)

# ─── STEP 4: Execute real generation ─────────────────────────────────────────
print("\n" + "=" * 60)
print("REAL EXECUTION MODE")
print("=" * 60)
print(f"This will create {len(payloads)} tasks on Kie.ai / Seedance 2.0")
print("Credits WILL be consumed.")
print(f"\nType the exact confirmation phrase to proceed:")
confirmation = input("> ").strip()

if confirmation != CONFIRMATION_PHRASE:
    print(f"\nConfirmation mismatch. Expected: {CONFIRMATION_PHRASE}")
    print("Aborting. No Kie API calls made.")
    sys.exit(1)

# Load .env
try:
    import dotenv

    dotenv.load_dotenv(BASE / ".env")
except ImportError:
    print("FATAL: python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

API_KEY = os.environ.get("KIE_API_KEY", "")
CREATE_TASK_URL = os.environ.get(
    "KIE_CREATE_TASK_URL", "https://api.kie.ai/api/v1/jobs/createTask"
)
RECORD_INFO_URL = os.environ.get(
    "KIE_RECORD_INFO_URL", "https://api.kie.ai/api/v1/jobs/recordInfo"
)

if not API_KEY:
    print("FATAL: KIE_API_KEY not set in .env")
    sys.exit(1)

POLL_INTERVAL = config.get("pollIntervalSeconds", 30)
MAX_POLL_ROUNDS = config.get("maxPollRounds", 40)
BASE_URL = config.get("publicAssetBaseUrl", "")

print(f"\nAPI Key: {'*' * len(API_KEY[:8]) if len(API_KEY) > 8 else '**NOT SET**'}")
print(f"Create URL: {CREATE_TASK_URL}")
print(f"Poll interval: {POLL_INTERVAL}s, Max rounds: {MAX_POLL_ROUNDS}")
print(f"\nProceeding with {len(payloads)} tasks...\n")


def http_post(url_str, payload_dict, headers=None):
    if headers is None:
        headers = {}
    parsed = urllib.parse.urlparse(url_str)
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=60)
    body = json.dumps(payload_dict).encode("utf-8")
    headers["Content-Type"] = headers.get("Content-Type", "application/json")
    conn.request(
        "POST",
        parsed.path + ("?" + parsed.query if parsed.query else ""),
        body=body,
        headers=headers,
    )
    res = conn.getresponse()
    data = res.read().decode("utf-8")
    conn.close()
    try:
        return res.status, json.loads(data)
    except json.JSONDecodeError:
        return res.status, {"raw": data}


def http_get(url_str, headers=None):
    if headers is None:
        headers = {}
    parsed = urllib.parse.urlparse(url_str)
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=60)
    conn.request(
        "GET",
        parsed.path + ("?" + parsed.query if parsed.query else ""),
        headers=headers,
    )
    res = conn.getresponse()
    data = res.read().decode("utf-8")
    conn.close()
    try:
        return res.status, json.loads(data)
    except json.JSONDecodeError:
        return res.status, {"raw": data}


def download_file(url_str, dest_path):
    parsed = urllib.parse.urlparse(url_str)
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=300)
    conn.request("GET", parsed.path + ("?" + parsed.query if parsed.query else ""))
    res = conn.getresponse()
    if res.status == 200:
        with open(dest_path, "wb") as f:
            f.write(res.read())
    conn.close()
    return res.status


# ─── STEP 5: Create tasks ─────────────────────────────────────────────────────
tasks = {}
generation_report_scenes = []

for entry in payloads:
    pf = entry["file"]
    payload_data = entry["data"]
    sid = pf.stem.replace("payload_", "")

    headers = {"Authorization": f"Bearer {API_KEY}"}

    # Prepare create request
    create_body = payload_data.copy()

    request_path = REQUESTS_DIR / f"{sid}_request.json"
    with open(request_path, "w", encoding="utf-8") as f:
        json.dump(create_body, f, indent=2, ensure_ascii=False)

    print(f"[{sid}] Creating task...")
    print(f"       Model: {create_body.get('model')}")
    print(f"       Duration: {create_body['input'].get('duration')}s")
    print(f"       Refs: {len(create_body['input'].get('reference_image_urls', []))}")

    status_code, response_data = http_post(CREATE_TASK_URL, create_body, headers)

    response_path = RESPONSES_DIR / f"{sid}_create_response.json"
    with open(response_path, "w", encoding="utf-8") as f:
        json.dump(
            {"statusCode": status_code, "body": response_data},
            f,
            indent=2,
            ensure_ascii=False,
        )

    task_id = (
        response_data.get("data", {}).get("taskId") or response_data.get("taskId") or ""
    )
    created_at = datetime.now(timezone.utc).isoformat()

    if status_code in (200, 201) and task_id:
        print(f"       OK | taskId={task_id}")
        tasks[sid] = {"taskId": task_id, "status": "created"}
        generation_report_scenes.append(
            {
                "sceneId": sid,
                "taskId": task_id,
                "createStatus": status_code,
                "finalStatus": "created",
                "videoUrl": None,
                "videoPath": None,
                "creditsUsed": response_data.get("data", {}).get("creditsUsed")
                or response_data.get("creditsUsed"),
                "errorMessage": None,
                "createdAt": created_at,
                "completedAt": None,
            }
        )
    else:
        err = response_data.get("message", str(response_data))
        print(f"       FAILED | status={status_code} | {err}")
        tasks[sid] = {"taskId": None, "status": "create_failed"}
        generation_report_scenes.append(
            {
                "sceneId": sid,
                "taskId": None,
                "createStatus": status_code,
                "finalStatus": "create_failed",
                "videoUrl": None,
                "videoPath": None,
                "creditsUsed": None,
                "errorMessage": err,
                "createdAt": created_at,
                "completedAt": None,
            }
        )

# Save task IDs
with open(TASKS_FILE, "w", encoding="utf-8") as f:
    json.dump(
        {"tasks": tasks, "timestamp": datetime.now(timezone.utc).isoformat()},
        f,
        indent=2,
        ensure_ascii=False,
    )

print(f"\nCreated: {sum(1 for t in tasks.values() if t['taskId'])}/{len(tasks)}")
print(
    f"Failed: {sum(1 for t in tasks.values() if t['status'] == 'create_failed')}/{len(tasks)}"
)

# ─── STEP 6: Poll for completion ──────────────────────────────────────────────
pending = {sid: t for sid, t in tasks.items() if t.get("taskId")}

for round_num in range(1, MAX_POLL_ROUNDS + 1):
    if not pending:
        break

    print(f"\n--- Poll round {round_num}/{MAX_POLL_ROUNDS} ---")
    completed = []

    for sid, t in pending.items():
        task_id = t["taskId"]
        record_url = RECORD_INFO_URL.rstrip("/")
        full_url = (
            f"{record_url}/{task_id}"
            if not record_url.endswith("/recordInfo")
            else f"{record_url}/{task_id}"
        )

        status_code, resp = http_get(full_url, {"Authorization": f"Bearer {API_KEY}"})

        poll_path = STATUS_DIR / f"{sid}_poll_{round_num:02d}.json"
        with open(poll_path, "w", encoding="utf-8") as f:
            json.dump(
                {"round": round_num, "statusCode": status_code, "body": resp},
                f,
                indent=2,
                ensure_ascii=False,
            )

        job_data = resp.get("data", resp)
        job_status = job_data.get("status", "unknown")
        finished_at = datetime.now(timezone.utc).isoformat()

        print(f"  [{sid}] {task_id} → {job_status}")

        # Update report entry
        for entry in generation_report_scenes:
            if entry["sceneId"] == sid:
                entry["finalStatus"] = job_status
                if "creditsUsed" in job_data:
                    entry["creditsUsed"] = job_data["creditsUsed"]

        if job_status in ("succeeded", "completed", "done"):
            video_url = (
                job_data.get("output", {}).get("video_url")
                or job_data.get("video_url")
                or ""
            )
            entry["videoUrl"] = video_url

            if video_url:
                dest = RAW_OUTPUT / f"{sid}__{task_id}.mp4"
                print(f"  [{sid}] Downloading video → {dest}")
                dl_status = download_file(video_url, dest)
                if dl_status == 200:
                    print(f"  [{sid}] Download OK ({dest.stat().st_size} bytes)")
                    entry["videoPath"] = str(dest.relative_to(BASE))
                else:
                    print(f"  [{sid}] Download FAILED (HTTP {dl_status})")
            else:
                print(f"  [{sid}] No video_url in response")

            entry["completedAt"] = finished_at
            completed.append(sid)

        elif job_status in ("failed", "error", "cancelled"):
            err_msg = job_data.get("error", job_data.get("message", "Unknown error"))
            entry["errorMessage"] = err_msg
            entry["completedAt"] = finished_at
            completed.append(sid)
            print(f"  [{sid}] FAILED: {err_msg}")

    for sid in completed:
        del pending[sid]

    if pending:
        time.sleep(POLL_INTERVAL)

if pending:
    print(
        f"\nTimeout: {len(pending)} tasks still pending after {MAX_POLL_ROUNDS} rounds"
    )
    for sid in pending:
        for entry in generation_report_scenes:
            if entry["sceneId"] == sid:
                entry["finalStatus"] = "timeout"
                entry["completedAt"] = datetime.now(timezone.utc).isoformat()

# ─── STEP 7: Final report ─────────────────────────────────────────────────────
final_report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "totalScenes": len(generation_report_scenes),
    "completed": sum(
        1
        for e in generation_report_scenes
        if e["finalStatus"] in ("succeeded", "completed", "done")
    ),
    "failed": sum(
        1
        for e in generation_report_scenes
        if e["finalStatus"]
        in ("failed", "error", "cancelled", "create_failed", "timeout")
    ),
    "scenes": generation_report_scenes,
    "kieCalled": True,
    "creditsConsumed": sum(
        (e["creditsUsed"] or 0)
        for e in generation_report_scenes
        if isinstance(e.get("creditsUsed"), (int, float))
    ),
}

final_report_path = VALIDATION_DIR / "final_generation_report.json"
with open(final_report_path, "w", encoding="utf-8") as f:
    json.dump(final_report, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 60)
print("GENERATION REPORT")
print("=" * 60)
print(f"Total: {final_report['totalScenes']}")
print(f"Completed: {final_report['completed']}")
print(f"Failed: {final_report['failed']}")
print(f"Credits consumed: {final_report['creditsConsumed']}")

for e in generation_report_scenes:
    mark = "OK" if e["finalStatus"] in ("succeeded", "completed", "done") else "FAIL"
    print(
        f"  [{mark}] {e['sceneId']} | {e['taskId']} | {e['finalStatus']} | video={e['videoPath'] or 'N/A'}"
    )

print(f"\nReport: {final_report_path}")
