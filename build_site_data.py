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


REPO = Path(__file__).parent


def extract_toml_summary(toml_path: Path) -> dict:
    """Pull n_ends and n_throws from a detected.toml."""
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    summary_rows = data.get("game", {}).get("summary", [])
    # summary is list-of-lists: [header, row, row, ...]
    if len(summary_rows) > 1:
        n_ends = len(summary_rows) - 1      # exclude header
        n_throws = sum(row[1] for row in summary_rows[1:])   # col 1 = n_throws
    else:
        n_ends = 0
        n_throws = 0
    return {"n_ends": n_ends, "n_throws": n_throws}


def main():
    with open(REPO / "index.json") as f:
        index = json.load(f)

    games = []
    for entry in index:
        yt_id = entry["youtube_id"]
        game = dict(entry)

        meta_path = REPO / "games" / yt_id / "metadata.json"
        toml_path = REPO / "games" / yt_id / "detected.toml"

        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            # metadata.json wins over index.json for any overlapping fields
            game.update({k: v for k, v in meta.items() if k not in ("status",)})

        if toml_path.exists():
            game.update(extract_toml_summary(toml_path))
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
    print(f"Wrote {len(games)} games ({done} analyzed) → {out}")


if __name__ == "__main__":
    main()
