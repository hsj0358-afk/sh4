"""Phase 0 browser probe. Launches the same kind of Chromium session the
project uses (persistent profile, headless, project UA + stealth script) in a
throwaway profile dir, on a local data: page only. Usage:
    python browser_probe.py <repo> <scratch_profile_dir>"""
import sys, tempfile
from pathlib import Path

repo = Path(sys.argv[1])
profile = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(tempfile.mkdtemp())
sys.path.insert(0, str(repo))
from toto.sources.browser import STEALTH_JS, UA            # noqa: E402
from playwright.sync_api import sync_playwright           # noqa: E402

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(profile), headless=True, user_agent=UA,
        args=["--disable-blink-features=AutomationControlled"])
    ctx.add_init_script(STEALTH_JS)
    page = ctx.new_page()
    page.goto("data:text/html,<title>probe</title><p>ok</p>")
    info = page.evaluate("""() => ({ua: navigator.userAgent,
        platform: navigator.platform, webdriver: navigator.webdriver,
        langs: navigator.languages, tz: Intl.DateTimeFormat().resolvedOptions().timeZone})""")
    print("chromium version :", ctx.browser.version if ctx.browser else "(persistent)")
    print("title            :", page.title())
    for k, v in info.items():
        print(f"{k:17}: {v}")
    ctx.close()
print("profile dir      :", profile, "->", sorted(x.name for x in profile.iterdir())[:6])
