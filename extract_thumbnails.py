#!/usr/bin/env python3
"""extract_thumbnails.py — generate small throw thumbnails for the website.

For games with a local throws/ directory: resize existing JPEGs.
For YouTube-only games: seek to each throw timestamp and extract via ffmpeg.

Usage:
    # All analyzed games in the repo:
    python3 extract_thumbnails.py

    # Specific YouTube IDs:
    python3 extract_thumbnails.py 8rICGhgpN00 rH1a0tPhEts
"""

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from PIL import Image

REPO      = Path(__file__).parent
THUMB_W   = 240
THUMB_H   = 135
THUMB_Q   = 72    # JPEG quality
FPS       = 2.0
YT_BASE   = "https://www.youtube.com/watch?v="


# ── Helpers ───────────────────────────────────────────────────────────────────

def frame_to_sec(f: int) -> float:
    return f / FPS


def _yt_direct_url(youtube_id: str) -> str | None:
    """Get a direct video URL from yt-dlp (for ffmpeg seeking)."""
    yt_dlp = shutil.which("yt-dlp") or os.path.expanduser("~/teaching/bin/yt-dlp")
    try:
        result = subprocess.run(
            [yt_dlp, "-f", "bestvideo[height=1080]/best[height=1080]",
             "--get-url", "--no-warnings",
             f"{YT_BASE}{youtube_id}"],
            capture_output=True, text=True, timeout=30,
        )
        url = result.stdout.strip()
        return url if url.startswith("http") else None
    except Exception as e:
        print(f"  yt-dlp error: {e}")
        return None


def _ffmpeg_seek_frame(direct_url: str, time_sec: float, out_path: Path) -> bool:
    """Extract one frame from a direct URL at time_sec via ffmpeg."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-ss", str(time_sec),
             "-i", direct_url,
             "-vframes", "1",
             "-vf", f"scale={THUMB_W}:{THUMB_H}",
             "-q:v", "5",
             str(out_path)],
            timeout=30, check=True,
        )
        return out_path.exists()
    except Exception:
        return False


def _resize_jpeg(src: Path, dst: Path) -> None:
    """Resize an existing JPEG to thumbnail size."""
    with Image.open(src) as img:
        img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
        img.save(dst, "JPEG", quality=THUMB_Q, optimize=True)


def _throw_filename(end: int, throw: int, color: str) -> str:
    c = "red" if color == "red" else "yel"
    return f"E{end:01d}T{throw:02d}_{c}.jpg"


# ── Per-game extraction ───────────────────────────────────────────────────────

def process_game(youtube_id: str, source_throws: Path | None = None) -> int:
    """Extract thumbnails for one game. Returns count of thumbs written.

    source_throws: path to an existing throws/ directory (e.g. from a local
                   cvt run). If None, falls back to YouTube seeking.
    """
    game_dir  = REPO / "games" / youtube_id
    toml_path = game_dir / "detected.toml"
    # Prefer caller-supplied source, then repo-local throws/
    local_throws = source_throws or (game_dir / "throws")
    thumb_dir = game_dir / "thumbs"

    if not toml_path.exists():
        print(f"  {youtube_id}: no detected.toml — skipping")
        return 0

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    thumb_dir.mkdir(exist_ok=True)

    summary = data.get("game", {}).get("summary", [])[1:]  # skip header row
    written = 0
    direct_url = None   # lazy-fetch only if needed

    for row in summary:
        end_num, _, _, first_throw = row
        end_data = data.get("end", {}).get(str(end_num), {})
        frames   = end_data.get("throw_frames", [])
        colors   = _color_sequence(first_throw, len(frames))

        for throw_num, (frame, color) in enumerate(zip(frames, colors), 1):
            fname    = _throw_filename(end_num, throw_num, color)
            dst      = thumb_dir / fname

            if dst.exists():
                written += 1
                continue

            # Try local source first — filename may include frame number
            # e.g. E1T01_f775_red.jpg or E1T01_red.jpg
            local_src = None
            if local_throws and local_throws.exists():
                c = "red" if color == "red" else "yel"
                prefix = f"E{end_num}T{throw_num:02d}_"
                suffix = f"_{c}.jpg"
                for candidate in local_throws.iterdir():
                    if candidate.name.startswith(prefix) and candidate.name.endswith(suffix):
                        local_src = candidate
                        break
            if local_src:
                _resize_jpeg(local_src, dst)
                written += 1
                continue

            # Fall back to YouTube seek
            if direct_url is None:
                print(f"  {youtube_id}: fetching direct URL from YouTube...")
                direct_url = _yt_direct_url(youtube_id)
                if not direct_url:
                    print(f"  {youtube_id}: could not get direct URL — skipping")
                    return written

            t = frame_to_sec(frame)
            ok = _ffmpeg_seek_frame(direct_url, t, dst)
            if ok:
                written += 1
            else:
                print(f"    failed: E{end_num}T{throw_num:02d} @ {t:.1f}s")

    return written


def _color_sequence(first_throw: str, n: int) -> list[str]:
    order = ["red", "yellow"] if first_throw == "drk" else ["yellow", "red"]
    return [order[i % 2] for i in range(n)]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="YouTube IDs to process (default: all analyzed)")
    ap.add_argument("--source-dir", help="Parent dir containing {video_id}_apr12.nosync/throws/ dirs")
    ap.add_argument("--id-map", help="Comma-separated youtube_id=video_id pairs for --source-dir lookup")
    args = ap.parse_args()

    # Build youtube_id -> source throws path mapping
    source_map: dict[str, Path] = {}
    if args.source_dir and args.id_map:
        source_root = Path(args.source_dir)
        for pair in args.id_map.split(","):
            yt_id, vid_id = pair.strip().split("=")
            # Try common naming patterns
            for pattern in [f"{vid_id}_apr12.nosync", f"{vid_id}.nosync", vid_id]:
                p = source_root / pattern / "throws"
                if p.is_dir():
                    source_map[yt_id] = p
                    break

    targets = args.ids if args.ids else [
        d.name for d in (REPO / "games").iterdir()
        if (d / "detected.toml").exists()
    ]

    print(f"Processing {len(targets)} games...")
    total = 0
    for yt_id in sorted(targets):
        src = source_map.get(yt_id)
        src_label = f" (from {src.parent.name})" if src else " (YouTube)"
        print(f"  {yt_id}{src_label}...", end=" ", flush=True)
        n = process_game(yt_id, source_throws=src)
        print(f"{n} thumbs")
        total += n

    print(f"\nDone: {total} thumbnails total")


if __name__ == "__main__":
    main()
