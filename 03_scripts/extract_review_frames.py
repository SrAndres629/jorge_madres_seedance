#!/usr/bin/env python3
"""
extract_review_frames.py

Extracts keyframes from 5 generated MP4 videos and builds contact sheets.
Uses gstreamer for frame extraction (no ffmpeg required) and PIL for contact sheets.

Does NOT call Kie. Does NOT generate video. Does NOT spend credits.
"""

import os
import re
import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

BASE = Path(os.environ.get("PROJECT_ROOT", os.getcwd()))
RAW_DIR = BASE / "05_outputs/raw"
REVIEW_DIR = BASE / "05_outputs/review"
KEYFRAMES_DIR = REVIEW_DIR / "keyframes"
SHEETS_DIR = REVIEW_DIR / "contact_sheets"
REPORT_PATH = REVIEW_DIR / "review_assets_report.json"

KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
SHEETS_DIR.mkdir(parents=True, exist_ok=True)

TARGET_TIMES = [
    ("00_25", 0.25),
    ("01_00", 1.00),
    ("02_00", 2.00),
    ("03_00", 3.00),
    ("03_75", 3.75),
]


def get_video_duration(mp4_path):
    """Use gst-discoverer-1.0 to get duration in seconds. Returns float or None."""
    try:
        result = subprocess.run(
            ["gst-discoverer-1.0", str(mp4_path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return None
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stdout)
        if m:
            h, mm, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + mm * 60 + s
    except Exception:
        pass
    return None


def get_video_resolution(mp4_path):
    """Use gst-discoverer-1.0 to get width/height. Returns (w, h) or (None, None)."""
    try:
        result = subprocess.run(
            ["gst-discoverer-1.0", str(mp4_path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return None, None
        w_match = re.search(r"Width\s*:\s*(\d+)", result.stdout)
        h_match = re.search(r"Height\s*:\s*(\d+)", result.stdout)
        if w_match and h_match:
            return int(w_match.group(1)), int(h_match.group(1))
    except Exception:
        pass
    return None, None


def extract_frame_at_time(mp4_path, timestamp, out_jpeg):
    """Extract a single frame at the given timestamp using gstreamer.
    Uses playbin with seek event + a single-frame jpegenc + filesink."""
    if out_jpeg.exists():
        out_jpeg.unlink()
    pipeline = [
        "gst-launch-1.0",
        "-e",
        "playbin",
        f"uri=file://{mp4_path.resolve()}",
        f"video-sink=fakesink",
    ]
    # Simpler approach: use decodebin + appsink-like via videoscale + jpegenc + filesink
    # We seek to the timestamp using a combination of decodebin with index seek
    seek_ns = int(timestamp * 1_000_000_000)
    pipeline_str = (
        f"filesrc location={mp4_path} ! "
        f"qtdemux ! h264parse ! avdec_h264 ! "
        f"videoconvert ! videoscale ! "
        f"jpegenc quality=85 ! "
        f"filesink location={out_jpeg}"
    )
    # We use gst-launch with seek via --no-position and a pad probe is complex.
    # Simpler: use playbin to seek, but for static extraction we run the whole
    # pipeline and rely on `gst-launch-1.0 -e` to dump the first frame.
    # However to seek to a specific time we use this trick:
    # run the demuxer, seek, then snap the next decoded frame.
    # Easiest: use the snapshot element from compositor? Not available.
    # The cleanest: do a full decode, then for each target time do a SEPARATE
    # short pipeline that seeks to the time and emits ONE frame.
    #
    # Use a 2-step approach with seek based on a manual pipeline:
    # Actually the most reliable is: use decodebin with "source" element seek
    # by position. gst-launch supports this via playbin with --flags.
    #
    # Simplest working approach in practice:
    # gst-launch-1.0 -e -v filesrc ! qtdemux name=d d.video_0 ! h264parse !
    # avdec_h264 ! videoconvert ! jpegenc ! multifilesink location=...
    # This will dump ALL frames. We extract the one closest to the target.
    #
    # For our purposes (small MP4s ~4s), dumping all frames is fine.
    # We then pick the frame whose index matches the target time.
    pass
    return None


def dump_all_frames(mp4_path, tmp_dir, prefix):
    """Dump every frame of the video as a JPEG into tmp_dir with prefix."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(tmp_dir / f"{prefix}_%05d.jpg")
    pipeline = (
        f"gst-launch-1.0 -e "
        f"filesrc location={mp4_path} "
        f"! qtdemux "
        f"! avdec_h264 "
        f"! videoconvert "
        f"! videoscale "
        f"! videorate "
        f"! jpegenc quality=85 "
        f"! multifilesink location={pattern}"
    )
    result = subprocess.run(
        pipeline, shell=True, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        print(f"  [debug] gstreamer stderr: {result.stderr[:300]}")
        return []
    frames = sorted(tmp_dir.glob(f"{prefix}_*.jpg"))
    return frames


def pick_frames_at_times(frames, duration, target_times, out_paths):
    """Pick frames closest to the target times. Returns list of (time_label, out_path, src_index, used_time)."""
    if not frames or not duration or duration <= 0:
        return []
    # Assume uniform frame distribution across duration
    n = len(frames)
    picks = []
    for label, target in target_times:
        # Cap target to be safely within duration
        safe_target = min(target, max(0, duration - 0.05))
        idx = int(round((safe_target / duration) * (n - 1)))
        idx = max(0, min(n - 1, idx))
        src = frames[idx]
        out = out_paths[label]
        # Copy/rename the file
        out.write_bytes(src.read_bytes())
        picks.append((label, out, idx, safe_target))
    return picks


def make_contact_sheet(scene_id, frame_paths_in_order, out_path):
    """Compose a contact sheet with 5 frames in a row, scaled down, with labels."""
    images = []
    for path in frame_paths_in_order:
        if path.exists():
            images.append(Image.open(path).convert("RGB"))
    if not images:
        return False
    # Resize each to a common thumbnail width preserving 9:16
    thumb_w = 320
    thumb_h = int(thumb_w * 16 / 9)
    thumbs = []
    for img in images:
        ratio = thumb_w / img.width
        new_h = int(img.height * ratio)
        resized = img.resize((thumb_w, new_h), Image.Resampling.LANCZOS)
        thumbs.append(resized)
    # Compose: horizontal row with thin separator and label below each
    label_h = 30
    sep_w = 6
    bg = (255, 255, 255)
    total_w = thumb_w * 5 + sep_w * 4
    total_h = thumb_h + label_h + 10
    sheet = Image.new("RGB", (total_w, total_h), bg)
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14
        )
    except OSError:
        font = ImageFont.load_default()
    time_labels = ["t=0.25s", "t=1.00s", "t=2.00s", "t=3.00s", "t=3.75s"]
    for i, t in enumerate(thumbs):
        x = i * (thumb_w + sep_w)
        sheet.paste(t, (x, 0))
        # label centered below
        label = f"{scene_id} | {time_labels[i]}"
        bbox = draw.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        draw.text(
            (x + (thumb_w - text_w) // 2, thumb_h + 6), label, fill=(0, 0, 0), font=font
        )
    sheet.save(out_path, "JPEG", quality=88)
    return True


def process_video(mp4_path, scene_id, tmp_dir):
    out_paths = {
        label: KEYFRAMES_DIR / f"{scene_id}_t{label.replace('_', '_')}.jpg"
        for label, _ in TARGET_TIMES
    }
    duration = get_video_duration(mp4_path)
    width, height = get_video_resolution(mp4_path)
    if duration is None or width is None:
        return {
            "sceneId": scene_id,
            "videoPath": str(mp4_path.relative_to(BASE)),
            "duration": None,
            "resolution": [width, height],
            "framesExtracted": 0,
            "frames": {},
            "contactSheetPath": None,
            "ok": False,
            "error": "Could not probe video",
        }
    frames = dump_all_frames(mp4_path, tmp_dir, f"{scene_id}_dump")
    if not frames:
        return {
            "sceneId": scene_id,
            "videoPath": str(mp4_path.relative_to(BASE)),
            "duration": round(duration, 3),
            "resolution": [width, height],
            "framesExtracted": 0,
            "frames": {},
            "contactSheetPath": None,
            "ok": False,
            "error": "gstreamer pipeline failed",
        }
    picks = pick_frames_at_times(frames, duration, TARGET_TIMES, out_paths)
    # Cleanup dump
    for f in frames:
        try:
            f.unlink()
        except OSError:
            pass
    frame_report = {}
    for label, outp, idx, used_t in picks:
        frame_report[label] = {
            "path": str(outp.relative_to(BASE)),
            "sourceFrameIndex": idx,
            "usedTimestamp": round(used_t, 3),
        }
    # Contact sheet
    sheet_path = SHEETS_DIR / f"{scene_id}_contact_sheet.jpg"
    frame_paths_in_order = [out_paths[label] for label, _ in TARGET_TIMES]
    sheet_ok = make_contact_sheet(scene_id, frame_paths_in_order, sheet_path)
    return {
        "sceneId": scene_id,
        "videoPath": str(mp4_path.relative_to(BASE)),
        "duration": round(duration, 3),
        "resolution": [width, height],
        "framesExtracted": len(picks),
        "frames": frame_report,
        "contactSheetPath": str(sheet_path.relative_to(BASE)) if sheet_ok else None,
        "ok": len(picks) == 5 and sheet_ok,
    }


def main():
    tmp_root = BASE / "04_logs" / "_tmp_frames"
    tmp_root.mkdir(parents=True, exist_ok=True)

    videos = sorted(RAW_DIR.glob("*.mp4"))
    if len(videos) != 5:
        print(f"WARNING: Expected 5 videos in {RAW_DIR}, found {len(videos)}")

    results = []
    for v in videos:
        # Parse sceneId from filename: {sceneId}__{taskId}.mp4
        stem = v.stem
        scene_id = stem.split("__")[0]
        print(f"[{scene_id}] Processing {v.name} ({v.stat().st_size} bytes)")
        result = process_video(v, scene_id, tmp_root / scene_id)
        results.append(result)
        print(
            f"  duration={result.get('duration')}s, frames={result.get('framesExtracted')}/5, ok={result.get('ok')}"
        )

    # Clean tmp
    try:
        for d in tmp_root.iterdir():
            for f in d.iterdir():
                f.unlink()
            d.rmdir()
        tmp_root.rmdir()
    except OSError:
        pass

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "noKieCalled": True,
        "noCreditsSpent": True,
        "totalVideos": len(results),
        "successfulScenes": sum(1 for r in results if r.get("ok")),
        "scenes": results,
        "overallOk": all(r.get("ok") for r in results),
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("REVIEW ASSETS REPORT")
    print("=" * 60)
    print(f"Total videos: {report['totalVideos']}")
    print(f"Successful: {report['successfulScenes']}")
    print(f"Overall OK: {report['overallOk']}")
    for r in results:
        print(
            f"  [{'OK' if r['ok'] else 'FAIL'}] {r['sceneId']} | dur={r.get('duration')}s | frames={r.get('framesExtracted')}/5"
        )
    print(f"\nReport: {REPORT_PATH}")
    if not report["overallOk"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
