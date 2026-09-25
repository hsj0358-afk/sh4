"""Phase 0 environment + source probe (READ-ONLY for the repository).

Run from OUTSIDE the repository, pointing at it:
    python phase0_env.py --repo ~/sh4 --round 260055 --out ~/phase0/env.txt

What it does
  1. Environment: OS, Python, Playwright/Chromium, claude CLI version and
     `claude auth status` (local check - NO model call), secret presence
     (names only, never values), time zone, naive vs aware clocks.
  2. Paths: cache root, browser profile path, panel auto dir (Linux temp),
     /tmp cleanup policy.
  3. Sources: one light request per source using the PROJECT'S OWN clients
     (FotMobBrowser / WhoScoredBrowser with cache=None -> no persistent
     profile, no cache writes; PinnacleClient; plain Playwright for Betman),
     recording stage, status, size, block markers, whether data parsed.

It never writes inside the repository (no cache=, no artifact, no report).
It never runs `claude -p`.
"""
import argparse, json, os, platform, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--round", default="")
ap.add_argument("--out", default="")
ap.add_argument("--skip-sources", action="store_true")
args = ap.parse_args()
repo = Path(args.repo).expanduser().resolve()
sys.path.insert(0, str(repo))
os.chdir(tempfile.mkdtemp(prefix="phase0_"))      # never run inside the repo

lines = []
def say(s=""):
    print(s); lines.append(s)

def sh(argv, timeout=60):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except Exception as exc:                                   # noqa: BLE001
        return None, "", f"{type(exc).__name__}: {exc}"

say("=" * 64); say("PHASE 0 ENV PROBE"); say("=" * 64)
# ---------------------------------------------------------------- 1. env
say(f"OS               : {platform.platform()}")
rc, out, _ = sh(["cat", "/etc/os-release"])
pretty = next((l.split("=", 1)[1].strip('"') for l in out.splitlines()
               if l.startswith("PRETTY_NAME=")), "?")
say(f"distro           : {pretty}")
say(f"python           : {sys.version.split()[0]} ({sys.executable})")
try:
    from importlib.metadata import version
    say(f"playwright       : {version('playwright')}")
except Exception as exc:                                       # noqa: BLE001
    say(f"playwright       : NOT INSTALLED ({exc})")
for mod in ("yaml", "requests", "bs4", "lxml"):
    try:
        __import__(mod); say(f"module {mod:10}: ok")
    except Exception as exc:                                   # noqa: BLE001
        say(f"module {mod:10}: MISSING ({exc})")

rc, out, err = sh(["timedatectl", "show", "-p", "Timezone", "--value"])
say(f"system timezone  : {out or '(timedatectl unavailable)'}")
try:
    say(f"/etc/localtime   : {os.readlink('/etc/localtime')}")
except OSError:
    say("/etc/localtime   : (not a symlink)")
say(f"TZ env           : {os.environ.get('TZ', '(unset)')}")
say(f"LANG             : {os.environ.get('LANG', '(unset)')}")
say(f"datetime.now()   : {datetime.now():%Y-%m-%d %H:%M:%S}  (naive local; roundlog/cache/generated_at use this)")
say(f"datetime.utcnow(): {datetime.utcnow():%Y-%m-%d %H:%M:%S}")
say(f"now(UTC aware)   : {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S %Z}")
off = datetime.now().astimezone().utcoffset()
say(f"local UTC offset : {off}  -> {'OK (KST)' if off and off.total_seconds() == 9*3600 else 'NOT KST - set Asia/Seoul'}")

# secrets: names only
for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
          "TOTO_PANEL_AUTO_DIR", "TOTO_CLAUDE_CLI"):
    say(f"env {k:24}: {'SET' if os.environ.get(k) else 'not set'}")

from toto import panelauto                                     # noqa: E402
cli = panelauto.find_claude_cli()
say(f"claude CLI       : {cli or 'NOT FOUND'}")
if cli:
    ok, ver, why = panelauto.cli_probe(cli)
    say(f"claude --version : {ver or why}")
    a = panelauto.auth_status(cli)
    say(f"claude auth      : state={a.state} method={a.method} provider={a.provider} ({a.message})")

# ---------------------------------------------------------------- 2. paths
from toto.cache import CACHE_ROOT                              # noqa: E402
say("")
say(f"cache root       : {CACHE_ROOT}  exists={CACHE_ROOT.exists()}")
if CACHE_ROOT.exists():
    days = sorted(p.name for p in CACHE_ROOT.iterdir() if p.is_dir())
    say(f"cache entries    : {days[-6:]}")
say(f"browser profile  : {CACHE_ROOT / 'browser'}  exists={(CACHE_ROOT / 'browser').exists()}")
say(f"panel auto root  : {panelauto.auto_root()}  (from TOTO_PANEL_AUTO_DIR or tempfile.gettempdir())")
tmpconf = Path("/usr/lib/tmpfiles.d/tmp.conf")
if tmpconf.exists():
    rule = [l for l in tmpconf.read_text().splitlines() if l.strip() and not l.startswith("#")]
    say(f"/tmp cleanup     : {rule}  ('D' = wiped at boot; age column = periodic cleanup)")
rc, out, _ = sh(["findmnt", "-no", "FSTYPE", "/tmp"])
say(f"/tmp fs          : {out or '(same fs as /)'}")
if args.round:
    from toto import artifact
    say(f"artifact path    : {artifact.path_for(args.round)}  exists={artifact.path_for(args.round).is_file()}")

# ---------------------------------------------------------------- 3. sources
if args.skip_sources:
    say("\n(sources skipped)")
else:
    from toto.settings import load_settings
    settings = load_settings()
    say("")
    say("SOURCES (one light request each; project clients; no cache writes)")

    def verdict(stage, status, size, blocked, parsed, err=""):
        state = ("실패" if (err or not status or status >= 400 or blocked)
                 else ("성공" if parsed else "부분"))
        return (f"{state:3} | stage={stage} | status={status} | {size:,}B | "
                f"blocked={blocked} | parsed={parsed}" + (f" | {err[:140]}" if err else ""))

    # Betman (plain Playwright, same launch args as sources/betman.py)
    t0 = time.time()
    try:
        from playwright.sync_api import sync_playwright
        url = settings.betman.get("buy_url", "https://www.betman.co.kr/main/mainPage/gamebuy/gameBuyList.do")
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = b.new_page()
            r = pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(3000)
            html = pg.content(); title = pg.title(); b.close()
        low = html[:6000].lower()
        blocked = any(s in low for s in ("access denied", "captcha", "차단", "forbidden", "just a moment"))
        parsed = ("승무패" in html) or ("gmId" in html) or ("gameSlip" in html)
        say(f"베트맨    {verdict('browser', r.status if r else 0, len(html), blocked, parsed)} | title={title[:40]!r} | {time.time()-t0:.0f}s")
    except Exception as exc:                                   # noqa: BLE001
        say(f"베트맨    {verdict('browser', 0, 0, False, False, f'{type(exc).__name__}: {exc}')}")

    # FotMob (project FotMobBrowser, non-persistent because cache=None)
    t0 = time.time()
    try:
        from toto.sources.fotmob import FotMobBrowser
        from toto.sources.browser import unwrap_json
        lid = ((settings.leagues or {}).get("epl") or {}).get("fotmob_id", 47)
        with FotMobBrowser(settings, cache=None) as br:
            status, text = br.get_raw(f"https://www.fotmob.com/api/data/leagues?id={lid}")
        try:
            data = json.loads(unwrap_json(text)); parsed = isinstance(data, dict) and bool(data)
            keys = list(data)[:5] if parsed else []
        except Exception:                                      # noqa: BLE001
            parsed, keys = False, []
        low = (text or "")[:4000].lower()
        blocked = any(s in low for s in ("access denied", "captcha", "just a moment", "forbidden"))
        say(f"FotMob    {verdict('browser(API)', status, len(text or ''), blocked, parsed)} | keys={keys} | {time.time()-t0:.0f}s")
    except Exception as exc:                                   # noqa: BLE001
        say(f"FotMob    {verdict('browser(API)', 0, 0, False, False, f'{type(exc).__name__}: {exc}')}")

    # WhoScored (project WhoScoredBrowser + project block markers)
    t0 = time.time()
    try:
        from toto.sources.whoscored import WhoScoredBrowser, _looks_blocked
        with WhoScoredBrowser(settings, cache=None) as br:
            status, html = br.get_raw(settings.whoscored.get("base", "https://www.whoscored.com"))
        blocked = bool(html) and _looks_blocked(html)   # empty = connection failure, not a block page
        parsed = "/Regions/" in (html or "") or "tournament" in (html or "").lower()
        say(f"후스코어드 {verdict('browser', status, len(html or ''), blocked, parsed)} | {time.time()-t0:.0f}s")
    except Exception as exc:                                   # noqa: BLE001
        say(f"후스코어드 {verdict('browser', 0, 0, False, False, f'{type(exc).__name__}: {exc}')}")

    # Pinnacle (project PinnacleClient, plain HTTPS)
    t0 = time.time()
    try:
        from toto.sources.pinnacle import PinnacleClient
        data = PinnacleClient(settings, cache=None)._get("/sports/29/leagues?all=false")
        parsed = isinstance(data, list) and len(data) > 0
        say(f"피나클    {verdict('http(requests)', 200, len(json.dumps(data)), False, parsed)} | leagues={len(data) if parsed else 0} | {time.time()-t0:.0f}s")
    except Exception as exc:                                   # noqa: BLE001
        say(f"피나클    {verdict('http(requests)', 0, 0, False, False, f'{type(exc).__name__}: {exc}')}")

say("")
say("claude model calls by this script: 0 (only --version and auth status)")
if args.out:
    Path(args.out).expanduser().write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nsaved -> {args.out}")
