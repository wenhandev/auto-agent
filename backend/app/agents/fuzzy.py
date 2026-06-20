"""Backward-compatible alias for vision_navigate with smart text-click helpers."""

from __future__ import annotations

import asyncio
import math
import random
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin

from app.tools.browser import get_page


class FuzzyAgent:
    """Thin wrapper: fuzzy_action nodes run through vision_navigate."""

    def __init__(self) -> None:
        from app.agents.vision import VisionAgent

        self._vision = VisionAgent()

    async def run_fuzzy_action(
        self,
        instruction: str,
        on_progress: Callable[[str], Awaitable[None]],
    ) -> dict:
        return await self._vision.run_navigate(
            goal=instruction,
            on_progress=on_progress,
        )


async def _page_context(page: Any) -> dict[str, str]:
    try:
        title = await page.title()
    except Exception:
        title = ""
    return {"url": page.url, "title": title}


async def _click_text_smart(page: Any, text: str, *, timeout_ms: int = 2000) -> dict[str, Any]:
    """Click visible text, opening hidden nav menus when needed."""
    locator = page.get_by_text(text, exact=False).first
    ctx = await _page_context(page)
    errors: list[str] = []

    try:
        if await locator.count() == 0:
            return {
                "error": f"no element found matching text {text!r}",
                "retry_hint": "scroll, take a screenshot, or try a shorter label",
                **ctx,
            }
    except Exception as exc:
        return {
            "error": f"could not locate text {text!r}: {exc}",
            "retry_hint": "verify the label exists on the current page",
            **ctx,
        }

    async def _try_visible_click() -> dict[str, Any] | None:
        try:
            if await locator.is_visible(timeout=timeout_ms):
                await locator.click(timeout=timeout_ms)
                return {"clicked_text": text, "method": "visible_click", **ctx}
        except Exception as exc:
            errors.append(f"visible_click: {exc}")
        return None

    result = await _try_visible_click()
    if result is not None:
        return result

    try:
        parent = locator.locator(
            "xpath=ancestor::*[contains(@class,'globalnav') or @role='menuitem' or @role='button'][1]"
        )
        if await parent.count() > 0:
            await parent.hover(timeout=timeout_ms)
            await asyncio.sleep(0.3)
            result = await _try_visible_click()
            if result is not None:
                result["method"] = "hover_parent_click"
                return result
    except Exception as exc:
        errors.append(f"hover_parent: {exc}")

    try:
        await locator.click(force=True, timeout=timeout_ms)
        return {"clicked_text": text, "method": "force_click", **ctx}
    except Exception as exc:
        errors.append(f"force_click: {exc}")

    try:
        href = await locator.get_attribute("href")
        if href:
            target = urljoin(page.url, href)
            await page.goto(target, wait_until="domcontentloaded")
            return {
                "clicked_text": text,
                "method": "href_navigate",
                "href": target,
                **await _page_context(page),
            }
    except Exception as exc:
        errors.append(f"href_navigate: {exc}")

    return {
        "error": (
            f"could not click text {text!r}: element found but not interactable "
            f"({'; '.join(errors) if errors else 'no strategy succeeded'})"
        ),
        "retry_hint": (
            "open the parent navigation menu first, scroll the item into view, "
            "or click a different visible label"
        ),
        **ctx,
    }


async def click_text(text: str) -> dict[str, Any]:
    page = await get_page()
    return await _click_text_smart(page, text)


async def _drag_horizontal(
    page: Any,
    *,
    thumb_selector: str,
    track_selector: str,
    min_percent: float = 0.95,
    steps: int = 24,
) -> dict[str, Any]:
    """Drag a slider thumb horizontally to the end of its track."""
    thumb = page.locator(thumb_selector).first
    track = page.locator(track_selector).first
    ctx = await _page_context(page)

    try:
        if await thumb.count() == 0:
            return {
                "error": f"thumb not found: {thumb_selector!r}",
                "retry_hint": "verify the slider thumb selector",
                **ctx,
            }
        if await track.count() == 0:
            return {
                "error": f"track not found: {track_selector!r}",
                "retry_hint": "verify the slider track selector",
                **ctx,
            }
    except Exception as exc:
        return {"error": f"could not locate slider: {exc}", **ctx}

    track_box = await track.bounding_box()
    thumb_box = await thumb.bounding_box()
    if not track_box or not thumb_box:
        return {
            "error": "could not measure slider bounding boxes",
            "retry_hint": "scroll the slider into view and retry",
            **ctx,
        }

    start_x = thumb_box["x"] + thumb_box["width"] / 2
    start_y = thumb_box["y"] + thumb_box["height"] / 2
    end_x = track_box["x"] + track_box["width"] - thumb_box["width"] / 2 - 2
    end_y = start_y

    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    for i in range(1, steps + 1):
        x = start_x + (end_x - start_x) * i / steps
        await page.mouse.move(x, end_y)
        await asyncio.sleep(0.02)
    await page.mouse.up()
    await asyncio.sleep(0.15)

    verified = False
    try:
        badge = page.locator("#verify-badge.visible, .badge.visible").first
        if await badge.count() > 0 and await badge.is_visible():
            verified = True
    except Exception:
        pass

    dragged_pct = 1.0 if end_x <= start_x else min(1.0, (end_x - start_x) / max(1, track_box["width"]))
    return {
        "dragged": True,
        "method": "mouse_drag",
        "thumb_selector": thumb_selector,
        "track_selector": track_selector,
        "min_percent": min_percent,
        "estimated_percent": round(dragged_pct * 100, 1),
        "verified_badge_visible": verified,
        **await _page_context(page),
    }


async def drag_slider(
    thumb_selector: str = "#slider-thumb",
    track_selector: str = "#slider-track",
    min_percent: float = 0.95,
) -> dict[str, Any]:
    """Drag a captcha-style slider handle to the end of its track."""
    page = await get_page()
    return await _drag_horizontal(
        page,
        thumb_selector=thumb_selector,
        track_selector=track_selector,
        min_percent=min_percent,
    )


_GAP_DETECT_JS = """
() => {
  const canvas = document.getElementById('bg-canvas');
  const thumb = document.getElementById('slider-thumb');
  const trackWrap = document.querySelector('.track-wrap');
  if (!canvas || !thumb || !trackWrap) return { error: 'missing_elements' };

  const w = canvas.width;
  const h = canvas.height;
  const data = canvas.getContext('2d').getImageData(0, 0, w, h).data;
  let bestX = 0;
  let bestScore = -1;

  for (let x = 40; x < w - 40; x++) {
    let score = 0;
    for (let y = 24; y < h - 24; y++) {
      const i = (y * w + x) * 4;
      const lum = data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
      if (data[i + 3] < 128) score += 4;
      const iL = (y * w + x - 1) * 4;
      const iR = (y * w + x + 1) * 4;
      const lumL = data[iL] * 0.299 + data[iL + 1] * 0.587 + data[iL + 2] * 0.114;
      const lumR = data[iR] * 0.299 + data[iR + 1] * 0.587 + data[iR + 2] * 0.114;
      score += Math.abs(lum - lumL) + Math.abs(lum - lumR);
    }
    if (score > bestScore) {
      bestScore = score;
      bestX = x;
    }
  }

  const CW = w;
  const PIECE_W = 52;
  const PIECE_START = 8;
  const travel = CW - PIECE_W - PIECE_START;
  const ratio = travel > 0 ? (bestX - PIECE_START) / travel : 0;
  const maxThumb = trackWrap.clientWidth - thumb.offsetWidth;
  return {
    gap_x: bestX,
    target_thumb_left: Math.max(0, Math.min(maxThumb, ratio * maxThumb)),
    max_thumb_left: maxThumb,
  };
}
"""


async def _drag_human_like(
    page: Any,
    *,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    steps: int = 30,
    jitter: bool = True,
    min_duration_ms: float = 350,
) -> None:
    """Simulate human mouse drag with easing, variable timing, and Y jitter."""
    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.06, 0.14))

    per_step_base = max(0.008, min_duration_ms / 1000 / max(steps, 1))
    for i in range(1, steps + 1):
        t = i / steps
        eased = t * t * (3 - 2 * t)
        x = start_x + (end_x - start_x) * eased
        y = end_y
        if jitter:
            y += math.sin(i * 0.65) * random.uniform(0.8, 2.8)
            y += random.uniform(-1.2, 1.2)
            x += random.uniform(-0.6, 0.6)
        await page.mouse.move(x, y)
        delay = per_step_base * random.uniform(0.75, 1.35)
        delay += 0.012 * (1 - abs(t - 0.5) * 2)
        await asyncio.sleep(delay)

    await asyncio.sleep(random.uniform(0.04, 0.1))
    await page.mouse.up()


async def _detect_puzzle_gap(page: Any) -> dict[str, Any]:
    try:
        result = await page.evaluate(_GAP_DETECT_JS)
    except Exception as exc:
        return {"error": f"gap detection failed: {exc}"}
    if not isinstance(result, dict):
        return {"error": "gap detection returned invalid data"}
    if result.get("error"):
        return {"error": str(result["error"])}
    return result


async def drag_puzzle_captcha(
    thumb_selector: str = "#slider-thumb",
    track_selector: str = "#captcha-track",
    *,
    steps: int = 30,
    jitter: bool = True,
    page: Any | None = None,
) -> dict[str, Any]:
    """Drag a puzzle-piece captcha slider to align with the detected gap."""
    if page is None:
        page = await get_page()
    ctx = await _page_context(page)

    thumb = page.locator(thumb_selector).first
    track = page.locator(track_selector).first
    try:
        if await thumb.count() == 0:
            return {"error": f"thumb not found: {thumb_selector!r}", **ctx}
        if await track.count() == 0:
            return {"error": f"track not found: {track_selector!r}", **ctx}
    except Exception as exc:
        return {"error": f"could not locate puzzle captcha: {exc}", **ctx}

    gap_info = await _detect_puzzle_gap(page)
    if gap_info.get("error"):
        return {"error": gap_info["error"], "retry_hint": "wait for canvas to render", **ctx}

    track_box = await track.bounding_box()
    thumb_box = await thumb.bounding_box()
    if not track_box or not thumb_box:
        return {
            "error": "could not measure puzzle captcha bounding boxes",
            "retry_hint": "scroll captcha into view",
            **ctx,
        }

    target_left = float(gap_info.get("target_thumb_left", 0))
    start_x = thumb_box["x"] + thumb_box["width"] / 2
    start_y = thumb_box["y"] + thumb_box["height"] / 2
    end_x = track_box["x"] + target_left + thumb_box["width"] / 2
    end_y = start_y + random.uniform(-0.5, 0.5)

    await _drag_human_like(
        page,
        start_x=start_x,
        start_y=start_y,
        end_x=end_x,
        end_y=end_y,
        steps=steps,
        jitter=jitter,
    )
    await asyncio.sleep(0.2)

    verified = False
    fail_signal = ""
    try:
        badge = page.locator("#verify-badge.visible, .badge.visible").first
        if await badge.count() > 0 and await badge.is_visible():
            verified = True
        fail_el = page.locator("#captcha-fail")
        if await fail_el.count() > 0:
            fail_signal = await fail_el.get_attribute("data-signal") or ""
    except Exception:
        pass

    return {
        "dragged": True,
        "method": "puzzle_drag",
        "thumb_selector": thumb_selector,
        "track_selector": track_selector,
        "gap_x": gap_info.get("gap_x"),
        "target_thumb_left": round(target_left, 1),
        "verified_badge_visible": verified,
        "anti_bot_signal": fail_signal or None,
        **await _page_context(page),
    }


_RECAPTCHA_IFRAME_SELECTORS = (
    "iframe[src*='recaptcha/api2/anchor']",
    "iframe[title='reCAPTCHA']",
    "iframe[src*='recaptcha']",
)

_RECAPTCHA_ANCHOR_SELECTORS = (
    "#recaptcha-anchor",
    ".recaptcha-checkbox-border",
    "span[role='checkbox']",
    ".rc-anchor-checkbox-holder",
)


async def _find_recaptcha_anchor_frame(page: Any) -> Any | None:
    """Return the Playwright frame hosting the reCAPTCHA v2 anchor checkbox."""
    try:
        await page.wait_for_selector(
            "iframe[src*='recaptcha'], iframe[title='reCAPTCHA']",
            state="attached",
            timeout=15000,
        )
    except Exception:
        pass

    for frame in page.frames:
        url = frame.url or ""
        if "recaptcha/api2/anchor" in url or (
            "google.com/recaptcha" in url and "anchor" in url
        ):
            return frame
    return None


async def _recaptcha_token_present(page: Any) -> bool:
    try:
        return bool(
            await page.evaluate(
                """() => {
                  const ta = document.querySelector('textarea[name="g-recaptcha-response"]');
                  return !!(ta && ta.value && ta.value.length > 0);
                }"""
            )
        )
    except Exception:
        return False


async def _click_recaptcha_in_page(page: Any) -> dict[str, Any]:
    """Click the reCAPTCHA v2 checkbox inside its anchor iframe."""
    ctx = await _page_context(page)
    errors: list[str] = []

    anchor_frame = await _find_recaptcha_anchor_frame(page)
    if anchor_frame is not None:
        for sel in _RECAPTCHA_ANCHOR_SELECTORS:
            try:
                await anchor_frame.wait_for_selector(sel, state="visible", timeout=12000)
                await anchor_frame.click(sel, timeout=5000)
                await asyncio.sleep(1.0)

                checked = False
                try:
                    checked = await anchor_frame.locator(
                        ".recaptcha-checkbox-checked, #recaptcha-anchor[aria-checked='true']"
                    ).first.is_visible()
                except Exception:
                    pass

                token_present = await _recaptcha_token_present(page)
                if not token_present:
                    await asyncio.sleep(1.5)
                    token_present = await _recaptcha_token_present(page)

                return {
                    "clicked": True,
                    "method": "frame_click",
                    "anchor_selector": sel,
                    "checkbox_checked": checked,
                    "token_present": token_present,
                    **await _page_context(page),
                }
            except Exception as exc:
                errors.append(f"frame {sel}: {exc}")

    for sel in _RECAPTCHA_IFRAME_SELECTORS:
        try:
            frame = page.frame_locator(sel).first
            anchor = frame.locator(", ".join(_RECAPTCHA_ANCHOR_SELECTORS)).first
            if await anchor.count() == 0:
                continue
            await anchor.scroll_into_view_if_needed(timeout=3000)
            await anchor.click(timeout=5000)
            await asyncio.sleep(1.0)

            checked = False
            try:
                checked_loc = frame.locator(
                    ".recaptcha-checkbox-checked, #recaptcha-anchor[aria-checked='true']"
                ).first
                if await checked_loc.count() > 0:
                    checked = await checked_loc.is_visible()
            except Exception:
                pass

            token_present = await _recaptcha_token_present(page)
            return {
                "clicked": True,
                "method": "iframe_click",
                "iframe_selector": sel,
                "checkbox_checked": checked,
                "token_present": token_present,
                **await _page_context(page),
            }
        except Exception as exc:
            errors.append(f"{sel}: {exc}")

    return {
        "error": (
            "could not find or click reCAPTCHA checkbox"
            + (f" ({'; '.join(errors)})" if errors else "")
        ),
        "retry_hint": "wait for iframe to load, then click #recaptcha-anchor inside it",
        **ctx,
    }


async def click_recaptcha_checkbox() -> dict[str, Any]:
    """Click the reCAPTCHA v2 checkbox widget on the current page."""
    page = await get_page()
    return await _click_recaptcha_in_page(page)


async def drag_element_horizontal(
    page: Any,
    locator: Any,
    *,
    track_selector: str = "#slider-track",
    min_percent: float = 0.95,
) -> dict[str, Any]:
    """Drag an arbitrary element using the element box as the thumb."""
    ctx = await _page_context(page)
    thumb_box = await locator.bounding_box()
    track = page.locator(track_selector).first
    track_box = await track.bounding_box() if await track.count() > 0 else None

    if not thumb_box:
        return {"error": "element has no bounding box", **ctx}
    if not track_box:
        end_x = thumb_box["x"] + 280
        track_box = {
            "x": thumb_box["x"],
            "y": thumb_box["y"],
            "width": end_x - thumb_box["x"] + thumb_box["width"] / 2,
            "height": thumb_box["height"],
        }

    start_x = thumb_box["x"] + thumb_box["width"] / 2
    start_y = thumb_box["y"] + thumb_box["height"] / 2
    end_x = track_box["x"] + track_box["width"] - thumb_box["width"] / 2 - 2
    end_y = start_y

    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    steps = 24
    for i in range(1, steps + 1):
        x = start_x + (end_x - start_x) * i / steps
        await page.mouse.move(x, end_y)
        await asyncio.sleep(0.02)
    await page.mouse.up()
    await asyncio.sleep(0.15)

    return {
        "dragged": True,
        "method": "element_drag",
        "min_percent": min_percent,
        **await _page_context(page),
    }
