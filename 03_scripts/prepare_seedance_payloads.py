#!/usr/bin/env python3
"""
prepare_seedance_payloads.py

Pre-flight dry-run payload builder for Kie.ai / Seedance 2.0.
Does NOT call Kie. Does NOT create tasks. Only prepares payloads.
"""

import json
import os
import sys
import http.client
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(os.environ.get("PROJECT_ROOT", os.getcwd()))

CONFIG_PATH = BASE / "00_config/campaign_config.json"
SCENE_PLAN_PATH = BASE / "00_config/final_scene_plan.json"
PAYLOADS_DIR = BASE / "04_logs/dry_run_payloads"
VALIDATION_DIR = BASE / "04_logs/validation"

for d in [PAYLOADS_DIR, VALIDATION_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_url(url, timeout=10):
    """Lightweight HEAD check for HTTP 200."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path
        if parsed.query:
            path += "?" + parsed.query

        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(host, port, timeout=timeout)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)

        conn.request("HEAD", path)
        res = conn.getresponse()
        status = res.status
        conn.close()
        return {"url": url, "statusCode": status, "ok": status == 200}
    except Exception as e:
        return {"url": url, "statusCode": 0, "ok": False, "error": str(e)}


def main():
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dryRun": True,
        "kieCalled": False,
        "configLoaded": False,
        "scenePlanLoaded": False,
        "assetValidation": {"total": 0, "found": 0, "missing": [], "ok": False},
        "promptValidation": {
            "total": 0,
            "found": 0,
            "empty": [],
            "missing": [],
            "ok": False,
        },
        "urlValidation": {
            "total": 0,
            "ok_count": 0,
            "fail_count": 0,
            "results": [],
            "allOk": False,
        },
        "payloadValidation": {
            "totalPayloads": 0,
            "allGenerateAudioTrue": True,
            "correctAspectRatio": True,
            "correctResolution": True,
            "correctDurations": True,
            "noReferenceAudioUrls": True,
            "noFirstFrameUrl": True,
            "noLastFrameUrl": True,
            "errors": [],
        },
        "payloadsGenerated": 0,
        "payloadPaths": [],
        "overallOk": False,
    }

    # 1. Load campaign config
    try:
        config = load_json(CONFIG_PATH)
        report["configLoaded"] = True
    except Exception as e:
        print(f"FATAL: Cannot load campaign_config.json: {e}")
        report["overallOk"] = False
        write_report(report)
        sys.exit(1)

    # 2. Load scene plan
    try:
        scenes = load_json(SCENE_PLAN_PATH)
        report["scenePlanLoaded"] = True
        assert isinstance(scenes, list) and len(scenes) == 7
    except Exception as e:
        print(f"FATAL: Cannot load final_scene_plan.json: {e}")
        report["overallOk"] = False
        write_report(report)
        sys.exit(1)

    base_url = config.get("publicAssetBaseUrl", "")

    # 3. Validate 10 assets exist
    all_asset_paths = set()
    for scene in scenes:
        for ref in scene["references"]:
            all_asset_paths.add(ref)

    report["assetValidation"]["total"] = len(all_asset_paths)
    for asset_path in sorted(all_asset_paths):
        full_path = BASE / asset_path
        if full_path.exists():
            report["assetValidation"]["found"] += 1
        else:
            report["assetValidation"]["missing"].append(asset_path)

    report["assetValidation"]["ok"] = (
        report["assetValidation"]["found"] == report["assetValidation"]["total"]
    )
    if not report["assetValidation"]["ok"]:
        print(f"FATAL: Missing assets: {report['assetValidation']['missing']}")
        write_report(report)
        sys.exit(1)

    # 4. Validate 7 prompt files exist
    report["promptValidation"]["total"] = len(scenes)
    for scene in scenes:
        pf = BASE / scene["promptFile"]
        if pf.exists():
            report["promptValidation"]["found"] += 1
            # 5. Validate prompt file is not empty
            content = pf.read_text(encoding="utf-8").strip()
            if not content:
                report["promptValidation"]["empty"].append(scene["promptFile"])
        else:
            report["promptValidation"]["missing"].append(scene["promptFile"])

    report["promptValidation"]["ok"] = (
        report["promptValidation"]["found"] == report["promptValidation"]["total"]
        and len(report["promptValidation"]["empty"]) == 0
    )
    if not report["promptValidation"]["ok"]:
        print(
            f"FATAL: Prompt issues - missing: {report['promptValidation']['missing']}, empty: {report['promptValidation']['empty']}"
        )
        write_report(report)
        sys.exit(1)

    # 6-7. Build URLs and check HTTP 200
    url_results = []
    all_urls_ok = True
    for scene in scenes:
        for ref in scene["references"]:
            url = base_url + ref
            result = check_url(url)
            result["sceneId"] = scene["sceneId"]
            url_results.append(result)
            if not result["ok"]:
                all_urls_ok = False

    report["urlValidation"]["total"] = len(url_results)
    report["urlValidation"]["ok_count"] = sum(1 for r in url_results if r["ok"])
    report["urlValidation"]["fail_count"] = sum(1 for r in url_results if not r["ok"])
    report["urlValidation"]["results"] = url_results
    report["urlValidation"]["allOk"] = all_urls_ok

    if not all_urls_ok:
        failed = [r["url"] for r in url_results if not r["ok"]]
        print(f"WARNING: Some URLs failed HTTP 200 check: {failed}")
        # Continue anyway - director may update URLs later

    # 8. Build payloads
    for scene in scenes:
        prompt_text = (BASE / scene["promptFile"]).read_text(encoding="utf-8").strip()
        reference_urls = [base_url + ref for ref in scene["references"]]

        payload = {
            "model": config["model"],
            "input": {
                "prompt": prompt_text,
                "reference_image_urls": reference_urls,
                "generate_audio": config.get("generateAudio", True),
                "resolution": config["resolution"],
                "aspect_ratio": config["aspectRatio"],
                "duration": scene["duration"],
                "web_search": config.get("webSearch", False),
            },
        }

        payload_filename = f"payload_{scene['sceneId']}.json"
        payload_path = PAYLOADS_DIR / payload_filename
        with open(payload_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        report["payloadsGenerated"] += 1
        report["payloadPaths"].append(f"04_logs/dry_run_payloads/{payload_filename}")

        # 9. Validate payload
        inp = payload["input"]
        pv = report["payloadValidation"]
        pv["totalPayloads"] += 1

        if inp.get("generate_audio") is not True:
            pv["allGenerateAudioTrue"] = False
            pv["errors"].append(
                {"sceneId": scene["sceneId"], "check": "generate_audio must be true"}
            )

        if inp.get("aspect_ratio") != "9:16":
            pv["correctAspectRatio"] = False
            pv["errors"].append(
                {"sceneId": scene["sceneId"], "check": "aspect_ratio must be 9:16"}
            )

        if inp.get("resolution") != "720p":
            pv["correctResolution"] = False
            pv["errors"].append(
                {"sceneId": scene["sceneId"], "check": "resolution must be 720p"}
            )

        expected_dur = 5 if scene["sceneId"].startswith(("06", "07")) else 4
        if inp.get("duration") != expected_dur:
            pv["correctDurations"] = False
            pv["errors"].append(
                {
                    "sceneId": scene["sceneId"],
                    "check": f"duration must be {expected_dur}",
                    "got": inp.get("duration"),
                }
            )

        if "reference_audio_urls" in inp:
            pv["noReferenceAudioUrls"] = False
            pv["errors"].append(
                {
                    "sceneId": scene["sceneId"],
                    "check": "no reference_audio_urls allowed",
                }
            )

        if "first_frame_url" in inp:
            pv["noFirstFrameUrl"] = False
            pv["errors"].append(
                {"sceneId": scene["sceneId"], "check": "no first_frame_url allowed"}
            )

        if "last_frame_url" in inp:
            pv["noLastFrameUrl"] = False
            pv["errors"].append(
                {"sceneId": scene["sceneId"], "check": "no last_frame_url allowed"}
            )

    # 10. Overall status
    pv = report["payloadValidation"]
    report["overallOk"] = (
        report["configLoaded"]
        and report["scenePlanLoaded"]
        and report["assetValidation"]["ok"]
        and report["promptValidation"]["ok"]
        and pv["allGenerateAudioTrue"]
        and pv["correctAspectRatio"]
        and pv["correctResolution"]
        and pv["correctDurations"]
        and pv["noReferenceAudioUrls"]
        and pv["noFirstFrameUrl"]
        and pv["noLastFrameUrl"]
        and report["payloadsGenerated"] == 7
    )

    write_report(report)

    status = "PASSED" if report["overallOk"] else "FAILED"
    print(f"\nPre-flight check: {status}")
    print(f"  Config loaded: {report['configLoaded']}")
    print(f"  Scene plan loaded: {report['scenePlanLoaded']}")
    print(
        f"  Assets: {report['assetValidation']['found']}/{report['assetValidation']['total']} found"
    )
    print(
        f"  Prompts: {report['promptValidation']['found']}/{report['promptValidation']['total']} found, {len(report['promptValidation']['empty'])} empty"
    )
    print(
        f"  URLs: {report['urlValidation']['ok_count']}/{report['urlValidation']['total']} HTTP 200"
    )
    print(f"  Payloads: {report['payloadsGenerated']} generated")
    print(f"  Payload errors: {len(pv['errors'])}")
    print(f"\nReport: 04_logs/validation/preflight_report.json")


def write_report(report):
    report_path = VALIDATION_DIR / "preflight_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
