"""Deterministic DOM → Playwright selector candidate generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from playwright.async_api import Page


_INTERACTIVE_TAGS = frozenset(
    {"a", "button", "input", "select", "textarea", "label", "summary"}
)
_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "link",
        "textbox",
        "combobox",
        "checkbox",
        "radio",
        "switch",
        "tab",
        "menuitem",
        "searchbox",
        "spinbutton",
    }
)

_RESOLVE_AT_POINT_JS = """
([x, y]) => {
  const INTERACTIVE_TAGS = new Set(%(tags)s);
  const INTERACTIVE_ROLES = new Set(%(roles)s);

  function isInteractive(el) {
    if (!el || el.nodeType !== 1) return false;
    const tag = el.tagName.toLowerCase();
    if (INTERACTIVE_TAGS.has(tag)) return true;
    const role = el.getAttribute('role');
    if (role && INTERACTIVE_ROLES.has(role)) return true;
    if (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1') return true;
    if (typeof el.onclick === 'function') return true;
    return false;
  }

  function findInteractive(el) {
    let cur = el;
    for (let i = 0; i < 4 && cur; i++) {
      if (isInteractive(cur)) return cur;
      cur = cur.parentElement;
    }
    return el;
  }

  function visibleText(el) {
    const t = (el.innerText || el.textContent || '').trim();
    return t.length > 80 ? t.slice(0, 80) : t;
  }

  function cssPath(el) {
    if (!el || el.nodeType !== 1) return '';
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 4) {
      let part = cur.tagName.toLowerCase();
      if (cur.id) {
        parts.unshift('#' + CSS.escape(cur.id));
        break;
      }
      const testId = cur.getAttribute('data-testid');
      if (testId) {
        parts.unshift('[data-testid="' + testId.replace(/"/g, '\\"') + '"]');
        break;
      }
      const parent = cur.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(
          (c) => c.tagName === cur.tagName
        );
        if (siblings.length > 1) {
          const idx = siblings.indexOf(cur) + 1;
          part += ':nth-of-type(' + idx + ')';
        }
      }
      parts.unshift(part);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }

  function describe(el) {
    return {
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      dataTestId: el.getAttribute('data-testid') || null,
      name: el.getAttribute('name') || null,
      ariaLabel: el.getAttribute('aria-label') || null,
      text: visibleText(el),
      role: el.getAttribute('role') || null,
      cssPath: cssPath(el),
    };
  }

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (x < 0 || y < 0 || x > vw || y > vh) {
    return { error: 'coordinates outside viewport', viewport: { width: vw, height: vh } };
  }

  let el = document.elementFromPoint(x, y);
  if (!el) {
    return { error: 'no element at point', viewport: { width: vw, height: vh } };
  }
  el = findInteractive(el);
  return { element: describe(el), viewport: { width: vw, height: vh } };
}
""" % {
    "tags": json.dumps(list(_INTERACTIVE_TAGS)),
    "roles": json.dumps(list(_INTERACTIVE_ROLES)),
}


@dataclass(frozen=True)
class SelectorCandidate:
    selector: str
    strategy: str
    confidence: float
    match_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "strategy": self.strategy,
            "confidence": self.confidence,
            "match_count": self.match_count,
        }


def _escape_attr(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_candidates(descriptor: dict[str, Any]) -> list[SelectorCandidate]:
    """Build ordered selector candidates from an element descriptor (no DOM access)."""
    candidates: list[SelectorCandidate] = []
    seen: set[str] = set()

    def add(selector: str, strategy: str, confidence: float) -> None:
        if not selector or selector in seen:
            return
        seen.add(selector)
        candidates.append(
            SelectorCandidate(selector=selector, strategy=strategy, confidence=confidence)
        )

    el_id = descriptor.get("id")
    if el_id and isinstance(el_id, str) and el_id.strip():
        safe_id = re.sub(r'([!"#$%&\'()*+,./:;<=>?@\[\\\]^`{|}~])', r"\\\1", el_id.strip())
        add(f"#{safe_id}", "id", 0.98)

    test_id = descriptor.get("dataTestId") or descriptor.get("data_testid")
    if test_id and isinstance(test_id, str) and test_id.strip():
        add(
            f'[data-testid="{_escape_attr(test_id.strip())}"]',
            "data-testid",
            0.95,
        )

    name = descriptor.get("name")
    if name and isinstance(name, str) and name.strip():
        tag = descriptor.get("tag") or "input"
        add(
            f'{tag}[name="{_escape_attr(name.strip())}"]',
            "name",
            0.88,
        )

    aria = descriptor.get("ariaLabel") or descriptor.get("aria_label")
    if aria and isinstance(aria, str) and aria.strip():
        add(
            f'[aria-label="{_escape_attr(aria.strip())}"]',
            "aria-label",
            0.85,
        )

    text = descriptor.get("text")
    if text and isinstance(text, str) and text.strip() and len(text.strip()) <= 80:
        snippet = text.strip().replace('"', '\\"')
        add(f'text="{snippet}"', "text", 0.75)

    css_path = descriptor.get("cssPath") or descriptor.get("css_path")
    if css_path and isinstance(css_path, str) and css_path.strip():
        add(css_path.strip(), "css-path", 0.55)

    return candidates


async def _count_matches(page: Page, selector: str) -> int:
    if selector.startswith("text="):
        text = selector[5:].strip().strip('"').strip("'")
        try:
            return await page.get_by_text(text, exact=True).count()
        except Exception:
            return 0
    try:
        return await page.locator(selector).count()
    except Exception:
        return 0


async def enrich_candidates(page: Page, candidates: list[SelectorCandidate]) -> list[SelectorCandidate]:
    """Attach match_count; drop id candidates when id is not unique."""
    enriched: list[SelectorCandidate] = []
    el_id = None
    for c in candidates:
        if c.strategy == "id":
            el_id = c.selector.lstrip("#")
            break

    if el_id:
        try:
            id_count = await page.locator(f"#{el_id}").count()
        except Exception:
            id_count = 0
        if id_count != 1:
            candidates = [c for c in candidates if c.strategy != "id"]

    for c in candidates:
        count = await _count_matches(page, c.selector)
        enriched.append(
            SelectorCandidate(
                selector=c.selector,
                strategy=c.strategy,
                confidence=c.confidence,
                match_count=count,
            )
        )
    return enriched


async def resolve_element_at_point(page: Page, x: float, y: float) -> dict[str, Any]:
    """Resolve interactive element at viewport coordinates."""
    raw = await page.evaluate(_RESOLVE_AT_POINT_JS, [x, y])
    if not isinstance(raw, dict):
        return {"error": "invalid pick result"}
    if raw.get("error"):
        return raw
    element = raw.get("element")
    if not isinstance(element, dict):
        return {"error": "no element at point"}
    candidates = build_candidates(element)
    candidates = await enrich_candidates(page, candidates)
    return {
        "element_summary": {
            "tag": element.get("tag"),
            "role": element.get("role"),
            "name": element.get("ariaLabel") or element.get("text"),
            "text": element.get("text"),
        },
        "candidates": [c.to_dict() for c in candidates],
        "viewport": raw.get("viewport"),
    }


async def test_selector_on_page(page: Page, selector: str) -> dict[str, Any]:
    """Return match count and preview for a selector on the current page."""
    count = await _count_matches(page, selector)
    preview: dict[str, Any] = {"tag": None, "text": None, "role": None, "visible": False}
    if count >= 1:
        try:
            if selector.startswith("text="):
                text = selector[5:].strip().strip('"').strip("'")
                loc = page.get_by_text(text, exact=True).first
            else:
                loc = page.locator(selector).first
            preview = await loc.evaluate(
                """el => ({
                    tag: el.tagName ? el.tagName.toLowerCase() : null,
                    text: ((el.innerText || el.textContent || '').trim()).slice(0, 120),
                    role: el.getAttribute('role'),
                    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
                })"""
            )
        except Exception:
            pass
    return {"match_count": count, "preview": preview}
