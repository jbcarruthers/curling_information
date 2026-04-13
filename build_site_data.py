#!/usr/bin/env python3
"""build_site_data.py — generate games_data.json for the GitHub Pages site.

Run from the curling_information repo root after adding new detected.toml files.
Reads index.json + each game's metadata.json + detected.toml to produce a
single JSON file the site loads in one request.

Usage:
    python3 build_site_data.py
"""

import json
import tomllib
from pathlib import Path


REPO        = Path(__file__).parent
FPS         = 2.0
SETTLING_S  = 25.0   # assumed stone-settling time (TIMING_RULES.md §fixed approx)


def _color_seq(first_throw: str, n: int) -> list[str]:
    order = ["red", "yellow"] if first_throw == "drk" else ["yellow", "red"]
    return [order[i % 2] for i in range(n)]


def _has_thumbs(yt_id: str) -> bool:
    return (REPO / "games" / yt_id / "thumbs").is_dir()


def extract_toml_detail(toml_path: Path, yt_id: str) -> dict:
    """Extract n_ends, n_throws, per-end throw list, and clock totals."""
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    summary_rows = data.get("game", {}).get("summary", [])[1:]  # skip header

    n_ends   = len(summary_rows)
    n_throws = sum(r[1] for r in summary_rows)

    ends = []
    clock = {"red": 0.0, "yellow": 0.0}   # cumulative seconds
    thumbs_exist = _has_thumbs(yt_id)

    for row in summary_rows:
        end_num, _, camera, first_throw = row
        end_data = data.get("end", {}).get(str(end_num), {})
        frames   = end_data.get("throw_frames", [])
        colors   = _color_seq(first_throw, len(frames))

        throws = []

        for i, (frame, color) in enumerate(zip(frames, colors)):
            t_sec = frame / FPS
            yt_t  = int(frame / FPS)   # YouTube &t= param (integer seconds)

            # Clock time used this throw (TIMING_RULES.md):
            # T1 always = 0 (clock never starts before first throw of end)
            # T2-T16: clock ran from settling of previous throw until this release
            #   used = (this_frame - prev_frame) / FPS - SETTLING_S, clamped >= 0
            # Inter-end gaps are excluded because we reset per end.
            if i == 0:
                used_s = 0.0
            else:
                used_s = max(0.0, (frame - frames[i - 1]) / FPS - SETTLING_S)

            clock[color] = round(clock[color] + used_s, 1)

            thumb = None
            if thumbs_exist:
                c = "red" if color == "red" else "yel"
                thumb = f"games/{yt_id}/thumbs/E{end_num}T{i+1:02d}_{c}.jpg"

            throws.append({
                "n": i + 1,
                "color": color,
                "frame": frame,
                "t_sec": round(t_sec, 1),
                "yt_t": yt_t,
                "used_s": round(used_s, 1),
                "thumb": thumb,
            })

        ends.append({
            "end": end_num,
            "camera": camera,
            "first_throw": first_throw,
            "throws": throws,
        })

    return {
        "n_ends":   n_ends,
        "n_throws": n_throws,
        "clock_red_s":    round(clock["red"],    1),
        "clock_yellow_s": round(clock["yellow"], 1),
        "ends": ends,
    }


def main():
    with open(REPO / "index.json") as f:
        index = json.load(f)

    games = []
    for entry in index:
        yt_id = entry["youtube_id"]
        game  = dict(entry)

        meta_path = REPO / "games" / yt_id / "metadata.json"
        toml_path = REPO / "games" / yt_id / "detected.toml"

        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            game.update({k: v for k, v in meta.items() if k not in ("status",)})

        if toml_path.exists():
            game.update(extract_toml_detail(toml_path, yt_id))
            game["status"] = "done"
        else:
            game.setdefault("n_ends", None)
            game.setdefault("n_throws", None)
            game["status"] = "pending"

        games.append(game)

    out = REPO / "games_data.json"
    with open(out, "w") as f:
        json.dump(games, f, separators=(",", ":"))

    done = sum(1 for g in games if g["status"] == "done")
    size_kb = out.stat().st_size // 1024
    print(f"Wrote {len(games)} games ({done} analyzed), {size_kb} KB → {out}")


if __name__ == "__main__":
    main()
