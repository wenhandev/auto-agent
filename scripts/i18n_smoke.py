"""Headless Playwright smoke test for the shadcn + i18n migration.

Reproduces the verification done during the migration:
  1. Loads /workflows in the default (English) locale and checks the
     "Workflows" header is rendered.
  2. Navigates to /settings and uses the language Select to switch to
     Simplified Chinese (zh-CN), then re-checks the /workflows header
     for the Chinese label.
  3. Switches to Traditional Chinese (zh-TW) and checks the localized
     header label.

Each step writes a fullpage screenshot to ``auto-agent/assets``:
  - ``shadcn-en.png``
  - ``shadcn-zh-cn.png``
  - ``shadcn-zh-tw.png``

Requirements:
  pip install playwright
  python -m playwright install chromium

Usage:
  # Frontend dev server must be running, e.g. on http://localhost:5173/
  python scripts/i18n_smoke.py [--url http://localhost:5173]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from playwright.sync_api import (
        Page,
        Playwright,
        TimeoutError as PlaywrightTimeoutError,
        sync_playwright,
    )
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(
        "playwright is not installed. Run: pip install playwright "
        "&& python -m playwright install chromium\n"
    )
    raise SystemExit(2) from exc


REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"


EXPECTED_HEADERS = {
    "en": "Workflows",
    "zh-CN": "工作流",
    "zh-TW": "工作流程",
}

LANGUAGE_OPTION_LABEL = {
    "en": "English",
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="http://localhost:5173",
        help="Frontend base URL (default: http://localhost:5173)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser window instead of running headlessly.",
    )
    return parser.parse_args()


def switch_language(page: Page, target: str) -> None:
    """Open the language Select on the Settings page and pick `target`."""
    page.goto(f"{page.url.split('/settings')[0].split('/workflows')[0]}/settings")
    # shadcn Select renders a button; trigger is the language combobox.
    trigger = page.get_by_role("combobox").first
    trigger.click()
    page.get_by_role("option", name=LANGUAGE_OPTION_LABEL[target]).click()
    # Wait for the nav label to switch.
    page.wait_for_timeout(150)


def screenshot_workflows(page: Page, base_url: str, locale: str) -> Path:
    page.goto(f"{base_url}/workflows")
    expected = EXPECTED_HEADERS[locale]
    try:
        page.wait_for_selector(f"text={expected}", timeout=5000)
    except PlaywrightTimeoutError as exc:
        raise AssertionError(
            f"Workflows header for {locale} not found "
            f"(expected text '{expected}'). Page content: {page.content()[:500]}"
        ) from exc
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    out = ASSETS_DIR / f"shadcn-{locale.lower()}.png"
    page.screenshot(path=str(out), full_page=True)
    return out


def run(pw: Playwright, base_url: str, headed: bool) -> list[Path]:
    browser = pw.chromium.launch(headless=not headed)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    saved: list[Path] = []

    page.goto(f"{base_url}/workflows")
    page.wait_for_load_state("networkidle", timeout=10_000)

    for locale in ("en", "zh-CN", "zh-TW"):
        switch_language(page, locale)
        path = screenshot_workflows(page, base_url, locale)
        print(f"[ok] {locale}: header '{EXPECTED_HEADERS[locale]}' -> {path}")
        saved.append(path)

    context.close()
    browser.close()
    return saved


def main() -> int:
    args = parse_args()
    base_url = args.url.rstrip("/")
    with sync_playwright() as pw:
        try:
            saved = run(pw, base_url, args.headed)
        except AssertionError as exc:
            sys.stderr.write(f"[fail] {exc}\n")
            return 1
    print(f"[done] {len(saved)} screenshot(s) saved under {ASSETS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
