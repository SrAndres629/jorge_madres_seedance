#!/usr/bin/env python3
"""
final_prompt_content_audit.py

Audits every prompt file and its corresponding payload for
exact v2 content, required markers, grammar issues, and alignment.

Does NOT call Kie. Does NOT generate video. Does NOT spend credits.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(os.environ.get("PROJECT_ROOT", os.getcwd()))
PROMPTS_DIR = BASE / "02_prompts/final"
PAYLOADS_DIR = BASE / "04_logs/dry_run_payloads"
VALIDATION_DIR = BASE / "04_logs/validation"
VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

SCENES = [
    {
        "sceneId": "01_hook_00_04",
        "markers": [
            "emotional entry point",
            "mirror is the main visual portal",
            "first frame must feel impossible to ignore",
        ],
    },
    {
        "sceneId": "02_time_04_08",
        "markers": [
            "stable axis inside the chaos",
            "The chaos belongs to the objects, time, and camera movement",
            "native to social media",
        ],
    },
    {
        "sceneId": "03_water_08_12",
        "markers": [
            "symbolic and elegant",
            "water itself should motivate the transition",
            "sell the problem without making the face look destroyed",
        ],
    },
    {
        "sceneId": "04_precision_12_16",
        "markers": [
            "quieter than the previous clips",
            "protect the dignity of the woman",
            "the line does not come out like before",
        ],
    },
    {
        "sceneId": "05_solution_16_20",
        "markers": [
            "relief, readiness, and everyday confidence",
            "three quick benefit impressions",
            "not a fake before-and-after",
        ],
    },
    {
        "sceneId": "06_authority_20_25",
        "markers": [
            "official authority reveal",
            "He does not perform magic",
            "chaos stopped by expertise, not fantasy",
        ],
    },
    {
        "sceneId": "07_cta_25_30",
        "markers": [
            "CapCut",
            "final CTA card",
            "writing on WhatsApp is the next easy step",
        ],
    },
]

GRAMMAR_ERRORS = ["an calm", "an firm", "an clear"]

entries = []
all_ok = True
any_final_prompt_issue = False
any_payload_prompt_issue = False
any_grammar_issues = False

for scene in SCENES:
    sid = scene["sceneId"]
    prompt_path = PROMPTS_DIR / f"prompt_{sid}.txt"
    payload_path = PAYLOADS_DIR / f"payload_{sid}.json"

    prompt_text = prompt_path.read_text(encoding="utf-8").strip()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload_prompt = payload["input"]["prompt"].strip()

    # Markers in prompt file
    prompt_markers_found = {m: m in prompt_text for m in scene["markers"]}
    prompt_markers_ok = all(prompt_markers_found.values())

    # Markers in payload prompt
    payload_markers_found = {m: m in payload_prompt for m in scene["markers"]}
    payload_markers_ok = all(payload_markers_found.values())

    # Grammar check (both prompt file and payload)
    grammar_in_prompt = []
    grammar_in_payload = []
    for ge in GRAMMAR_ERRORS:
        if ge in prompt_text:
            grammar_in_prompt.append(ge)
        if ge in payload_prompt:
            grammar_in_payload.append(ge)

    # Match
    prompts_equal = prompt_text == payload_prompt

    entry = {
        "sceneId": sid,
        "promptFile": f"02_prompts/final/prompt_{sid}.txt",
        "promptCharCount": len(prompt_text),
        "first300Chars_promptFile": prompt_text[:300],
        "requiredMarkers_promptFile": prompt_markers_found,
        "promptFile_markersOk": prompt_markers_ok,
        "payloadFile": f"04_logs/dry_run_payloads/payload_{sid}.json",
        "payloadPromptCharCount": len(payload_prompt),
        "first300Chars_payloadPrompt": payload_prompt[:300],
        "requiredMarkers_payloadPrompt": payload_markers_found,
        "payloadPrompt_markersOk": payload_markers_ok,
        "promptFileEqualsPayloadPrompt": prompts_equal,
        "grammarErrors_promptFile": grammar_in_prompt,
        "grammarErrors_payloadPrompt": grammar_in_payload,
        "grammarOk": len(grammar_in_prompt) == 0 and len(grammar_in_payload) == 0,
        "overallOk": prompt_markers_ok
        and payload_markers_ok
        and prompts_equal
        and (len(grammar_in_prompt) == 0)
        and (len(grammar_in_payload) == 0),
    }

    if not entry["overallOk"]:
        all_ok = False
    if not prompt_markers_ok:
        any_final_prompt_issue = True
    if not payload_markers_ok or not prompts_equal:
        any_payload_prompt_issue = True
    if not entry["grammarOk"]:
        any_grammar_issues = True

    entries.append(entry)

report_json = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "totalScenes": len(entries),
    "scenes": entries,
    "summary": {
        "finalPromptsOk": not any_final_prompt_issue,
        "payloadPromptsOk": not any_payload_prompt_issue,
        "noGrammarIssues": not any_grammar_issues,
        "allPromptsMatchPayloads": all(
            e["promptFileEqualsPayloadPrompt"] for e in entries
        ),
        "overallOk": all_ok,
    },
}

# Write JSON
json_path = VALIDATION_DIR / "final_prompt_content_audit.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(report_json, f, indent=2, ensure_ascii=False)

# Write Markdown
md_path = VALIDATION_DIR / "final_prompt_content_audit.md"
md = [
    "# Final Prompt Content Audit",
    "",
    f"**Timestamp:** {report_json['timestamp']}",
    f"**Overall:** {'PASSED' if all_ok else 'FAILED'}",
    "",
    "## Summary",
    "",
    f"- finalPromptsOk: **{report_json['summary']['finalPromptsOk']}**",
    f"- payloadPromptsOk: **{report_json['summary']['payloadPromptsOk']}**",
    f"- noGrammarIssues: **{report_json['summary']['noGrammarIssues']}**",
    f"- allPromptsMatchPayloads: **{report_json['summary']['allPromptsMatchPayloads']}**",
    f"- overallOk: **{report_json['summary']['overallOk']}**",
    "",
    "---",
    "",
]

for e in entries:
    md.append(f"## Scene {e['sceneId']}")
    md.append("")
    md.append(f"- Prompt file: `{e['promptFile']}` ({e['promptCharCount']} chars)")
    md.append(
        f"- Payload file: `{e['payloadFile']}` ({e['payloadPromptCharCount']} chars)"
    )
    md.append(f"- Prompt equals payload: **{e['promptFileEqualsPayloadPrompt']}**")
    md.append(f"- Grammar OK: **{e['grammarOk']}**")
    md.append(f"- Overall scene OK: **{e['overallOk']}**")
    md.append("")

    md.append("### Required markers in prompt file")
    for m, v in e["requiredMarkers_promptFile"].items():
        md.append(f"- [{'x' if v else ' '}] `{m}`")

    md.append("")
    md.append("### Required markers in payload prompt")
    for m, v in e["requiredMarkers_payloadPrompt"].items():
        md.append(f"- [{'x' if v else ' '}] `{m}`")

    md.append("")
    md.append("### First 300 chars (prompt file)")
    md.append("```")
    md.append(e["first300Chars_promptFile"])
    md.append("```")

    if e["grammarErrors_promptFile"]:
        md.append(
            f"WARNING: grammar errors in prompt file: {e['grammarErrors_promptFile']}"
        )
    if e["grammarErrors_payloadPrompt"]:
        md.append(
            f"WARNING: grammar errors in payload prompt: {e['grammarErrors_payloadPrompt']}"
        )

    md.append("")
    md.append("---")
    md.append("")

md_text = "\n".join(md)
with open(md_path, "w", encoding="utf-8") as f:
    f.write(md_text)

# Console output
status = "PASSED" if all_ok else "FAILED"
print(f"Final prompt content audit: {status}")
for e in entries:
    m = "OK" if e["overallOk"] else "FAIL"
    print(
        f"  [{m}] {e['sceneId']} | markers={e['promptFile_markersOk']} | match={e['promptFileEqualsPayloadPrompt']} | grammar={e['grammarOk']} | chars={e['promptCharCount']}"
    )

print(f"\nSummary:")
for k, v in report_json["summary"].items():
    print(f"  {k}: {'OK' if v else 'FAIL'}")

print(f"\nReports:")
print(f"  {json_path}")
print(f"  {md_path}")

if not all_ok:
    exit(1)
