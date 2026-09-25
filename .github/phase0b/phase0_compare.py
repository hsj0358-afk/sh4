"""Phase 0: compare a PC artifact with a VPS artifact of the SAME round.
READ-ONLY - both files are only read (via the project's own loader).

    python phase0_compare.py --repo ~/sh4 \
        --pc  ~/phase0/pc_260055.json \
        --vps ~/sh4/data/artifacts/260055.json \
        [--vps-html ~/sh4/reports/toto_260055.html]

Values that legitimately move between two collection times (odds, market
probabilities, fetched_at, standings/form if a matchday passed in between)
are reported as TIME-VARYING, not as failures. What must match is structure
and coverage: the same 14 matches/teams/kickoffs, and the VPS filling at
least as many fields as the PC.
"""
import argparse, dataclasses, re, sys
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--pc", required=True)
ap.add_argument("--vps", required=True)
ap.add_argument("--vps-html", default="")
ap.add_argument("--tolerance", type=float, default=0.05,
                help="allowed relative drop in non-null stat fields (default 5%%)")
ap.add_argument("--past-round", action="store_true",
                help="round already kicked off: missing odds/market = TIME-VARYING, not failure")
a = ap.parse_args()
sys.path.insert(0, str(Path(a.repo).expanduser().resolve()))
from toto import artifact                                        # noqa: E402

def load(p):
    r, why = artifact.load_path(Path(p).expanduser())
    if r is None:
        sys.exit(f"cannot load {p}: {why}")
    return r

pc, vps = load(a.pc), load(a.vps)
problems, conditional, notes = [], [], []

def head(t):
    print(f"\n== {t}")

def word(s):
    return (s or "").split(" ")[0] if s else "(없음)"

# ------------------------------------------------------------ source status
head("source_status (PC | VPS)")
keys = list(dict.fromkeys(list(pc.source_status) + list(vps.source_status)))
for k in keys:
    p, v = pc.source_status.get(k, ""), vps.source_status.get(k, "")
    print(f"  {k:8}: PC  {p}\n  {'':8}  VPS {v}")
    wp, wv = word(p), word(v)
    core = k in ("경기목록", "순위·폼") or (k == "배당률" and not a.past_round)
    if wv == "실패" or (not v and p):
        (problems if core else conditional).append(f"{k}: VPS {v or '(없음)'}")
    elif wv in ("부분",) and wp == "ok":
        conditional.append(f"{k}: VPS 부분 (PC ok) — {v}")

# ------------------------------------------------------------ matches
head("경기 목록")
print(f"  round PC={pc.round_id} VPS={vps.round_id} | matches PC={len(pc.matches)} VPS={len(vps.matches)}")
if pc.round_id != vps.round_id:
    problems.append("회차가 다릅니다")
nos = [m.no for m in vps.matches]
if len(vps.matches) != 14 or sorted(nos) != list(range(1, 15)):
    problems.append(f"VPS 경기 번호가 1~14 가 아닙니다: {nos}")
pm = {m.no: m for m in pc.matches}
mismatch = 0
for m in vps.matches:
    o = pm.get(m.no)
    if o is None:
        problems.append(f"{m.no}번: PC 에 없음"); continue
    diff = []
    for side in ("home", "away"):
        a1, b1 = getattr(o, side), getattr(m, side)
        if (a1.name_ko, a1.canonical) != (b1.name_ko, b1.canonical):
            diff.append(f"{side} {a1.name_ko}/{a1.canonical} vs {b1.name_ko}/{b1.canonical}")
        if b1.matched is False:
            diff.append(f"{side} VPS 팀명 매칭 실패 '{b1.name_ko}'")
    if o.kickoff_kst != m.kickoff_kst:
        diff.append(f"kickoff {o.kickoff_kst} vs {m.kickoff_kst}")
    if o.league != m.league:
        diff.append(f"league {o.league} vs {m.league}")
    if diff:
        mismatch += 1
        print(f"  {m.no:02d} ✗ " + " · ".join(diff))
print(f"  팀·킥오프·리그 불일치 경기: {mismatch}")
if mismatch:
    problems.append(f"경기 식별 불일치 {mismatch}경기")

# ------------------------------------------------------------ odds / market
head("배당 · Pinnacle 시장 기준선 (값은 수집 시각에 따라 움직임 = TIME-VARYING)")
def has_1x2(m):
    return all(getattr(m.odds, k) is not None for k in ("home", "draw", "away"))
cnt_pc = sum(has_1x2(m) for m in pc.matches); cnt_v = sum(has_1x2(m) for m in vps.matches)
print(f"  1X2 배당 있는 경기: PC {cnt_pc}/14 · VPS {cnt_v}/14")
print(f"  시장확률 있는 경기: PC {sum(m.probs is not None for m in pc.matches)}/14 · "
      f"VPS {sum(m.probs is not None for m in vps.matches)}/14")
maxd = 0.0
for m in vps.matches:
    o = pm.get(m.no)
    if o and m.probs and o.probs:
        d = max(abs(m.probs.home - o.probs.home), abs(m.probs.draw - o.probs.draw),
                abs(m.probs.away - o.probs.away))
        maxd = max(maxd, d)
print(f"  시장확률 최대 차이(%p): {maxd*100:.2f}  · fetched_at 예: "
      f"PC {pc.matches[0].odds.fetched_at} / VPS {vps.matches[0].odds.fetched_at}")
if cnt_v < cnt_pc and a.past_round:
    notes.append(f"배당 {cnt_v}/14 — 이미 시작한 회차라 시장이 닫힘 (TIME-VARYING)")
    print("  → 지난 회차: 배당 부족은 시장 종료로 본다 (--past-round)")
elif cnt_v < cnt_pc:
    (problems if cnt_v == 0 else conditional).append(f"배당 {cnt_v}/14 (PC {cnt_pc}/14)")

# ------------------------------------------------------------ profiles
FIELDS = [f.name for f in dataclasses.fields(type(pc.matches[0].home_profile.stats))]
def profiles(r):
    out = {}
    for m in r.matches:
        for side in ("home", "away"):
            p = getattr(m, f"{side}_profile")
            if p is not None:
                out[(m.no, side)] = p
    return out
PP, VP = profiles(pc), profiles(vps)

def filled(st, f):
    v = getattr(st, f, None)
    return v not in (None, "", [], {})

head("순위 (rank · played · points) — played 가 다르면 그 사이 경기가 있었던 것 = TIME-VARYING")
rank_pc = sum(p.stats.rank is not None for p in PP.values())
rank_v = sum(p.stats.rank is not None for p in VP.values())
played_diff = sum(1 for k, p in VP.items() if k in PP and p.stats.played != PP[k].stats.played)
same_rank = sum(1 for k, p in VP.items() if k in PP and p.stats.rank == PP[k].stats.rank)
print(f"  순위 있는 팀: PC {rank_pc}/28 · VPS {rank_v}/28 · 같은 순위 {same_rank} · played 다른 팀 {played_diff}")
if rank_v < rank_pc:
    (problems if rank_v == 0 else conditional).append(f"순위 {rank_v}/28 (PC {rank_pc}/28)")

head("최근 폼")
f_pc = sum(bool(p.form) for p in PP.values()); f_v = sum(bool(p.form) for p in VP.values())
same_last = sum(1 for k, p in VP.items() if k in PP and p.form and PP[k].form
                and (p.form[0].date, p.form[0].result) == (PP[k].form[0].date, PP[k].form[0].result))
print(f"  폼 있는 팀: PC {f_pc}/28 · VPS {f_v}/28 · 최근 경기 같은 팀 {same_last}")
if f_v < f_pc:
    conditional.append(f"폼 {f_v}/28 (PC {f_pc}/28)")

head("상세 지표 (TeamStats 66칸 중 값이 있는 칸)")
tot_pc = sum(filled(p.stats, f) for p in PP.values() for f in FIELDS)
tot_v = sum(filled(p.stats, f) for p in VP.values() for f in FIELDS)
print(f"  전체 채워진 칸: PC {tot_pc} · VPS {tot_v}")
lost = Counter()
for k, p in VP.items():
    if k in PP:
        for f in FIELDS:
            if filled(PP[k].stats, f) and not filled(p.stats, f):
                lost[f] += 1
if lost:
    print("  PC 에는 있고 VPS 에는 없는 칸 (칸: 팀 수): " +
          ", ".join(f"{f}:{n}" for f, n in lost.most_common(12)))
if tot_pc and tot_v < tot_pc * (1 - a.tolerance):
    conditional.append(f"상세 지표 칸 {tot_v} (PC {tot_pc}, -{(1 - tot_v / tot_pc) * 100:.0f}%)")

head("후스코어드 정성 자료 (강점/약점/스타일)")
def q(r):
    return (sum(bool(p.strengths) for p in r.values()), sum(bool(p.weaknesses) for p in r.values()),
            sum(bool(p.style_of_play) for p in r.values()))
qp, qv = q(PP), q(VP)
print(f"  강점/약점/스타일 있는 팀: PC {qp} · VPS {qv}")
if qv[1] < qp[1] or qv[0] < qp[0]:
    conditional.append(f"정성 자료 VPS {qv} (PC {qp})")

head("시즌 경기 색인 · 분석 축")
print(f"  season_matches: PC {len(pc.season_matches)} · VPS {len(vps.season_matches)}")
print(f"  분석(analysis) 있는 경기: PC {sum(m.analysis is not None for m in pc.matches)} · "
      f"VPS {sum(m.analysis is not None for m in vps.matches)}")
if len(vps.season_matches) < len(pc.season_matches):
    conditional.append(f"시즌 색인 {len(vps.season_matches)} (PC {len(pc.season_matches)})")

if a.vps_html:
    head("VPS 기본 HTML")
    h = Path(a.vps_html).expanduser()
    if not h.is_file():
        problems.append("VPS 리포트 없음")
        print("  없음")
    else:
        t = h.read_text(encoding="utf-8")
        cards = len(re.findall(r'<a class="sumcard" href="#match-\d\d"', t))
        anchors = len(set(re.findall(r'id="match-(\d\d)"', t)))
        print(f"  {h.stat().st_size:,} bytes · 요약 카드 {cards} · 경기 앵커 {anchors} · 외부 script src {len(re.findall(r'<script[^>]+src=', t))}")
        if cards != 14 or anchors != 14:
            problems.append(f"VPS HTML 카드 {cards}/앵커 {anchors}")

head("판정 제안 (최종 판정은 사람이 한다)")
for p in problems:
    print(f"  FAIL 사유: {p}")
for c in conditional:
    print(f"  CONDITIONAL 사유: {c}")
print("  → " + ("FAIL" if problems else "CONDITIONAL" if conditional else "PASS"))
