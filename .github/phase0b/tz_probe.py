"""Phase 0 time-zone probe. Read-only: imports toto, loads a saved artifact,
calls the project's own comparison functions with simulated instants.
Usage: TZ=UTC python tz_probe.py <repo> <round>   (then TZ=Asia/Seoul)"""
import os, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

repo, rnd = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(repo))
from toto import artifact, roundlog, marketeval          # noqa: E402
from toto.models import as_of_from_match, KST             # noqa: E402

print(f"TZ env            : {os.environ.get('TZ', '(unset)')}")
try:
    print(f"/etc/localtime    : {os.readlink('/etc/localtime')}")
except OSError:
    print("/etc/localtime    : (not a symlink)")
print(f"time.tzname       : {time.tzname}")
print(f"datetime.now()    : {datetime.now():%Y-%m-%d %H:%M:%S}  (naive local)")
print(f"datetime.utcnow() : {datetime.utcnow():%Y-%m-%d %H:%M:%S}  (naive UTC)")
print(f"now(timezone.utc) : {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S %Z}")
print(f"roundlog now      : {datetime.now():%Y-%m-%d %H:%M}  "
      "(roundlog.record uses naive datetime.now(), roundlog.py:422)")

report, why = artifact.load(rnd)
if report is None:
    sys.exit(f"artifact not loaded: {why}")
m = report.matches[0]
k_aware = as_of_from_match(m)
print(f"sample kickoff    : match {m.no} kickoff_kst='{m.kickoff_kst}' "
      f"-> {k_aware.isoformat()} (aware KST)")

# Simulated real instant: 1 hour AFTER kickoff.
t = k_aware + timedelta(hours=1)
local_naive = datetime.fromtimestamp(t.timestamp())   # what datetime.now() returns then
stamp = local_naive.strftime("%Y-%m-%d %H:%M")        # generated_at / recorded_at
print(f"\nscenario          : real instant = kickoff + 1h = {t.isoformat()}")
print(f"  local now seen  : {local_naive:%Y-%m-%d %H:%M} (naive)")
print(f"  roundlog._started -> {roundlog._started(m.kickoff_kst, local_naive)}"
      "   (expected True: match already started)")
rec, kick = marketeval._stamp(stamp), marketeval._stamp(m.kickoff_kst)
print(f"  marketeval recorded_at={stamp} >= kickoff? {rec >= kick}"
      "   (expected True: post-kickoff row must be excluded)")
print(f"  artifact.is_prematch(now=aware) -> "
      f"{artifact.is_prematch(report, now=t)}   (production path is aware; expected False)")

# Cache folder date around KST midnight.
t2 = datetime(2026, 9, 26, 3, 0, tzinfo=KST)
print(f"\ncache day at {t2.isoformat()} : "
      f"{datetime.fromtimestamp(t2.timestamp()):%Y-%m-%d} "
      "(cache.py:39 uses naive datetime.now(); KST date is 2026-09-26)")
