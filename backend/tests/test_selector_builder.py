"""Unit tests for selector_builder."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.selector_builder import build_candidates


def test_build_candidates_prefers_data_testid() -> None:
    cands = build_candidates(
        {
            "tag": "button",
            "id": "btn",
            "dataTestId": "login-submit",
            "name": None,
            "ariaLabel": "Continue",
            "text": "Continue",
            "cssPath": "button.foo",
        }
    )
    strategies = [c.strategy for c in cands]
    assert strategies[0] == "id"
    assert "data-testid" in strategies
    assert cands[0].selector == "#btn"
    assert any(c.selector == '[data-testid="login-submit"]' for c in cands)


def test_build_candidates_text_and_css_path() -> None:
    cands = build_candidates(
        {
            "tag": "span",
            "id": None,
            "dataTestId": None,
            "name": None,
            "ariaLabel": None,
            "text": "Download Summary",
            "cssPath": "div.panel > button:nth-of-type(2)",
        }
    )
    assert any(c.strategy == "text" for c in cands)
    assert any(c.strategy == "css-path" for c in cands)


def test_build_candidates_aria_label() -> None:
    cands = build_candidates(
        {
            "tag": "button",
            "ariaLabel": "Download Summary INV-2024-3325",
            "cssPath": "button",
        }
    )
    assert any(
        c.strategy == "aria-label"
        and "INV-2024-3325" in c.selector
        for c in cands
    )


def test_build_candidates_deduplicates() -> None:
    cands = build_candidates({"tag": "input", "name": "email", "cssPath": "input"})
    selectors = [c.selector for c in cands]
    assert len(selectors) == len(set(selectors))
