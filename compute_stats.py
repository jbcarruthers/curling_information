#!/usr/bin/env python3
"""compute_stats.py — generate stats_data.json for the stats page.

Run after build_site_data.py whenever new games are added or the
color mapping is updated.

Usage:
    python3 compute_stats.py
"""

import json
import statistics
from pathlib import Path
from datetime import date

REPO = Path(__file__).parent

# ── Color mapping ─────────────────────────────────────────────────────────────
# For each analyzed game (sorted by date), which team number threw first?
# 1 = team1 threw first,  2 = team2 threw first.
# First throw color × this answer → red_team / yel_team.
# Update this list whenever new games are added and verified.
FIRST_THROWER = [
    # game#  youtube_id          date        team1               team2
    1,   # 4W3YQ7j8li4     2025-10-07  O'Neill           Carruthers
    1,   # aXKwz7hvi1w     2025-10-13  Jussaume          Secor P
    2,   # K1N2gLYi92Q     2025-10-20  Simon             Bialek
    2,   # yIl9ZEJwWdk     2025-10-21  Berube            Mullaney
    2,   # kVVL4iHC14Q     2026-01-13  Secor D           Mullaney
    2,   # dX8y3YEnOvk     2026-01-13  Pekowitz          Williams
    1,   # ZPv-_eyvoa0     2026-01-13  Rowe              Celiku
    2,   # rXyE06qa88E     2026-01-13  Berube            Barclay
    2,   # 8rICGhgpN00     2026-03-17  Tschumakow        Berube
    2,   # ySlRrnzqrYs     2026-03-17  Williams          Simard
    2,   # CEVkCyDmj14     2026-03-17  Mullaney          Huse
    2,   # W9GxfgBRev8     2026-03-17  Walker            Ho
    2,   # RrTpiNJuNWk     2026-03-24  Barclay           O'Neill
    1,   # vHz0TpD4L5Y     2026-03-24  Carruthers        Tschumakow  (corrected)
    1,   # rH1a0tPhEts     2026-03-31  Carruthers        Barclay
    2,   # rGQuJrEvHX4     2026-03-31  Pekowitz          collier
    2,   # t0-BqPciWzw     2026-03-31  Davis             Secor D
    1,   # 0sZGO-qykRw     2026-03-31  Tschumakow        O'Neill
    2,   # 7-tPgq2Uyhc     2026-03-31  Celiku            Huse
    1,   # q57ngxyLmJk     2026-03-31  Leichter          Ho         (corrected)
    2,   # WxqN1eCEyl8     2026-04-07  Huse              Mullaney
    2,   # rQc35-7Pny0     2026-04-07  Neill             Leichter
    2,   # EUIwlJBb4LA     2026-04-07  Walker            Ho
    2,   # mnZbb75XYtM     2026-04-07  Williams          Simard
]

POS_NAMES = {1: "lead", 2: "second", 3: "vice", 4: "skip"}


def _assign_colors(g, ans):
    t1 = g.get("team1", "?")
    t2 = g.get("team2", "?")
    c1 = g["ends"][0]["throws"][0]["color"]
    if ans == 1:
        return (t1, t2) if c1 == "red" else (t2, t1)
    else:
        return (t2, t1) if c1 == "red" else (t1, t2)


def compute(games_data):
    done = [g for g in games_data if g.get("status") == "done" and g.get("ends")]
    done.sort(key=lambda g: g["date"])

    assert len(done) == len(FIRST_THROWER), \
        f"FIRST_THROWER has {len(FIRST_THROWER)} entries but {len(done)} analyzed games"

    color_map = []
    team_end_times = {}    # team -> [scaled s per end]
    team_pos_times = {}    # team -> pos(1-4) -> [used_s per throw]
    from_start = {}        # end_num -> [per-team s]
    from_end_rel = {}      # relative position from end (-1=final) -> [per-team s]

    for g, ans in zip(done, FIRST_THROWER):
        red_team, yel_team = _assign_colors(g, ans)
        color_map.append({
            "youtube_id": g["youtube_id"],
            "date": g["date"],
            "red_team": red_team,
            "yel_team": yel_team,
        })

        n_ends = len(g["ends"])
        for end in g["ends"]:
            en = end["end"]
            throws = end["throws"]
            n = len(throws)
            scale = 16 / n if n < 16 else 1.0

            red_s = sum(t["used_s"] for t in throws if t["color"] == "red")
            yel_s = sum(t["used_s"] for t in throws if t["color"] == "yellow")

            team_end_times.setdefault(red_team, []).append(red_s * scale)
            team_end_times.setdefault(yel_team, []).append(yel_s * scale)

            from_start.setdefault(en, []).append(red_s * scale)
            from_start.setdefault(en, []).append(yel_s * scale)

            rel = en - n_ends - 1
            from_end_rel.setdefault(rel, []).append(red_s * scale)
            from_end_rel.setdefault(rel, []).append(yel_s * scale)

            # Per-position
            red_throws = sorted([t for t in throws if t["color"] == "red"],  key=lambda t: t["n"])
            yel_throws = sorted([t for t in throws if t["color"] == "yellow"], key=lambda t: t["n"])
            for color_throws, team in ((red_throws, red_team), (yel_throws, yel_team)):
                for i, t in enumerate(color_throws):
                    pos = i // 2 + 1
                    team_pos_times.setdefault(team, {}).setdefault(pos, []).append(t["used_s"])

    # ── Team stats ────────────────────────────────────────────────────────────
    team_stats = []
    for team, times in team_end_times.items():
        pos_stats = {}
        for p in (1, 2, 3, 4):
            d = team_pos_times.get(team, {}).get(p, [])
            if d:
                pos_stats[POS_NAMES[p]] = {
                    "median": round(statistics.median(d), 1),
                    "mean":   round(sum(d) / len(d), 1),
                    "n":      len(d),
                }
        team_stats.append({
            "team":          team,
            "n_ends":        len(times),
            "median_per_end": round(statistics.median(times), 1),
            "mean_per_end":   round(sum(times) / len(times), 1),
            "positions":     pos_stats,
        })
    team_stats.sort(key=lambda x: x["median_per_end"], reverse=True)

    # ── End progression ───────────────────────────────────────────────────────
    end_from_start = []
    for en in sorted(from_start):
        d = from_start[en]
        end_from_start.append({
            "end":    en,
            "label":  f"End {en}",
            "n":      len(d),
            "median": round(statistics.median(d), 1),
            "mean":   round(sum(d) / len(d), 1),
        })

    REL_LABELS = {-1:"Final", -2:"2nd last", -3:"3rd last", -4:"4th last",
                  -5:"5th last", -6:"6th last", -7:"7th last", -8:"8th last"}
    end_from_finish = []
    for rel in sorted(from_end_rel, reverse=True):
        d = from_end_rel[rel]
        end_from_finish.append({
            "rel":    rel,
            "label":  REL_LABELS.get(rel, str(rel)),
            "n":      len(d),
            "median": round(statistics.median(d), 1),
            "mean":   round(sum(d) / len(d), 1),
        })

    return {
        "generated":       str(date.today()),
        "n_games":         len(done),
        "n_ends":          sum(len(g["ends"]) for g in done),
        "n_throws":        sum(g["n_throws"] for g in done),
        "color_map":       color_map,
        "team_stats":      team_stats,
        "end_from_start":  end_from_start,
        "end_from_finish": end_from_finish,
    }


def main():
    with open(REPO / "games_data.json") as f:
        games_data = json.load(f)

    stats = compute(games_data)

    out = REPO / "stats_data.json"
    with open(out, "w") as f:
        json.dump(stats, f, separators=(",", ":"))

    print(f"Wrote stats_data.json — {stats['n_games']} games, "
          f"{stats['n_ends']} ends, {len(stats['team_stats'])} teams")


if __name__ == "__main__":
    main()
