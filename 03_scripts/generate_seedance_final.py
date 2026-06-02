#!/usr/bin/env python3
"""
generate_seedance_final.py

Safe Kie.ai / Seedance 2.0 generation script.
Defaults to dry-run mode. Requires --execute + confirmation phrase for real calls.

CRITICAL:
- recordInfo uses query param: ?taskId=TASK_ID (NOT path-based)
- States: waiting → queuing → generating → success | fail
- Result URLs may come from resultJson (JSON string) or output.video_url
- Credits may come as creditsConsumed or creditsUsed
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

DRY_RUN = "--execute" not in sys.argv
CONFIRMATION_PHRASE = "GENERAR_7_CLIPS_JORGE"


# ─── Utility functions ───────────────────────────────────────────────────────
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


def build_record_info_url(base_url, task_id):
    """KIE API uses query param: GET /api/v1/jobs/recordInfo?taskId=..."""
    return base_url.rstrip("/") + "?taskId=" + urllib.parse.quote(task_id)


def extract_state(job_data):
    """Read Kie job state from possible field names. Returns (state_str, is_active, is_success, is_fail)."""
    state = (
        job_data.get("state")
        or job_data.get("status")
        or job_data.get("data", {}).get("state")
        or job_data.get("data", {}).get("status")
        or "unknown"
    )
    active_states = {
        "waiting",
        "queuing",
        "generating",
        "processing",
        "pending",
        "running",
    }
    success_states = {"success", "succeeded", "completed", "done"}
    fail_states = {"fail", "failed", "error", "cancelled", "canceled", "timeout"}

    return (
        state,
        state in active_states,
        state in success_states,
        state in fail_states,
    )


def extract_video_url(job_data):
    """Robust extraction of video URL from Kie response. Tries multiple paths."""
    # 1. output.video_url
    output = job_data.get("output", {})
    if isinstance(output, dict) and output.get("video_url"):
        return output["video_url"]

    # 2. Direct video_url
    if job_data.get("video_url"):
        return job_data["video_url"]

    # 3. resultUrl
    if job_data.get("resultUrl"):
        return job_data["resultUrl"]

    # 4. resultUrls[0]
    result_urls = job_data.get("resultUrls", [])
    if isinstance(result_urls, list) and len(result_urls) > 0:
        return result_urls[0]

    # 5. resultJson (may be a JSON string)
    result_json = job_data.get("resultJson", "")
    if isinstance(result_json, str) and result_json.strip():
        try:
            parsed = json.loads(result_json)
            return extract_video_url_from_parsed(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(result_json, dict):
        url = extract_video_url_from_parsed(result_json)
        if url:
            return url

    # 6. Check nested data
    data = job_data.get("data", {})
    if isinstance(data, dict):
        return extract_video_url(data)

    return ""


def extract_video_url_from_parsed(parsed):
    """Search a parsed resultJson dict for video URLs."""
    if isinstance(parsed, dict):
        for key in ("resultUrls", "video_urls", "urls", "output_urls"):
            urls = parsed.get(key, [])
            if isinstance(urls, list) and len(urls) > 0:
                return urls[0]
        if parsed.get("video_url"):
            return parsed["video_url"]
        if parsed.get("url"):
            return parsed["url"]
        for k, v in parsed.items():
            if isinstance(v, str) and v.startswith("http") and ".mp4" in v:
                return v
        for k, v in parsed.items():
            if isinstance(v, str) and v.startswith("http"):
                return v
    return ""


def extract_credits(parsed):
    """Extract credits from possible field names. Returns number or 0."""
    for key in ("creditsConsumed", "creditsUsed", "credits_consumed", "credits_used"):
        val = parsed.get(key)
        if isinstance(val, (int, float)):
            return val
    data = parsed.get("data", {})
    if isinstance(data, dict):
        return extract_credits(data)
    return 0


# ─── PARSER VALIDATION (mock data, no Kie calls) ─────────────────────────────
MOCK_SUCCESS = {
    "code": 200,
    "msg": "success",
    "data": {
        "taskId": "task_test_001",
        "state": "success",
        "resultJson": '{"resultUrls":["https://cdn.kie.ai/output/test_video.mp4"]}',
        "creditsConsumed": 50,
    },
}

MOCK_FAIL = {
    "code": 200,
    "msg": "success",
    "data": {
        "taskId": "task_test_002",
        "state": "fail",
        "resultJson": "",
        "creditsConsumed": 25,
    },
}

MOCK_ACTIVE = {
    "code": 200,
    "msg": "success",
    "data": {
        "taskId": "task_test_003",
        "state": "generating",
        "resultJson": "",
    },
}


def run_parser_validation():
    """Test all parser functions against mock data. Returns (all_ok, detail)."""
    results = []

    # Test success state
    _, _, is_success, _ = extract_state(MOCK_SUCCESS["data"])
    results.append(("successStateRecognized", is_success))

    # Test fail state
    _, _, _, is_fail = extract_state(MOCK_FAIL["data"])
    results.append(("failStateRecognized", is_fail))

    # Test active state
    _, is_active, _, _ = extract_state(MOCK_ACTIVE["data"])
    results.append(("activeStateRecognized", is_active))

    # Test video URL extraction from resultJson
    video_url = extract_video_url(MOCK_SUCCESS["data"])
    expected_url = "https://cdn.kie.ai/output/test_video.mp4"
    results.append(("resultJsonParsed", video_url == expected_url))
    results.append(("videoUrlExtracted", bool(video_url)))

    # Test credits extraction
    credits = extract_credits(MOCK_SUCCESS["data"])
    results.append(("creditsConsumedExtracted", credits == 50))

    # Test recordInfo URL construction
    test_url = build_record_info_url(
        "https://api.kie.ai/api/v1/jobs/recordInfo", "abc123"
    )
    results.append(("recordInfoUsesQueryParam", test_url.endswith("?taskId=abc123")))

    all_ok = all(v for _, v in results)

    detail = dict(results)
    return all_ok, detail


parser_all_ok, parser_detail = run_parser_validation()

parser_report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "noKieCalled": True,
    "overallOk": parser_all_ok,
    **parser_detail,
}

parser_report_path = VALIDATION_DIR / "kie_api_parser_validation_report.json"
with open(parser_report_path, "w", encoding="utf-8") as f:
    json.dump(parser_report, f, indent=2, ensure_ascii=False)

if not parser_all_ok:
    print("FATAL: Parser validation FAILED.")
    print(json.dumps(parser_report, indent=2))
    sys.exit(1)

print("Parser validation PASSED (mock data, no Kie calls)")
for k, v in parser_detail.items():
    print(f"  {k}: {'OK' if v else 'FAIL'}")

# ─── STEP 1: Load and validate all reports ───────────────────────────────────
preflight_errors = []

try:
    config = load_json(CONFIG_PATH)
except Exception as e:
    print(f"FATAL: Cannot load campaign_config.json: {e}")
    sys.exit(1)

try:
    preflight = load_json(PREFLIGHT_PATH)
except Exception as e:
    print(f"FATAL: Cannot load preflight_report.json: {e}")
    sys.exit(1)

try:
    alignment = load_json(ALIGNMENT_PATH)
except Exception as e:
    print(f"FATAL: Cannot load alignment report: {e}")
    sys.exit(1)

try:
    audit = load_json(AUDIT_PATH)
except Exception as e:
    print(f"FATAL: Cannot load audit report: {e}")
    sys.exit(1)

if not preflight.get("overallOk"):
    preflight_errors.append("preflight_report.json overallOk is false")
if not alignment.get("overallOk"):
    preflight_errors.append("alignment_report.json overallOk is false")
if not audit.get("summary", {}).get("overallOk"):
    preflight_errors.append("final_prompt_content_audit.json overallOk is false")

payload_files = sorted(PAYLOADS_DIR.glob("payload_*.json"))
if len(payload_files) != 7:
    preflight_errors.append(f"Expected 7 payloads, found {len(payload_files)}")

payloads = []
for pf in payload_files:
    p = load_json(pf)
    inp = p.get("input", {})
    payloads.append({"file": pf, "data": p})

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
        preflight_errors.append(f"{pf.name}: duration must be {expected_dur}")

    for forbidden in ("reference_audio_urls", "first_frame_url", "last_frame_url"):
        if forbidden in inp:
            preflight_errors.append(f"{pf.name}: {forbidden} must not be present")

url_failures = []
for entry in payloads:
    for url in entry["data"]["input"].get("reference_image_urls", []):
        result = check_url(url)
        if not result["ok"]:
            url_failures.append(result)
            preflight_errors.append(f"URL not 200: {url}")

gen_preflight = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "dryRun": DRY_RUN,
    "reportsValid": len(preflight_errors) == 0,
    "parserValid": parser_all_ok,
    "validationErrors": preflight_errors,
    "payloadsFound": len(payloads),
    "ready": len(preflight_errors) == 0 and parser_all_ok,
}

gen_preflight_path = VALIDATION_DIR / "final_generation_preflight_report.json"
with open(gen_preflight_path, "w", encoding="utf-8") as f:
    json.dump(gen_preflight, f, indent=2, ensure_ascii=False)

print(f"\n{'=' * 60}")
print("GENERATION PREFLIGHT")
print("=" * 60)
print(f"Mode: {'DRY-RUN' if DRY_RUN else 'EXECUTE (real)'}")
print(f"Reports valid: {gen_preflight['reportsValid']}")
print(f"Parser valid: {gen_preflight['parserValid']}")
print(f"Payloads: {gen_preflight['payloadsFound']}")
print(f"Errors: {len(preflight_errors)}")
print(f"Ready: {gen_preflight['ready']}")

for e in preflight_errors:
    print(f"  ERROR: {e}")

if not gen_preflight["ready"]:
    print("\nPreflight FAILED.")
    sys.exit(1)

print(f"\nReports: {gen_preflight_path}, {parser_report_path}")

if DRY_RUN:
    print("\nDRY-RUN mode. No Kie API calls made.")
    sys.exit(0)

# ─── EXECUTE REAL ────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("REAL EXECUTION MODE")
print("=" * 60)
print(f"Tasks to create: {len(payloads)}")
print("Credits WILL be consumed.")
confirmation = input("\nType exact phrase: ").strip()
if confirmation != CONFIRMATION_PHRASE:
    print(f"Aborting. Expected: {CONFIRMATION_PHRASE}")
    sys.exit(1)

try:
    import dotenv

    dotenv.load_dotenv(BASE / ".env")
except ImportError:
    print("FATAL: pip install python-dotenv")
    sys.exit(1)

API_KEY = os.environ.get("KIE_API_KEY", "")
CREATE_URL = os.environ.get(
    "KIE_CREATE_TASK_URL", "https://api.kie.ai/api/v1/jobs/createTask"
)
RECORD_INFO_URL = os.environ.get(
    "KIE_RECORD_INFO_URL", "https://api.kie.ai/api/v1/jobs/recordInfo"
)

if not API_KEY:
    print("FATAL: KIE_API_KEY not set")
    sys.exit(1)

POLL_INTERVAL = config.get("pollIntervalSeconds", 30)
MAX_POLL_ROUNDS = config.get("maxPollRounds", 40)

print(f"API Key: {'*' * min(len(API_KEY), 8)}***")
print(f"Poll: {POLL_INTERVAL}s, max {MAX_POLL_ROUNDS} rounds\n")


def http_post(url_str, body, headers=None):
    if headers is None:
        headers = {}
    parsed = urllib.parse.urlparse(url_str)
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=60)
    raw = json.dumps(body).encode("utf-8")
    headers["Content-Type"] = "application/json"
    conn.request(
        "POST",
        parsed.path + ("?" + parsed.query if parsed.query else ""),
        body=raw,
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
    path_q = parsed.path + ("?" + parsed.query if parsed.query else "")
    conn.request("GET", path_q, headers=headers)
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
    path_q = parsed.path + ("?" + parsed.query if parsed.query else "")
    conn.request("GET", path_q)
    res = conn.getresponse()
    if res.status in (200, 302, 301):
        data = res.read()
        with open(dest_path, "wb") as f:
            f.write(data)
    conn.close()
    return res.status


# ─── STEP 5: Create tasks ────────────────────────────────────────────────────
tasks = {}
report_scenes = []
headers_auth = {"Authorization": f"Bearer {API_KEY}"}

for entry in payloads:
    pf = entry["file"]
    sid = pf.stem.replace("payload_", "")
    body = entry["data"].copy()

    # Save request
    req_path = REQUESTS_DIR / f"{sid}_request.json"
    with open(req_path, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2, ensure_ascii=False)

    print(
        f"[{sid}] Creating task... dur={body['input'].get('duration')}s refs={len(body['input'].get('reference_image_urls', []))}"
    )
    sc, resp = http_post(CREATE_URL, body, headers_auth)

    # Save response
    resp_path = RESPONSES_DIR / f"{sid}_create_response.json"
    with open(resp_path, "w", encoding="utf-8") as f:
        json.dump({"statusCode": sc, "body": resp}, f, indent=2, ensure_ascii=False)

    task_id = resp.get("data", {}).get("taskId") or resp.get("taskId", "")
    created_at = datetime.now(timezone.utc).isoformat()

    if sc in (200, 201) and task_id:
        print(f"       OK | taskId={task_id}")
        tasks[sid] = {"taskId": task_id, "status": "created"}
        report_scenes.append(
            {
                "sceneId": sid,
                "taskId": task_id,
                "createStatus": sc,
                "finalStatus": "created",
                "videoUrl": None,
                "videoPath": None,
                "creditsUsed": extract_credits(resp),
                "errorMessage": None,
                "createdAt": created_at,
                "completedAt": None,
            }
        )
    else:
        err = resp.get("message") or resp.get("msg") or str(resp)[:200]
        print(f"       FAILED | {sc} | {err}")
        tasks[sid] = {"taskId": None, "status": "create_failed"}
        report_scenes.append(
            {
                "sceneId": sid,
                "taskId": None,
                "createStatus": sc,
                "finalStatus": "create_failed",
                "videoUrl": None,
                "videoPath": None,
                "creditsUsed": 0,
                "errorMessage": err,
                "createdAt": created_at,
                "completedAt": None,
            }
        )

with open(TASKS_FILE, "w", encoding="utf-8") as f:
    json.dump(
        {"tasks": tasks, "timestamp": datetime.now(timezone.utc).isoformat()},
        f,
        indent=2,
        ensure_ascii=False,
    )

created_n = sum(1 for t in tasks.values() if t["taskId"])
print(f"\nCreated: {created_n}/{len(tasks)}")

# ─── STEP 6: Poll ─────────────────────────────────────────────────────────────
pending = {sid: t for sid, t in tasks.items() if t.get("taskId")}

for rnd in range(1, MAX_POLL_ROUNDS + 1):
    if not pending:
        break
    print(f"\n--- Poll round {rnd}/{MAX_POLL_ROUNDS} ---")
    completed = []

    for sid, t in pending.items():
        task_id = t["taskId"]
        url = build_record_info_url(RECORD_INFO_URL, task_id)
        sc, resp = http_get(url, headers_auth)

        poll_path = STATUS_DIR / f"{sid}_poll_{rnd:02d}.json"
        with open(poll_path, "w", encoding="utf-8") as f:
            json.dump(
                {"round": rnd, "url": url, "statusCode": sc, "body": resp},
                f,
                indent=2,
                ensure_ascii=False,
            )

        job_data = resp.get("data", resp)
        state, is_active, is_success, is_fail = extract_state(job_data)
        now = datetime.now(timezone.utc).isoformat()
        print(f"  [{sid}] {task_id} → {state}")

        # Update report
        for e in report_scenes:
            if e["sceneId"] == sid:
                e["finalStatus"] = state
                cr = extract_credits(resp)
                if cr:
                    e["creditsUsed"] = cr

        if is_success:
            video_url = extract_video_url(job_data)
            for e in report_scenes:
                if e["sceneId"] == sid:
                    e["videoUrl"] = video_url
                    e["completedAt"] = now
            if video_url:
                dest = RAW_OUTPUT / f"{sid}__{task_id}.mp4"
                print(f"  [{sid}] Downloading → {dest.name}")
                dl_sc = download_file(video_url, dest)
                if dl_sc in (200, 302, 301) and dest.stat().st_size > 0:
                    print(f"       OK | {dest.stat().st_size} bytes")
                    for e in report_scenes:
                        if e["sceneId"] == sid:
                            e["videoPath"] = str(dest.relative_to(BASE))
                else:
                    print(
                        f"       Download FAILED (HTTP {dl_sc}, size={dest.stat().st_size})"
                    )
            else:
                print(f"  [{sid}] WARN: success but no video_url found in response")
            completed.append(sid)

        elif is_fail:
            err_msg = (
                job_data.get("error") or job_data.get("message") or str(resp)[:300]
            )
            print(f"  [{sid}] FAILED: {err_msg}")
            for e in report_scenes:
                if e["sceneId"] == sid:
                    e["errorMessage"] = err_msg
                    e["completedAt"] = now
            completed.append(sid)

    for sid in completed:
        del pending[sid]

    if pending:
        time.sleep(POLL_INTERVAL)

if pending:
    print(f"\nTimeout: {len(pending)} pending after {MAX_POLL_ROUNDS} rounds")
    for sid in pending:
        for e in report_scenes:
            if e["sceneId"] == sid:
                e["finalStatus"] = "timeout"
                e["completedAt"] = datetime.now(timezone.utc).isoformat()

# ─── STEP 7: Final report ────────────────────────────────────────────────────
final_report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "totalScenes": len(report_scenes),
    "completed": sum(
        1
        for e in report_scenes
        if e["finalStatus"] in ("success", "succeeded", "completed", "done")
    ),
    "failed": sum(
        1
        for e in report_scenes
        if e["finalStatus"]
        in ("fail", "failed", "error", "cancelled", "create_failed", "timeout")
    ),
    "scenes": report_scenes,
    "kieCalled": True,
}

final_path = VALIDATION_DIR / "final_generation_report.json"
with open(final_path, "w", encoding="utf-8") as f:
    json.dump(final_report, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 60)
print("FINAL GENERATION REPORT")
print("=" * 60)
print(f"Completed: {final_report['completed']} | Failed: {final_report['failed']}")
for e in report_scenes:
    mk = (
        "OK"
        if e["finalStatus"] in ("success", "succeeded", "completed", "done")
        else "FAIL"
    )
    print(
        f"  [{mk}] {e['sceneId']} | {e['taskId']} | {e['finalStatus']} | video={e['videoPath'] or 'N/A'}"
    )

print(f"\nReport: {final_path}")
