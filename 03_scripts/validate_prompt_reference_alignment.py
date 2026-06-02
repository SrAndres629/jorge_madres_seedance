#!/usr/bin/env python3
"""
validate_prompt_reference_alignment.py

Validates alignment between:
- 02_prompts/final/prompt_*.txt
- 00_config/final_scene_plan.json (expected references)
- 04_logs/dry_run_payloads/payload_*.json (actual references + prompt)

Does NOT call Kie. Does NOT generate video. Does NOT spend credits.
"""

import json
import os
import sys
import http.client
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(os.environ.get("PROJECT_ROOT", os.getcwd()))

SCENE_PLAN_PATH = BASE / "00_config/final_scene_plan.json"
PROMPTS_DIR = BASE / "02_prompts/final"
PAYLOADS_DIR = BASE / "04_logs/dry_run_payloads"
VALIDATION_DIR = BASE / "04_logs/validation"

VALIDATION_DIR.mkdir(parents=True, exist_ok=True)


def check_url(url, timeout=10):
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
        return {"statusCode": status, "ok": status == 200}
    except Exception as e:
        return {"statusCode": 0, "ok": False, "error": str(e)}


def main():
    scenes = json.loads(SCENE_PLAN_PATH.read_text(encoding="utf-8"))

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "totalScenes": len(scenes),
        "scenes": [],
        "overallOk": True,
        "summary": {
            "allPromptsMatch": True,
            "allReferencesMatch": True,
            "allDurationsOk": True,
            "allGenerateAudioOk": True,
            "allUrlsHttp200": True,
            "noForbiddenFields": True,
        },
    }

    for scene in scenes:
        sid = scene["sceneId"]
        prompt_file = BASE / scene["promptFile"]
        payload_file = PAYLOADS_DIR / f"payload_{sid}.json"

        entry = {
            "sceneId": sid,
            "promptFile": scene["promptFile"],
            "payloadFile": f"04_logs/dry_run_payloads/payload_{sid}.json",
            "expectedReferences": scene["references"],
            "actualReferences": [],
            "referencesMatch": False,
            "promptMatchesFile": False,
            "durationOk": False,
            "generateAudioOk": False,
            "aspectRatioOk": False,
            "resolutionOk": False,
            "noReferenceAudioUrls": True,
            "noFirstFrameUrl": True,
            "noLastFrameUrl": True,
            "noGeneratedTextInPrompt": True,
            "urlChecks": [],
            "allUrlsOk": False,
            "overallOk": False,
            "errors": [],
        }

        # Load prompt file
        if not prompt_file.exists():
            entry["errors"].append(f"Prompt file not found: {scene['promptFile']}")
            entry["overallOk"] = False
            report["overallOk"] = False
            report["scenes"].append(entry)
            continue

        prompt_text = prompt_file.read_text(encoding="utf-8").strip()

        # Load payload
        if not payload_file.exists():
            entry["errors"].append(f"Payload file not found: payload_{sid}.json")
            entry["overallOk"] = False
            report["overallOk"] = False
            report["scenes"].append(entry)
            continue

        payload = json.loads(payload_file.read_text(encoding="utf-8"))
        inp = payload.get("input", {})

        # 1. Check references match
        actual_refs = inp.get("reference_image_urls", [])
        # Convert full URLs back to relative paths for comparison
        base_url = (
            "https://raw.githubusercontent.com/SrAndres629/jorge_madres_seedance/main/"
        )
        actual_rel = []
        for url in actual_refs:
            if url.startswith(base_url):
                actual_rel.append(url[len(base_url) :])
            else:
                actual_rel.append(url)

        entry["actualReferences"] = actual_rel
        expected_refs = scene["references"]

        if set(actual_rel) == set(expected_refs) and len(actual_rel) == len(
            expected_refs
        ):
            entry["referencesMatch"] = True
        else:
            entry["referencesMatch"] = False
            entry["errors"].append(
                f"References mismatch. Expected: {expected_refs}, Got: {actual_rel}"
            )
            report["summary"]["allReferencesMatch"] = False

        # Check no cross-contamination
        all_scene_names = [
            f"scene_{s['sceneId']}" for s in scenes if s["sceneId"] != sid
        ]
        for ref in actual_rel:
            for other in all_scene_names:
                if other in ref:
                    entry["errors"].append(
                        f"Cross-contamination: {ref} references wrong scene {other}"
                    )
                    entry["referencesMatch"] = False
                    report["summary"]["allReferencesMatch"] = False

        # 2. Check prompt matches file
        payload_prompt = inp.get("prompt", "").strip()
        if payload_prompt == prompt_text:
            entry["promptMatchesFile"] = True
        else:
            entry["promptMatchesFile"] = False
            entry["errors"].append(
                f"Prompt mismatch: payload prompt ({len(payload_prompt)} chars) != file ({len(prompt_text)} chars)"
            )
            report["summary"]["allPromptsMatch"] = False

        # 3. Check duration
        expected_dur = scene["duration"]
        actual_dur = inp.get("duration")
        if actual_dur == expected_dur:
            entry["durationOk"] = True
        else:
            entry["errors"].append(
                f"Duration mismatch: expected {expected_dur}, got {actual_dur}"
            )
            report["summary"]["allDurationsOk"] = False

        # 4. Check generate_audio
        if inp.get("generate_audio") is True:
            entry["generateAudioOk"] = True
        else:
            entry["errors"].append(
                f"generate_audio must be true, got {inp.get('generate_audio')}"
            )
            report["summary"]["allGenerateAudioOk"] = False

        # 5. Check aspect_ratio
        if inp.get("aspect_ratio") == "9:16":
            entry["aspectRatioOk"] = True
        else:
            entry["errors"].append(
                f"aspect_ratio must be 9:16, got {inp.get('aspect_ratio')}"
            )

        # 6. Check resolution
        if inp.get("resolution") == "720p":
            entry["resolutionOk"] = True
        else:
            entry["errors"].append(
                f"resolution must be 720p, got {inp.get('resolution')}"
            )

        # 7. Check forbidden fields
        if "reference_audio_urls" in inp:
            entry["noReferenceAudioUrls"] = False
            entry["errors"].append("reference_audio_urls must not be present")
            report["summary"]["noForbiddenFields"] = False

        if "first_frame_url" in inp:
            entry["noFirstFrameUrl"] = False
            entry["errors"].append("first_frame_url must not be present")
            report["summary"]["noForbiddenFields"] = False

        if "last_frame_url" in inp:
            entry["noLastFrameUrl"] = False
            entry["errors"].append("last_frame_url must not be present")
            report["summary"]["noForbiddenFields"] = False

        # 8. Check no generated text requested in prompt
        text_keywords = [
            "generate text",
            "on-screen text",
            "write text",
            "add text",
            "overlay text",
        ]
        for kw in text_keywords:
            if kw.lower() in prompt_text.lower():
                # Check it's in a "Do not" context
                lines = prompt_text.split("\n")
                for line in lines:
                    if (
                        kw.lower() in line.lower()
                        and "do not" not in line.lower()
                        and "don't" not in line.lower()
                    ):
                        entry["noGeneratedTextInPrompt"] = False
                        entry["errors"].append(
                            f"Prompt may request generated text: '{line.strip()}'"
                        )

        # 9. HTTP 200 check for all reference URLs
        for url in actual_refs:
            result = check_url(url)
            entry["urlChecks"].append({"url": url, **result})
            if not result["ok"]:
                entry["errors"].append(f"URL failed HTTP 200: {url}")

        if all(u.get("ok", False) for u in entry["urlChecks"]):
            entry["allUrlsOk"] = True
        else:
            report["summary"]["allUrlsHttp200"] = False

        # Overall for this scene
        entry["overallOk"] = (
            entry["referencesMatch"]
            and entry["promptMatchesFile"]
            and entry["durationOk"]
            and entry["generateAudioOk"]
            and entry["aspectRatioOk"]
            and entry["resolutionOk"]
            and entry["noReferenceAudioUrls"]
            and entry["noFirstFrameUrl"]
            and entry["noLastFrameUrl"]
            and entry["noGeneratedTextInPrompt"]
            and entry["allUrlsOk"]
        )

        if not entry["overallOk"]:
            report["overallOk"] = False

        report["scenes"].append(entry)

    # Write report
    report_path = VALIDATION_DIR / "prompt_reference_alignment_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print summary
    status = "PASSED" if report["overallOk"] else "FAILED"
    print(f"\nAlignment check: {status}")
    print(f"  Scenes checked: {report['totalScenes']}")
    for s in report["scenes"]:
        mark = "OK" if s["overallOk"] else "FAIL"
        print(
            f"  [{mark}] {s['sceneId']}: refs={s['referencesMatch']} prompt={s['promptMatchesFile']} dur={s['durationOk']} audio={s['generateAudioOk']} urls={s['allUrlsOk']}"
        )
        if s["errors"]:
            for e in s["errors"]:
                print(f"         ERROR: {e}")
    print(f"\nSummary:")
    for k, v in report["summary"].items():
        print(f"  {k}: {'OK' if v else 'FAIL'}")
    print(f"\nReport: 04_logs/validation/prompt_reference_alignment_report.json")

    if not report["overallOk"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
