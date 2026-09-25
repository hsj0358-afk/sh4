"""Phase 0-B: structural digest of a saved round artifact (READ-ONLY).

    python artifact_digest.py <repo> <artifact.json> [--out digest.json]

Prints one compact JSON document so two collections (PC vs Actions) can be
compared without shipping the 6 MB artifact itself. Nothing is written
except the optional --out file.
"""
import dataclasses, json, sys
from collections import Counter
from pathlib import Path

repo, path = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else ""
sys.path.insert(0, str(repo))
from toto import artifact                                   # noqa: E402
from toto.models import find_season_match_by_id, find_season_match  # noqa: E402,F401

rep, why = artifact.load_path(path)
if rep is None:
    sys.exit(f"cannot load {path}: {why}")


def filled(v):
    return v not in (None, "", [], {})


FIELDS = [f.name for f in dataclasses.fields(type(rep.matches[0].home_profile.stats))]
field_fill = Counter()
matches = []
for m in rep.matches:
    sides = {}
    for side in ("home", "away"):
        ref, prof = getattr(m, side), getattr(m, f"{side}_profile")
        st = prof.stats if prof else None
        names = [f for f in FIELDS if st is not None and filled(getattr(st, f))]
        field_fill.update(names)
        sides[side] = {
            "ko": ref.name_ko, "canon": ref.canonical, "matched": ref.matched,
            "rank": getattr(st, "rank", None), "played": getattr(st, "played", None),
            "points": getattr(st, "points", None),
            "stats_filled": len(names),
            "form": [f"{e.date}:{e.result}" for e in (prof.form if prof else [])][:5],
            "strengths": len(prof.strengths) if prof else 0,
            "weaknesses": len(prof.weaknesses) if prof else 0,
            "style": len(prof.style_of_play or []) if prof else 0,
            "team_page_ok": getattr(prof, "team_page_ok", None) if prof else None,
            "rest_days": getattr(prof, "rest_days", None) if prof else None,
        }
    an = m.analysis
    axes = {}
    if an is not None:
        for side in ("home", "away"):
            ta = getattr(an, side, None)
            for ax in getattr(type(ta), "AXES", ()) if ta else ():
                axis = getattr(ta, ax, None)
                axes[f"{side}.{ax}"] = len(axis.metrics) if axis is not None else None
    # actual result of this fixture, if the season index already has it
    sm = None
    for s in rep.season_matches:
        if (s.home_team, s.away_team) == (m.home.canonical, m.away.canonical) and \
                str(s.kickoff or "")[:10] == (m.kickoff_kst or "")[:10]:
            sm = s
            break
    matches.append({
        "no": m.no, "league": m.league, "kickoff": m.kickoff_kst,
        "odds": [m.odds.home, m.odds.draw, m.odds.away],
        "odds_ah_ou": [m.odds.ah_line is not None, m.odds.ou_line is not None],
        "fetched_at": m.odds.fetched_at,
        "probs": [round(x, 4) for x in (m.probs.home, m.probs.draw, m.probs.away)] if m.probs else None,
        "home": sides["home"], "away": sides["away"],
        "h2h": bool(m.h2h), "radar": bool(m.radar), "matchup_notes": len(m.matchup_notes or []),
        "analysis": an is not None, "axes_metrics": axes,
        "evidence": len(getattr(an, "evidence", ()) or ()) if an else 0,
        "season_match": ({"id": sm.match_id, "finished": sm.finished,
                          "score": [sm.home_goals, sm.away_goals]} if sm else None),
    })

digest = {
    "round": rep.round_id, "generated_at": rep.generated_at,
    "source_status": rep.source_status, "warnings": len(rep.warnings),
    "n_matches": len(rep.matches), "nos": [m.no for m in rep.matches],
    "season_matches": len(rep.season_matches),
    "season_by_comp": dict(Counter(s.competition for s in rep.season_matches)),
    "season_finished": sum(1 for s in rep.season_matches if s.finished),
    "field_fill": dict(sorted(field_fill.items())),
    "total_stats_filled": sum(field_fill.values()),
    "matches": matches,
}
text = json.dumps(digest, ensure_ascii=False, default=str)
print("DIGEST " + text)
if out:
    Path(out).write_text(json.dumps(digest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
